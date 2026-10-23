
"""대학원 공동 이용 논문 검색 · AI 요약 · 과제 제출 Streamlit 웹 앱.

레이아웃: 왼쪽 사이드바 = 검색/개인키/과제표지, 오른쪽 = 결과/요약/통계/다운로드.

실행: streamlit run app.py
관리자: DATA_GO_KR_API_KEY 는 Cloud Secrets 또는 로컬 .env에서 공급.
사용자: OpenAI 키는 화면에서 개인별로 입력하며 파일/DB/로그에 저장하지 않음.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import date

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from paperlab import (
    API_NAME, SOURCE_URL, PaperAPIError, calculate_trends, extract_pdf_text,
    add_access_links, clean_paper_title, nanet_detail_url,
    scholar_search_url, prepare_evidence, search_candidates, search_papers, select_type,
    filter_paper_records, missing_title_rows, PAPER_DB_NAMES, clean_paper_title,
    summarize_paper, summary_lines,
)
from dcollection_fallback import (
    ALL_UNIVERSITIES, make_dcollection_destinations, no_results_from_nanet,
    universities,
)
from external_research import (
    research_source_names, research_search_destination, research_search_table,
)
from reporting import create_excel, create_pdf_report
from ui_helpers import ai_summary_blockers
from pdf_analysis import extract_pdf_pages
from prompt_templates import ASSIGNMENT, READING, fields_for, DISPLAY_NAMES, mode_label
from research_ai import (
    analyze_paper, analysis_lines, analysis_summary, estimate_ai_calls,
    normalize_analysis,
)
from citation_styles import (
    JOURNAL, THESIS, REPORT, UNKNOWN, REFERENCE_TYPES, REFERENCE_TEMPLATES,
    THESIS_EXAMPLE, suggested_citation, complete_citation, format_reference,
    missing_citation_fields,
)
from nanet_detail import fetch_nanet_detail_metadata, MetadataLookupError
from nanet_search_flow import (
    search_literature_basic, sort_catalog_records, partition_catalog_records, merge_catalog_pages,
    CATEGORY_ORDER,
)
from riss_catalog import (
    RISS_NAME, RISS_SOURCE_URL, RissCatalogError,
    fetch_riss_catalog, summarize_riss, make_riss_excel,
)

def admin_api_key() -> str:
    """Cloud Secret 우선, .env 대체. 사용자 화면에는 키를 노출하지 않음."""
    try:
        value = st.secrets.get("DATA_GO_KR_API_KEY", "")
        if value:
            return str(value)
    except (FileNotFoundError, OSError, KeyError):
        pass
    return os.getenv("DATA_GO_KR_API_KEY", "")


def riss_api_endpoint() -> str:
    """RISS Swagger GET 엔드포인트는 전체 경로가 확정된 뒤 관리자만 등록."""
    try:
        address = st.secrets.get("RISS_API_URL", "")
        if address:
            return str(address).strip()
    except (FileNotFoundError, OSError, KeyError):
        pass
    return os.getenv("RISS_API_URL", "").strip()


def riss_api_key() -> str:
    """보통 기존 공공데이터 서비스키 재사용; 별도 승인키가 있으면 선택 사용."""
    try:
        value = st.secrets.get("RISS_API_KEY", "")
        if value:
            return str(value)
    except (FileNotFoundError, OSError, KeyError):
        pass
    return os.getenv("RISS_API_KEY", "") or admin_api_key()


def current_paper() -> tuple[dict | None, str]:
    """검색 선택과 직접 업로드 중 하나의 서지정보를 보고서에 사용."""
    if st.session_state.get("paper_mode") == "검색 목록에서 선택":
        df = st.session_state.get("filtered_df")
        idx = st.session_state.get("selected_idx")
        if df is None or df.empty or idx is None or idx >= len(df):
            return None, ""
        row = df.iloc[idx].to_dict()
        return row, "국회도서관 API 검색 서지정보"
    title = st.session_state.get("manual_title", "").strip()
    if not title:
        return None, ""
    row = {
        "자료명/저자사항": title,
        "발행자": st.session_state.get("manual_publisher", "").strip(),
        "발행년": st.session_state.get("manual_year", "").strip(),
        "DB": "사용자 업로드",
        "controlno": "",
    }
    return row, "사용자 직접 제공 논문"



def edit_citation(paper: dict) -> dict[str, str]:
    """선택 논문별 참고문헌 입력·검증 UI. 자료가 바뀌면 각 논문의 입력값을 구분 보관."""
    unique = str(paper.get("controlno") or paper.get("자료명/저자사항") or "직접입력")
    suffix = hashlib.sha256(unique.encode("utf-8")).hexdigest()[:14]
    initial = suggested_citation(paper)
    previous = st.session_state.get("citation_records", {}).get(suffix, {})
    if isinstance(previous, dict):
        initial.update({name: val for name, val in previous.items() if name in initial})

    def text_field(key: str, label: str, note: str = "") -> str:
        return st.text_input(
            label, value=initial.get(key, ""), key=f"ref_{suffix}_{key}",
            help=note or "원문 서지정보와 대조하여 직접 수정하세요.",
        ).strip()

    st.markdown("#### 📝 정식 참고문헌 정보 확인")
    st.caption(
        "국회도서관 API가 제공하지 않는 DOI·권호·페이지·학위정보는 임의 생성하지 않습니다. "
        "서지정보와 논문 PDF를 대조하여 아래 항목을 수정하세요."
    )
    types = [UNKNOWN, *REFERENCE_TYPES]
    category = st.selectbox(
        "자료 종류 선택", types,
        index=types.index(initial["type"]) if initial["type"] in types else 0,
        key=f"ref_{suffix}_category",
        help="검색 결과의 DB가 미분류라면 원문 종류를 직접 선택해 주세요.",
    )
    author = text_field("author", "저자 또는 기관명")
    title = text_field("title", "논문/보고서 제목")
    date_value = text_field("publication_date", "발행·학위수여 연월", "예: 2026년 8월 (연도만 알면 월 미확인이라고 표시)")
    record = {"type": category, "author": author,
              "title": title, "publication_date": date_value}

    if category == JOURNAL:
        c1, c2 = st.columns(2)
        with c1:
            record["journal"] = text_field("journal", "학술지명")
            record["volume"] = text_field("volume", "권(Volume)")
        with c2:
            record["issue"] = text_field("issue", "호(Issue)")
            record["pages"] = text_field("pages", "수록 페이지")
        record["doi"] = text_field("doi", "DOI (있으면 입력)")
    elif category == THESIS:
        degrees = ["", "석사학위논문", "박사학위논문"]
        default_degree = initial.get("degree", "")
        record["degree"] = st.selectbox(
            "학위 종류", degrees, index=degrees.index(default_degree)
            if default_degree in degrees else 0, key=f"ref_{suffix}_degree",
        )
        record["university"] = text_field("university", "학위수여 대학·대학원", "예: 고려대학교 대학원")
    elif category == REPORT:
        record["publisher"] = text_field("publisher", "발행기관")
        record["report_number"] = text_field("report_number", "보고서 번호")
        c1, c2 = st.columns(2)
        with c1:
            record["doi"] = text_field("doi", "DOI (선택)")
        with c2:
            record["url"] = text_field("url", "보고서 URL (선택)")

    citation = complete_citation(paper, record)
    st.session_state.setdefault("citation_records", {})[suffix] = citation
    st.markdown("**모든 화면·보고서에 사용할 정식 참고문헌**")
    st.code(format_reference(citation), language=None)
    missing = missing_citation_fields(citation)
    if missing:
        st.warning("제출 전 추가 확인: " + ", ".join(missing))
    else:
        st.success("표기 항목이 채워졌습니다. 실제 원문과 맞는지 마지막으로 확인하세요.")
    return citation





def render_search_controls():
    """P0 search screen; all other legacy research functions are retained."""
    from p0_search_ui import render_search_controls as render
    render(admin_api_key())


def render_university_theses():
    """02와 독립된 01의 대학 학위논문 검색 페이지. 학교 검색은 외부 링크로 명시."""
    st.subheader("🏛 대학 학위논문 검색")
    st.caption("대학 dCollection 자료를 찾습니다. 국회도서관 검색 결과와 섞지 않습니다.")
    uni = st.selectbox("검색 대학", universities(), key="dcollection_university")
    query = st.text_input(
        "학위논문 제목 또는 연구 키워드",
        value=st.session_state.get("search_keyword", ""),
        key="dcollection_query", placeholder="예: 데이터베이스 포렌식",
    )
    links = make_dcollection_destinations(uni, query)
    left, right = st.columns(2)
    with left:
        st.link_button("🔎 입력 키워드로 대학 논문 찾기 ↗", links["web_search_url"],
                       disabled=not bool(links["keyword"]), use_container_width=True)
    with right:
        st.link_button("🏫 학교 dCollection 직접 검색 ↗", links["repository_search_url"],
                       use_container_width=True)
    st.link_button("전국 dCollection 참여대학 목록 ↗", links["directory_url"])
    st.info(
        "왼쪽 버튼은 Google의 site: 검색을 이용합니다. 검색 결과를 앱으로 자동 수집하지 않으며, "
        "오른쪽 버튼은 대학 저장소 검색 화면만 열고 키워드를 자동 입력하지 않습니다. "
        "검색 가능한 자료와 PDF 열람은 각 기관의 공개·이용 조건에 따릅니다."
    )


def render_external_controls():
    st.divider()
    with st.expander("📑 학회·협회·연구보고서 검색", expanded=False):
        src_name = st.selectbox(
            "검색 대상 기관/학술정보 서비스", research_source_names(),
            key="external_research_source",
        )
        src_keyword = st.text_input(
            "외부 검색에 사용할 주제·키워드", key="external_research_query",
            value="내부통제", placeholder="예: 내부통제, 포렌식",
        )
        src_links = research_search_destination(src_name, src_keyword)
        st.link_button(
            "🔎 이 키워드로 자료 검색 결과 열기 ↗",
            src_links["search_url"],
            disabled=not bool(src_links["keyword"]), use_container_width=True,
        )
        st.caption(
            "외부 검색 사이트(Google/Scholar)에서 실제 키워드 검색을 실행합니다. "
            "검색결과를 이 앱으로 자동 가져오거나, 원문 제공을 보장하지 않습니다."
        )


def render_riss_controls():
    st.divider()
    with st.expander("📚 RISS 서지 구축 통계", expanded=False):
        st.caption("기관코드·조사년도·국내/국외 MARC 구축 건수. 개별 논문 검색이 아닙니다.")
        riss_endpoint = riss_api_endpoint()
        riss_key = riss_api_key()
        if not riss_endpoint:
            st.info("관리자가 Swagger의 GET 전체 경로를 RISS_API_URL에 추가하면 사용할 수 있습니다.")
        if not riss_key:
            st.warning("승인된 RISS API용 공공데이터 인증키를 설정하세요.")
        with st.form("riss_load_form", clear_on_submit=False):
            riss_pages = st.selectbox("가져올 페이지 수", [1, 2, 3, 5, 10], index=2)
            riss_per_page = st.selectbox("페이지당 기관 기록", [10, 20, 50, 100], index=3)
            load_riss = st.form_submit_button(
                "📊 RISS 통계 불러오기", use_container_width=True,
                disabled=not (bool(riss_endpoint) and bool(riss_key)),
            )
        if load_riss:
            st.session_state.riss_notice = None
            st.session_state.riss_df = pd.DataFrame()
            try:
                with st.spinner("RISS 종합목록 통계를 가져오는 중입니다..."):
                    count, riss_df, columns = fetch_riss_catalog(
                        riss_key, riss_endpoint,
                        pages=riss_pages, per_page=riss_per_page,
                    )
                st.session_state.riss_df = riss_df
                st.session_state.riss_total = count
                st.session_state.riss_fields = columns
                st.session_state.riss_notice = (
                    "success", f"RISS 통계 {len(riss_df):,}건 수집 / API 전체 {count:,}건",
                )
            except (ValueError, RissCatalogError) as exc:
                st.session_state.riss_notice = ("error", str(exc))
            except Exception as exc:
                st.session_state.riss_notice = (
                    "error", f"RISS 통계 요청 실패 ({type(exc).__name__}). 관리자에게 문의하세요.",
                )



def render_search_results(admin_key):
    from p0_search_ui import render_search_results as render
    render(admin_key)


def render_ai_summary(user_ai_key, model):
    st.subheader("2. 논문 선택 및 근거 자료 업로드")
    if "paper_mode" not in st.session_state:
        frame = st.session_state.get("filtered_df")
        suggested_mode = ("검색 목록에서 선택" if isinstance(frame, pd.DataFrame) and not frame.empty
                          else "논문 직접 업로드")
        st.session_state.paper_mode = st.session_state.get("saved_paper_mode", suggested_mode)
    st.radio("분석할 자료 준비 방법", ["검색 목록에서 선택", "논문 직접 업로드"],
             horizontal=True, key="paper_mode")
    st.session_state.saved_paper_mode = st.session_state.paper_mode
    if st.session_state.paper_mode == "검색 목록에서 선택":
        select_df = st.session_state.get("filtered_df")
        if not isinstance(select_df, pd.DataFrame) or select_df.empty:
            st.warning("검색 탭에서 자료를 검색하거나 '논문 직접 업로드'로 전환하세요.")
            st.session_state.selected_idx = None
        else:
            options = list(range(len(select_df)))
            # 메뉴 전환 시 제거된 selectbox 위젯의 선택 상태 복구.
            if "selected_idx" not in st.session_state:
                st.session_state.selected_idx = st.session_state.get("saved_selected_idx")
            if st.session_state.get("selected_idx") not in options:
                st.session_state.pop("selected_idx", None)
            st.selectbox(
                "검색된 자료 중 한 편을 선택", options, key="selected_idx",
                format_func=lambda i: (
                    f"{str(select_df.iloc[i].get('발행년', ''))} | "
                    f"{str(select_df.iloc[i].get('자료명/저자사항', ''))[:115]}"
                ),
            )
            st.session_state.saved_selected_idx = st.session_state.get("selected_idx")
    else:
        for name in ("manual_title", "manual_publisher", "manual_year"):
            if name not in st.session_state:
                st.session_state[name] = st.session_state.get("saved_" + name, "")
        st.text_input("논문 제목 (필수)", key="manual_title", placeholder="예: 데이터베이스 포렌식 관련 연구")
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("저자·발행처 (알면 입력)", key="manual_publisher")
        with col2:
            st.text_input("발행연도 (알면 입력)", key="manual_year", max_chars=4)
        for name in ("manual_title", "manual_publisher", "manual_year"):
            st.session_state["saved_" + name] = st.session_state.get(name, "")

    paper, origin = current_paper()
    st.session_state.active_current_paper = paper
    st.session_state.active_origin = origin
    if paper:
        st.markdown(f"**선택 논문:** {clean_paper_title(paper.get('자료명/저자사항', ''))}")
        detail_url = nanet_detail_url(paper)
        scholar_url = scholar_search_url(paper.get("자료명/저자사항", ""))
        paper_links = st.columns(2)
        with paper_links[0]:
            if detail_url:
                st.link_button("📖 국회도서관 상세·원문 확인", detail_url, use_container_width=True)
            else:
                st.caption("이 자료는 국회도서관 관리번호가 없어 상세페이지 직접 연결이 어렵습니다.")
        with paper_links[1]:
            if scholar_url:
                st.link_button("🔎 Google Scholar에서 공개본 검색", scholar_url, use_container_width=True)
        st.caption("상세정보에서 '원문보기' 제공 여부를 확인하세요. 이용 제한 자료는 로그인/기관 방문이 필요할 수 있습니다.")
    # 서지정보 임시 참고문헌은 요약과 직접 관련 없으므로 보고서 탭에서만 확인합니다.
    st.markdown("#### ① 요약 목적 선택")
    mode_text = st.radio(
        "원하는 요약 방식", ["과제 제출용 · 6개 항목", "논문 읽기용 · 7문장"],
        horizontal=True, key="ai_summary_mode",
        help="두 방식의 결과는 각각 독립적으로 저장되며, AI 요청도 각각 발생합니다.",
    )
    current_mode = ASSIGNMENT if mode_text.startswith("과제") else READING
    st.caption("과제 제출용: 주제·목적·기술·활용·한계·발전 방향 / 논문 읽기용: 배경·질문·데이터·방법·결과·의의·후속 연구")

    st.markdown("#### ② 논문 PDF 업로드")
    st.caption("PDF를 올리면 **전체 페이지에서 추출 가능한 텍스트**를 읽고, AI에는 중요한 구간을 선별·분할해 전송합니다. 초록을 따로 입력할 필요는 없습니다.")
    uploader_gen = st.session_state.get("pdf_uploader_generation", 0)
    uploaded = st.file_uploader("논문 PDF 파일 업로드 (최대 15MB)", type=["pdf"],
                                key=f"pdf_upload_v23_{uploader_gen}")
    pdf_doc = None
    pdf_digest = ""
    pdf_count = None
    if uploaded is not None:
        uploaded_bytes = uploaded.getvalue()
        pdf_digest = hashlib.sha256(uploaded_bytes).hexdigest()
        try:
            # 페이지별 민감 자료는 전역 Streamlit 캐시가 아닌 개별 사용자 세션에만 유지.
            if st.session_state.get("pdf_doc_sha") != pdf_digest:
                st.session_state.pdf_doc = extract_pdf_pages(uploaded_bytes)
                st.session_state.pdf_doc_sha = pdf_digest
                st.session_state.pdf_bytes = uploaded_bytes
            else:
                st.session_state.pdf_bytes = uploaded_bytes
            pdf_doc = st.session_state.pdf_doc
            pdf_count = pdf_doc.total_pages
            if pdf_doc.char_count < 80:
                st.warning("PDF에서 읽을 수 있는 글자가 부족합니다. 스캔 PDF는 OCR을 지원하지 않으므로 아래에서 초록을 직접 입력하세요.")
            else:
                st.success(
                    f"PDF 전체 {pdf_count:,}페이지 중 {pdf_doc.text_pages:,}페이지에서 텍스트 추출 완료 "
                    f"({pdf_doc.char_count:,}자). AI 분석 시 결과·결론까지 포함하도록 대표 구간을 선별합니다."
                )
                if pdf_doc.clipped_pages:
                    st.warning(f"문자 수가 매우 많은 {pdf_doc.clipped_pages}개 페이지는 페이지 앞뒤 일부만 보존했습니다.")
                max_calls = estimate_ai_calls(pdf_doc)
                st.caption(f"이번 PDF 분석은 OpenAI API를 약 {max_calls}회 호출합니다. 구간별 분석이 필요한 긴 PDF는 "
                           "호출이 여러 번 발생하므로 개인 계정에 추가 비용이 청구될 수 있습니다.")
        except ValueError as exc:
            st.error(str(exc))
            st.session_state.pop("pdf_doc", None)
            st.session_state.pop("pdf_doc_sha", None)
            st.session_state.pop("pdf_bytes", None)
    else:
        # 다른 메뉴에 다녀온 후에도 본인 세션의 PDF 추출 결과를 유지.
        pdf_doc = st.session_state.get("pdf_doc")
        pdf_digest = st.session_state.get("pdf_doc_sha", "")
        if pdf_doc is not None:
            st.caption("이전 메뉴에서 업로드한 PDF가 현재 세션에 보관되어 있습니다.")

    usable_pdf_doc = pdf_doc if pdf_doc is not None and pdf_doc.char_count >= 80 else None
    with st.expander("✍️ PDF가 없거나 글자를 읽지 못할 때: 초록 직접 입력 (선택)",
                     expanded=bool(uploaded is not None and usable_pdf_doc is None)):
        abstract_key = f"abstract_widget_{st.session_state.get('abstract_generation', 0)}"
        if abstract_key not in st.session_state:
            st.session_state[abstract_key] = st.session_state.get("saved_abstract", "")
        abstract = st.text_area(
            "초록 또는 본문 발췌 붙여넣기 (선택)", height=155, key=abstract_key,
            placeholder="PDF를 확보하지 못했을 때 원문에서 확인한 초록을 붙여넣으세요.",
            help="PDF 텍스트 추출에 성공했다면 이 입력란은 비워 두셔도 됩니다.",
        )
        st.caption("PDF 없이 초록만 제공하면 근거 페이지는 표시할 수 없습니다.")
    st.session_state.saved_abstract = abstract.strip()
    if st.button("🗑 이 세션의 PDF·초록 원문 삭제", key="clear_pdf_02"):
        for name in ("pdf_doc", "pdf_doc_sha", "pdf_bytes", "saved_abstract", "active_evidence_id"):
            st.session_state.pop(name, None)
        st.session_state.pdf_uploader_generation = st.session_state.get("pdf_uploader_generation", 0) + 1
        st.session_state.abstract_generation = st.session_state.get("abstract_generation", 0) + 1
        st.rerun()

    # 사용자가 제공한 자료와 모드가 바뀌면 다른 결과를 잘못 재사용하지 않도록 해시로 구분.
    material_digest = hashlib.sha256((pdf_digest + "|" + abstract.strip()).encode("utf-8")).hexdigest()
    evidence_id = material_digest if (usable_pdf_doc or abstract.strip()) else ""
    paper_id = "" if paper is None else str(paper.get("controlno") or paper.get("자료명/저자사항"))
    evidence = abstract.strip() + (" ".join(p.text[:200] for p in usable_pdf_doc.pages if p.text.strip()) if usable_pdf_doc else "")
    context_key = (paper_id, evidence_id, current_mode)
    st.session_state.active_evidence_id = evidence_id
    st.session_state.active_paper_id = paper_id
    st.markdown("#### ③ 논문 확인 후 AI 요약")
    confirmed = st.checkbox("선택한 논문과 업로드 PDF/초록이 같은 논문임을 확인했습니다.")
    blockers = ai_summary_blockers(paper, confirmed, evidence, user_ai_key)
    enabled = not blockers
    if blockers:
        first = blockers[0]
        if first == "API_KEY":
            st.warning("🔑 **OpenAI API 키를 입력해야 AI 요약 버튼이 활성화됩니다.** "
                       "왼쪽 사이드바의 **'🤖 개인 AI 설정 → 본인의 OpenAI API 키'**에 입력해 주세요. "
                       "국회도서관 검색용 공공데이터 API 키와는 별개입니다.")
        elif first == "PAPER":
            st.info("분석할 논문을 위에서 선택하거나 직접 업로드해 주세요.")
        elif first == "EVIDENCE":
            st.info("분석할 내용이 없습니다. PDF를 업로드하거나 접힌 **'초록 직접 입력'**을 펼쳐 주세요.")
        elif first == "CONFIRM":
            st.info("선택 논문과 PDF/초록이 일치하는지 확인한 뒤 체크해 주세요.")
    else:
        st.success("AI 요약 준비 완료! 아래 버튼을 누르세요.")

    generate_caption = "✨ 6개 항목 AI 요약 생성" if current_mode == ASSIGNMENT else "✨ 7문장 논문 읽기 요약 생성"
    if st.button(generate_caption, type="primary", disabled=not enabled):
        try:
            with st.spinner("논문의 배경·방법·결과·결론을 확인하고 원문 근거를 대조하는 중..."):
                if usable_pdf_doc is None and current_mode == ASSIGNMENT:
                    # 구형 요약 함수와 과제 제출 형식을 유지 (초록 전용 1회 호출)
                    legacy = summarize_paper(user_ai_key, paper["자료명/저자사항"], abstract, model=model)
                    result = normalize_analysis({"items": [
                        {"key": name, "text": legacy[name], "evidence": []} for name in fields_for(ASSIGNMENT)
                    ]}, ASSIGNMENT, None, abstract)
                    result.update({"model": model, "ai_calls": 1, "strategy": "입력 초록 · 단일 AI 분석",
                                   "coverage": {"total_pages": 0, "text_pages": 0,
                                                "selected_pages": [], "selected_page_count": 0,
                                                "clipped_pages": 0, "chars_extracted": len(abstract.strip()), "sections": {}}})
                else:
                    result = analyze_paper(
                        user_ai_key, paper["자료명/저자사항"], current_mode,
                        pdf_doc=usable_pdf_doc, abstract=abstract, model=model,
                    )
            saved = st.session_state.get("analysis_results", {})
            saved[context_key] = result
            st.session_state.analysis_results = saved
            st.session_state.summary_result = analysis_summary(result)  # 이전 버전 인터페이스 호환
            st.session_state.summary_context = (paper_id, evidence_id)
            st.session_state.summary_origin = "+".join(filter(None, [
                "입력 초록" if abstract.strip() else "", "사용자 PDF" if usable_pdf_doc else "",
            ]))
            st.success(f"{mode_label(current_mode)} 생성 완료 · OpenAI 요청 {result['ai_calls']}회")
        except Exception as exc:
            # 외부 서비스 에러 본문에는 입력 내용이 섞일 수 있으므로 유형만 화면 표시
            st.error(f"AI 요약 생성 실패 ({type(exc).__name__}). API 키, 결제 상태, 모델 권한, 본문을 확인하세요.")

    result = st.session_state.get("analysis_results", {}).get(context_key)
    st.session_state.active_ai_result = result
    if result:
        st.subheader(f"{mode_label(current_mode)} 분석 결과")
        for index, item in enumerate(result["items"], 1):
            st.markdown(f"**{index}. {DISPLAY_NAMES.get(item['key'], item['key'])}:** {item['text']}")
            if item.get("evidence"):
                with st.expander(f"📄 {index}번 항목 근거 확인 (원문 문구 일치)", expanded=False):
                    for quote in item["evidence"]:
                        ref = f"PDF 기준 {quote['page']}쪽" if quote['page'] is not None else "사용자 입력 초록"
                        st.caption(f"{ref} · {quote['status']}")
                        st.write(quote["quote"])
                    st.caption("문구·페이지 일치만 확인했습니다. 의미 해석의 정확성은 원문과 직접 대조하세요.")
            else:
                st.caption("이 항목은 검증된 직접 인용이 없습니다. 원문에서 사실 여부를 확인해 주세요.")
        st.code(analysis_lines(result), language=None)
        st.download_button("요약 텍스트(.txt) 다운로드", analysis_lines(result).encode("utf-8-sig"),
                           file_name=f"논문_{'6항목' if current_mode == ASSIGNMENT else '7문장'}_요약.txt",
                           mime="text/plain", key=f"summary_txt_{current_mode}")
        info = result.get("coverage", {})
        if info.get("total_pages", 0):
            st.caption(f"PDF {info['total_pages']}페이지 중 대표 {info['selected_page_count']}페이지를 AI 분석 근거로 선별 · "
                       f"검증된 직접 인용 {result.get('evidence_verified_count', 0)}개 · "
                       f"일치 검증 실패 {result.get('unverified_quote_count', 0)}개(근거에서 제외)")
            with st.expander("📋 분석된 PDF 범위와 근거 페이지", expanded=False):
                for section, pages_used in info.get("sections", {}).items():
                    st.write(f"**{section}:** PDF 페이지 {', '.join(map(str, pages_used))}")
                st.caption("PDF 전체에서 텍스트를 추출했지만 AI에 모든 문장을 보내지는 않았습니다. "
                           "장 제목·대표 페이지의 발췌를 분석한 결과이므로 원문 전체의 완전성을 보장하지 않습니다.")
        if current_mode == READING:
            st.info("나의 생각·의문은 오른쪽 '논문 읽기·나의 생각 → ④ 나의 생각·저장'에서 직접 작성합니다. 입력값은 두 요약 모드의 보고서에서 공유됩니다.")
        st.caption("AI 생성 문장입니다. 원문 인용 문구가 일치해도 결론의 타당성은 사람이 재확인해야 합니다.")
    else:
        st.info("현재 논문·근거 자료·선택한 요약 방식의 분석 결과가 없습니다. AI 키·PDF를 준비하고 요약을 생성하세요.")



def render_trends():
    st.subheader("3. 수집한 자료의 연구 동향")
    filtered = st.session_state.get("filtered_df")
    if not isinstance(filtered, pd.DataFrame) or filtered.empty:
        st.info("먼저 국회도서관 API에서 논문을 검색하세요.")
    else:
        year_df, type_df = calculate_trends(filtered)
        st.caption(f"현재 수집·필터링된 {len(filtered):,}건만 분석합니다. 전체 학술 논문 모집단의 통계가 아닙니다.")
        y1, y2 = st.columns(2)
        with y1:
            st.markdown("**발행연도별 건수**")
            if not year_df.empty:
                st.bar_chart(year_df.set_index("발행연도"), y="건수", use_container_width=True)
                st.dataframe(year_df, hide_index=True)
            else:
                st.info("발행연도 데이터가 없습니다.")
        with y2:
            st.markdown("**자료 유형별 건수**")
            if not type_df.empty:
                st.bar_chart(type_df.set_index("자료유형"), y="건수", use_container_width=True)
                st.dataframe(type_df, hide_index=True)
            else:
                st.info("자료유형 데이터가 없습니다.")
        st.write("결측치 집계")
        missing_counts = filtered.replace(r"^\s*$", pd.NA, regex=True).isna().sum()
        st.dataframe(missing_counts.rename("결측 또는 빈값 건수"), use_container_width=True)
        duplicates = filtered.duplicated(subset=["controlno"] if "controlno" in filtered else None).sum()
        st.metric("자료 중복 건수", f"{duplicates}건")



def render_riss():
    st.subheader("4. RISS 종합목록 · 서지 구축 현황")
    st.caption("출처: 한국교육학술정보원_RISS 종합목록 · 개별 논문 제목이나 초록을 제공하는 API가 아닙니다.")
    st.markdown(f"[공공데이터포털 원본 데이터]({RISS_SOURCE_URL})")
    notice = st.session_state.get("riss_notice")
    if notice:
        kind, message = notice
        if kind == "success":
            st.success(message)
        else:
            st.error(message)

    stats_df = st.session_state.get("riss_df")
    if isinstance(stats_df, pd.DataFrame) and not stats_df.empty:
        st.caption("※ API의 전체 건수가 아닌 실제 가져온 기관·연도 기록만 대상으로 집계합니다.")
        overall, raw_yearly, raw_by_org = (
            len(stats_df), *summarize_riss(stats_df)
        )
        a, b, c = st.columns(3)
        a.metric("API 전체 기록", f"{st.session_state.get('riss_total', 0):,}건")
        b.metric("현재 수집한 기록", f"{overall:,}건")
        c.metric("조회된 조사년도", f"{stats_df['조사년도'].replace('', pd.NA).nunique():,}개")

        valid_years = sorted([x for x in stats_df["조사년도"].unique() if str(x).strip()], reverse=True)
        year_options = ["전체 조사년도"] + valid_years
        chosen_year = st.selectbox(
            "기관별 순위를 볼 조사년도", year_options,
            index=1 if len(year_options) > 1 else 0,
            help="기관별 구축건수는 연도별로 볼 때 해석하기 쉽습니다. 전체 연도를 합하면 반복 집계될 수 있습니다.",
        )
        selected_riss = (stats_df[stats_df["조사년도"] == chosen_year]
                         if chosen_year != "전체 조사년도" else stats_df)
        _, ranked = summarize_riss(selected_riss)
        st.markdown("**조사년도별 국내·국외 구축 건수 (현재 수집 범위)**")
        if not raw_yearly.empty:
            graph = raw_yearly.set_index("조사년도")[["국내 구축건수", "국외 구축건수"]].fillna(0)
            st.bar_chart(graph, use_container_width=True)
            st.dataframe(raw_yearly, hide_index=True, use_container_width=True)
        st.markdown("**기관코드별 구축 건수 상위 15개**")
        if not ranked.empty:
            st.dataframe(ranked.head(15), hide_index=True, use_container_width=True)
        st.markdown("**원본 기관·연도 기록**")
        st.dataframe(selected_riss, hide_index=True, use_container_width=True)
        st.caption(
            "서지 구축건수는 논문 수가 아닙니다. 자료가 누적 지표일 수 있으므로 "
            "여러 연도를 단순 합산한 값을 신규 구축량으로 해석하면 안 됩니다. "
            "기관코드에 해당하는 기관명은 이 API만으로 식별되지 않을 수 있습니다."
        )
        st.markdown("**자료 품질 확인**")
        missing_count = stats_df.isna().sum().rename("결측 건수")
        st.dataframe(missing_count, use_container_width=True)
        st.metric("동일한 원본 행의 중복 건수", f"{stats_df.duplicated().sum():,}건")
        try:
            report = make_riss_excel(stats_df, raw_yearly, raw_by_org)
            st.download_button(
                "📥 RISS 서지통계 Excel 다운로드", report,
                file_name="RISS_기관별서지구축_분석.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"엑셀 파일 생성 실패 ({type(exc).__name__})")
    else:
        st.info("왼쪽 사이드바의 'RISS 서지 구축 통계'에서 불러오기를 실행하세요.")
        if not riss_api_endpoint():
            st.warning(
                "RISS_API_URL 미설정: 공공데이터포털의 승인된 RISS 종합목록 Swagger에서 "
                "GET 요청의 전체 주소(uddi 포함)를 복사하여 운영자가 등록해야 합니다."
            )
        st.caption("RISS 통계는 논문 검색·AI 요약·참고문헌 생성에 섞이지 않습니다.")



def render_sources():
    st.subheader("5. 학회·협회 논문 및 연구보고서 찾기")
    st.caption("KCI · 학회 · 협회 · 공공기관 · ScienceON의 공식 페이지와 실제 외부 키워드 검색 결과로 연결합니다.")
    st.info(
        "검색 방식: 입력한 키워드로 Google의 기관별 site: 검색 또는 Google Scholar 검색을 엽니다. "
        "별도의 유료/기관 API 없이 사용하지만, 외부 사이트의 검색결과는 이 앱에서 자동 수집하지 않습니다."
    )
    source = st.session_state.get("external_research_source", research_source_names()[0])
    phrase = st.session_state.get("external_research_query", "").strip()
    dest = research_search_destination(source, phrase)
    st.write(f"선택 기관: **{source}**")
    st.write(f"입력 검색어: **{phrase or '(미입력)'}**")
    st.caption(f"검색 방식: {dest['search_engine']}")
    c1, c2 = st.columns(2)
    with c1:
        st.link_button(
            "🔎 이 키워드로 검색 결과 열기 ↗", dest["search_url"],
            use_container_width=True, disabled=not bool(phrase),
        )
    with c2:
        st.link_button(
            "🏛 기관 공식 사이트 열기 ↗", dest["homepage_url"],
            use_container_width=True,
        )
    if not phrase:
        st.warning("왼쪽 '학회·협회·연구보고서 검색' 메뉴에서 키워드를 입력해 주세요.")
    else:
        st.markdown("**다른 기관에서도 같은 키워드 검색하기**")
        st.dataframe(
            pd.DataFrame(research_search_table(phrase)),
            hide_index=True, use_container_width=True,
            column_config={
                "기관/검색처": st.column_config.TextColumn("기관/검색처", width="medium"),
                "자료 유형": st.column_config.TextColumn("자료 유형", width="medium"),
                "키워드 검색 결과": st.column_config.LinkColumn(
                    "🔎 외부 검색 결과", display_text="검색 결과 열기 ↗", width="medium"
                ),
                "공식 홈페이지": st.column_config.LinkColumn(
                    "🏛 공식 사이트", display_text="공식 사이트 열기 ↗", width="medium"
                ),
            },
        )
    st.caption(
        "Google에서 일부 기관 자료가 누락되거나 링크가 변경될 수 있습니다. "
        "학회·연구보고서의 서지정보·발행기관·저작권·원문 접근 조건을 원문 사이트에서 확인해 주세요."
    )



def render_submission(school, department, course, student, professor, submission_date):
    evidence_id = st.session_state.get("active_evidence_id", "")
    st.subheader("6. 과제 보고서 다운로드")
    st.caption("과제 표지의 학교·교과목·제출자 정보는 왼쪽 '과제 표지 정보'를 펼쳐 입력하세요.")
    preview = pd.DataFrame([
        {"항목": "학교 / 전공", "입력 내용": " / ".join(filter(None, [school, department])) or "미입력"},
        {"항목": "교과목", "입력 내용": course or "미입력"},
        {"항목": "제출자", "입력 내용": student or "미입력"},
        {"항목": "제출일", "입력 내용": submission_date.isoformat()},
    ])
    st.dataframe(preview, hide_index=True, use_container_width=True)

    selected, origin = current_paper()
    filtered = st.session_state.get("filtered_df")
    if not isinstance(filtered, pd.DataFrame):
        filtered = pd.DataFrame()
    # 직접 업로드한 논문은 앞서 수행한 검색 결과와 혼합하지 않습니다.
    if st.session_state.get("paper_mode") == "논문 직접 업로드":
        report_df = pd.DataFrame([selected]) if selected else pd.DataFrame()
    else:
        report_df = filtered.copy()
    keyword_for_report = st.session_state.get("search_keyword", "")
    if st.session_state.get("paper_mode") == "논문 직접 업로드":
        keyword_for_report = selected.get("자료명/저자사항", "") if selected else ""
    st.markdown("### 출력할 요약 모드")
    report_mode_label = st.radio(
        "보고서 형식", ["과제 제출용 · 6개 항목", "논문 읽기용 · 7문장"],
        horizontal=True, key="report_summary_mode",
        help="분석을 생성한 모드만 파일에 반영됩니다. 각 모드는 따로 생성해 주세요.",
    )
    report_mode = ASSIGNMENT if report_mode_label.startswith("과제") else READING
    report_paper_id = str(selected.get("controlno") or selected.get("자료명/저자사항")) if selected else ""
    result_to_export = st.session_state.get("analysis_results", {}).get((report_paper_id, evidence_id, report_mode))
    summary_to_export = analysis_summary(result_to_export) if result_to_export else None
    note_id = hashlib.sha256(f"{report_paper_id}|{evidence_id}".encode()).hexdigest()[:16]
    note_text = st.session_state.get("research_notes", {}).get(note_id, "") if report_mode == READING else ""
    if result_to_export:
        st.success(f"{mode_label(report_mode)} 분석 결과를 포함하여 보고서를 생성합니다.")
    else:
        st.info("현재 선택한 논문·자료에 대한 이 모드의 요약 결과가 없습니다. 먼저 '논문 AI 요약' 탭에서 생성하세요.")

    with st.expander("📚 자료 종류별 참고문헌 표기 기준 (필요할 때만 열기)", expanded=False):
        st.caption("이번 과제에 지정한 형식입니다. 제출 기관의 별도 인용 규정이 있으면 그 규정을 우선하세요.")
        for kind, template in REFERENCE_TEMPLATES.items():
            st.markdown(f"**{kind}**")
            st.code(template, language=None)
        st.caption("학위논문 표기 예시: " + THESIS_EXAMPLE)

    report_citation = None
    if selected:
        st.caption("서지정보는 같은 02 메뉴의 '논문 읽기·나의 생각 → 정식 참고문헌 확인·수정'에서 편집할 수 있습니다.")
        report_citation = st.session_state.get("active_citation_record")
        if not report_citation:
            report_citation = complete_citation(selected)
        st.code(format_reference(report_citation), language=None)
        missing_fields = missing_citation_fields(report_citation)
        if missing_fields:
            st.warning("참고문헌 보완 필요: " + ", ".join(missing_fields))
    else:
        st.info("참고문헌을 작성하려면 먼저 검색 목록에서 논문을 선택하거나 직접 업로드하세요.")

    if not report_df.empty:
        try:
            excel_data = create_excel(report_df, keyword_for_report,
                                      summary_to_export, selected, data_origin=origin,
                                      citation_record=report_citation,
                                      summary_mode=report_mode, analysis_result=result_to_export,
                                      research_note=note_text)
            st.download_button(
                "📊 검색·통계·참고문헌 Excel 다운로드", excel_data,
                file_name="논문_검색분석_과제자료.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"엑셀 생성 실패: {type(exc).__name__}")
    else:
        st.info("엑셀 출력을 위해 먼저 논문을 검색하거나 직접 입력해 주세요.")

    if selected and summary_to_export:
        if not student.strip() or not course.strip():
            st.warning("왼쪽 사이드바의 과제 표지 정보에서 제출자 이름과 교과목을 입력하세요.")
        else:
            metadata = {
                "school": school, "department": department, "course": course,
                "student": student, "professor": professor,
                "date": submission_date.isoformat(),
            }
            y_df, t_df = calculate_trends(report_df)
            try:
                pdf_data = create_pdf_report(
                    keyword_for_report, metadata, selected, summary_to_export,
                    y_df, t_df, st.session_state.get("summary_origin", "사용자 제공 텍스트"),
                    data_origin=origin, citation_record=report_citation,
                    summary_mode=report_mode, analysis_result=result_to_export,
                    research_note=note_text,
                )
                st.download_button(
                    "📄 표지 포함 PDF 과제 보고서 다운로드", pdf_data,
                    file_name=("논문_AI분석_과제보고서.pdf" if report_mode == ASSIGNMENT
                               else "논문_7문장_읽기노트.pdf"), mime="application/pdf",
                    type="primary", use_container_width=True,
                )
            except Exception as exc:
                st.error(f"PDF 보고서 생성 실패: {type(exc).__name__}")
    else:
        st.info("PDF 보고서를 만들려면 '논문 AI 요약' 탭에서 선택한 모드의 요약을 먼저 생성하세요.")



def render_help():
        st.info("대학 dCollection 및 학회·협회·보고서 검색은 입력 키워드로 외부 검색 결과를 여는 기능입니다. 국회도서관 API의 앱 내부 검색과 구분됩니다.")
        st.subheader("이용 및 과제 제출 안내")
        st.markdown("""
    **화면 구성**
    - 왼쪽 사이드바: 연구 주제 검색, 검색조건·자료유형 필터, 개인 AI 키, 과제 표지 입력
    - 오른쪽 메인: 검색 결과, AI 논문 요약, 연구 동향, RISS 서지 구축 통계, PDF·Excel 다운로드

    **기능 구성**
    - 국회도서관 API 논문 검색: 별도 비용 없는 공공데이터 API, 관리자 키 사용
    - 자료 통계: 검색 결과 내 발행연도와 유형의 빈도 분석
    - AI 요약: 6항목 과제용과 7문장 논문 읽기용 중 선택. PDF 전체 페이지 텍스트 추출 후 배경·방법·결과·결론 구간을 선별해 분석. PDF가 없거나 스캔본일 때만 접이식 초록 입력 사용
    - RISS 종합목록: 기관코드·조사년도별 국내/국외 서지 구축 현황 및 Excel 다운로드 (논문 검색 기능 아님)
    - 과제 제출: 학교·전공·이름·과목 표지, PDF 보고서, Excel 통계 및 자료유형별 참고문헌 표기

    **주의 사항**
    - 원우 개인 OpenAI API 키는 암호형 입력창으로 받으며 파일과 데이터베이스에 저장하지 않습니다. 브라우저 세션이 유지되는 동안 Streamlit 서버가 처리할 수 있습니다. 사용 후 창을 닫으세요.
    - 업로드한 PDF 텍스트는 OpenAI API에 전달됩니다. 저작권·개인정보·연구윤리 및 과목별 AI 활용 기준을 확인하세요.
    - 스캔본 PDF는 OCR 기능이 없어 초록을 복사하여 넣어야 합니다. PDF 전체에서 텍스트를 추출하지만 AI에는 핵심 페이지의 일부를 전달하고, 긴 PDF는 구간별로 분석합니다. 섹션의 모든 내용을 읽거나 Figure 이미지를 해석하는 것은 아닙니다.
    - API는 서지 목록 중심이며 논문 초록·본문을 자동으로 제공한다고 보장할 수 없습니다.
    - 참고문헌 편집과 자료별 표기 기준은 '과제 보고서' 탭에서 펼쳐 확인할 수 있습니다. 학술지 논문·학위논문·기관 연구보고서의 과제용 형식 중 선택합니다. 원문에 없는 서지정보는 '미확인'으로 표시하므로 제출 전에 반드시 검증하고 수정해야 합니다.
    - 공개 접속 주소를 아는 누구나 이용할 수 있습니다. 회원별 사용기록·개인 계정 기능은 구현하지 않았습니다.
    """)
        st.markdown(f"**데이터 출처:** [{API_NAME}]({SOURCE_URL}) · [{RISS_NAME}]({RISS_SOURCE_URL})")
        st.caption("국회도서관 API 요청형식: /basic?serviceKey=...&pageno=1&displaylines=10&search=전체,키워드")

