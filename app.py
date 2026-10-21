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
from citation_styles import (
    JOURNAL, THESIS, REPORT, UNKNOWN, REFERENCE_TYPES, REFERENCE_TEMPLATES,
    THESIS_EXAMPLE, suggested_citation, complete_citation, format_reference,
    missing_citation_fields,
)
from riss_catalog import (
    RISS_NAME, RISS_SOURCE_URL, RissCatalogError,
    fetch_riss_catalog, summarize_riss, make_riss_excel,
)

st.set_page_config(
    page_title="대학원 AI 논문 연구 도우미", page_icon="🎓", layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 1.8rem; max-width: 1500px;}
h1, h2, h3 {color: #17365D;}
[data-testid="stMetric"] {background: #f3f7fb; padding: 15px; border-radius: 12px;}
.small-copy {color:#55697d; font-size:.91rem;}
</style>
""", unsafe_allow_html=True)

load_dotenv()


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
    initial = suggested_citation(paper)
    unique = str(paper.get("controlno") or paper.get("자료명/저자사항") or "직접입력")
    suffix = hashlib.sha256(unique.encode("utf-8")).hexdigest()[:14]

    def text_field(key: str, label: str, note: str = "") -> str:
        return st.text_input(
            label, value=initial.get(key, ""), key=f"ref_{suffix}_{key}",
            help=note or "원문 서지정보와 대조하여 직접 수정하세요.",
        ).strip()

    st.markdown("#### 📝 자료 유형별 참고문헌 정보 확인")
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
    st.markdown("**과제보고서에 들어갈 참고문헌 미리보기**")
    st.code(format_reference(citation), language=None)
    missing = missing_citation_fields(citation)
    if missing:
        st.warning("제출 전 추가 확인: " + ", ".join(missing))
    else:
        st.success("표기 항목이 채워졌습니다. 실제 원문과 맞는지 마지막으로 확인하세요.")
    return citation


st.title("🎓 대학원 AI 논문 연구 도우미")
st.caption("논문 검색 → 연구 동향 분석 → 근거 기반 AI 6줄 요약 → 과제 제출 보고서")
st.caption("버전 2.1 · 쉬운 AI 요약 화면 · 자료유형별 참고문헌 · dCollection · RISS 서지통계")

# -------------------------------------------------------------------------
# 왼쪽: 논문 주제 검색 / 자료유형 필터 / 개인 AI 키 / 과제 표지 설정
# 오른쪽: 검색 결과, AI 분석, 연구 동향, 과제 다운로드
# -------------------------------------------------------------------------
with st.sidebar:
    st.header("🔎 논문 주제 검색")
    admin_key = admin_api_key()
    if admin_key:
        st.caption("✅ 국회도서관 API 키 읽기 완료 (실제 연결은 검색 시 확인)")
    else:
        st.warning("관리자 API 키가 없어 검색할 수 없습니다. PDF 직접 분석은 가능합니다.")

    # 검색 조건은 사이드바, 실제 검색 상태와 결과는 오른쪽에 표시.
    with st.form("search_form", clear_on_submit=False):
        keyword = st.text_input(
            "검색할 논문 주제",
            value=st.session_state.get("search_keyword", "데이터베이스 포렌식"),
            placeholder="예: 데이터베이스 포렌식",
        )
        search_field = st.selectbox(
            "검색 대상", ["전체", "자료명", "키워드"], index=0,
            help="국회도서관 자료검색 API의 공식 검색항목입니다.",
        )
        pages = st.selectbox("검색 페이지 수", [1, 2, 3, 4, 5], index=1)
        per_page = st.selectbox("페이지당 검색 건수", [5, 10, 15, 20], index=1)
        automatic_retry = st.checkbox(
            "검색 결과가 0건이면 핵심 단어로 재검색", value=True,
            help="예: '데이터베이스 포렌식'이 0건이면 '포렌식'으로 다시 검색하고 결과에 표시합니다.",
        )
        searched = st.form_submit_button(
            "🔎 논문 검색 실행", type="primary", use_container_width=True,
            disabled=not bool(admin_key),
        )

    if searched:
        now = time.monotonic()
        recent = [t for t in st.session_state.get("search_events", []) if now - t < 3600]
        st.session_state.pop("search_notice", None)
        st.session_state.search_attempts = []
        if len(recent) >= 12:
            st.session_state.search_notice = (
                "error", "이 브라우저 세션은 1시간에 최대 12회 검색할 수 있습니다."
            )
        else:
            try:
                candidates = search_candidates(keyword, automatic_retry)
                attempts = []
                xml_diagnostics = []
                final_df = pd.DataFrame()
                final_total = 0
                used_keyword = candidates[0]
                with st.spinner("국회도서관 API를 검색하는 중..."):
                    for candidate in candidates:
                        # 실제 요청마다 호출량 계산: 자동 재검색 역시 1회로 계산.
                        if len(recent) + len(attempts) >= 12:
                            break
                        total, result_df = search_papers(
                            admin_key, candidate, pages=pages,
                            per_page=per_page, search_field=search_field,
                            diagnostics=xml_diagnostics,
                        )
                        attempts.append((candidate, total, len(result_df)))
                        final_total, final_df, used_keyword = total, result_df, candidate
                        if not result_df.empty or total > 0:
                            break
                st.session_state.search_events = recent + [now] * len(attempts)
                st.session_state.search_attempts = attempts
                st.session_state.xml_diagnostics = xml_diagnostics
                st.session_state.paper_df = final_df
                st.session_state.search_keyword = keyword.strip()
                st.session_state.dcollection_query = keyword.strip()
                st.session_state.search_used_keyword = used_keyword
                st.session_state.search_field = search_field
                st.session_state.total_count = final_total
                st.session_state.pop("summary_result", None)
                st.session_state.pop("summary_context", None)
                st.session_state.pop("selected_idx", None)
                st.session_state.pop("sidebar_types", None)

                if not final_df.empty:
                    if used_keyword != keyword.strip():
                        message = (
                            f"입력 검색어 '{keyword.strip()}'는 결과가 없어 "
                            f"'{used_keyword}'(으)로 확장 검색했습니다. "
                            f"수집 {len(final_df):,}건 / API 전체 {final_total:,}건."
                        )
                    else:
                        message = f"검색 성공: 수집 {len(final_df):,}건 / API 전체 {final_total:,}건."
                    st.session_state.search_notice = ("success", message)
                elif final_total > 0:
                    st.session_state.search_notice = (
                        "error",
                        f"API 연결과 인증은 정상이며 전체 {final_total:,}건이 검색되었습니다. "
                        "다만 논문 목록을 읽지 못했습니다. 아래 'API 검색 진단'에서 "
                        "XML 태그 구조를 확인해 주세요. 인증키 문제는 아닙니다.",
                    )
                else:
                    checked = ", ".join(f"'{term}'" for term, _, _ in attempts)
                    st.session_state.search_notice = (
                        "info", f"API 응답은 정상이나 검색 결과가 0건입니다. "
                        f"시도한 검색어: {checked}. '자료명' 또는 다른 검색어도 시험해 보세요.",
                    )
            except (PaperAPIError, ValueError) as exc:
                st.session_state.search_notice = ("error", str(exc))
            except Exception as exc:
                st.session_state.search_notice = (
                    "error", f"검색에 실패했습니다 ({type(exc).__name__}). 관리자에게 문의하세요."
                )

    # 선택지가 비어 있거나 사용자가 필터를 모두 해제해도 원래 검색 목록을 표시.
    # 빈 목록과 필터 없는 전체 목록을 혼동하지 않도록 합니다.
    df = st.session_state.get("paper_df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        available_types = sorted(
            {str(t).strip() or "미분류" for t in df["DB"]},
            key=lambda t: (t == "미분류", t),
        )
        chosen_types = st.multiselect(
            "검색 자료유형 필터", available_types, default=available_types,
            key="sidebar_types",
            help="자료유형을 지정하지 않으면 전체 검색자료가 표시됩니다. "
                 "국회도서관 응답에 자료유형이 없으면 미분류로 표시됩니다.",
        )
        filtered = select_type(df, chosen_types)
        st.session_state.filtered_df = filtered
        st.caption(f"선택된 자료: {len(filtered):,}건")
        if not chosen_types:
            st.caption("필터 선택이 없어 전체 자료를 보여줍니다.")
        if "미분류" in available_types:
            st.caption("※ '미분류'는 API에 자료유형 정보가 없는 자료입니다.")
    else:
        st.session_state.filtered_df = pd.DataFrame()

    # The typed query is used in an actual external search URL; do not claim
    # that merely typing into the field runs the institution's own search.
    st.divider()
    with st.expander("🏛 대학별 논문·원문 찾기", expanded=False):
        dc_university_sidebar = st.selectbox(
            "원문을 찾을 대학", universities(), key="dcollection_university",
            help="대학별 공식 dCollection 사이트를 선택합니다.",
        )
        dc_query_sidebar = st.text_input(
            "외부 웹검색에 사용할 제목·키워드",
            value=st.session_state.get("search_keyword", ""),
            key="dcollection_query",
            placeholder="예: 내부통제",
            help="입력 후 아래 '키워드 검색 결과 열기'를 누르면 Google에서 선택 대학의 dCollection만 실제 검색합니다.",
        )
        dc_side_links = make_dcollection_destinations(dc_university_sidebar, dc_query_sidebar)
        st.link_button(
            "🔎 입력 키워드로 검색 결과 열기 ↗",
            dc_side_links["web_search_url"],
            disabled=not bool(dc_side_links["keyword"]), use_container_width=True,
        )
        st.link_button(
            "🏫 학교 dCollection 자료검색 화면 열기 ↗",
            dc_side_links["repository_search_url"], use_container_width=True,
        )
        st.caption(
            "검색 버튼은 Google의 실제 검색 결과를 새 탭에서 엽니다. "
            "학교 자체 검색창으로 이동하는 버튼은 키워드를 자동 입력하지 않습니다. "
            "여기서 논문 목록/PDF를 수집하지는 않습니다."
        )

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

    st.divider()
    st.header("🤖 개인 AI 설정")
    user_ai_key = st.text_input(
        "본인의 OpenAI API 키", type="password",
        help="AI 요약에만 사용합니다. 프로젝트 파일이나 DB에 저장하지 않습니다.",
        placeholder="sk-...",
    )
    model = st.selectbox("AI 요약 모델", ["gpt-4.1-mini", "gpt-4o-mini"])
    if user_ai_key.strip():
        st.success("OpenAI API 키 입력 완료 (실제 사용 가능 여부는 요약 시 확인)")
    else:
        st.info("AI 요약을 사용하려면 위에 **본인의 OpenAI API 키**를 입력하세요. 논문 검색·통계는 키 없이 가능합니다.")

    st.divider()
    with st.expander("📝 과제 표지 정보", expanded=False):
        st.caption("보고서 표지에 사용할 개인 정보를 입력하세요.")
        school = st.text_input("학교명", key="cover_school", placeholder="OO대학교")
        department = st.text_input("대학원/전공", key="cover_department", placeholder="OO대학원 OO전공")
        course = st.text_input("교과목", key="cover_course", placeholder="디지털 포렌식 연구")
        student = st.text_input("제출자 이름", key="cover_student")
        professor = st.text_input("담당 교수 (선택)", key="cover_professor")
        submission_date = st.date_input("제출일", date.today(), key="cover_date")

    st.divider()
    st.caption("이용 순서: 왼쪽에서 검색 → 오른쪽에서 논문 확인·AI 요약·차트·다운로드")
    st.caption("공개 링크 서비스 · 로그인 없음 · 브라우저별 세션")

# 오른쪽 메인 영역: 검색/AI요약/통계/다운로드 결과만 배치합니다.
search_tab, ai_tab, trends_tab, riss_tab, sources_tab, submit_tab, help_tab = st.tabs(
    ["📚 검색 결과", "🤖 논문 AI 요약", "📊 연구 동향", "📖 RISS 서지통계",
     "📑 학회·보고서 검색", "📄 과제 보고서", "ℹ️ 이용 안내"]
)

with search_tab:
    st.subheader("1. 국회도서관 논문 검색 결과")
    st.caption("왼쪽 사이드바에서 연구 주제와 검색 조건을 입력하세요. · API: /9720000/searchservice/basic (XML)")
    notice = st.session_state.get("search_notice")
    if notice:
        level, message = notice
        if level == "success":
            st.success(message)
        elif level == "error":
            st.error(message)
        else:
            st.info(message)

    df = st.session_state.get("paper_df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        filtered = st.session_state.get("filtered_df", pd.DataFrame())
        m1, m2, m3 = st.columns(3)
        m1.metric("API 전체 검색 결과", f"{st.session_state.get('total_count', 0):,}건")
        m2.metric("현재 수집된 자료", f"{len(df):,}건")
        m3.metric("유형 필터 적용", f"{len(filtered):,}건")
        st.caption(
            f"실제 API 검색어: {st.session_state.get('search_used_keyword', '')} "
            f"(검색 대상: {st.session_state.get('search_field', '전체')}) · "
            "전체 검색 결과 수와 수집 건수는 다릅니다. 통계는 실제 수집한 자료만 대상으로 합니다."
        )
        title_count = int(df["자료명/저자사항"].astype(str).str.strip().ne("").sum())
        if title_count == 0:
            st.warning(
                "검색 결과는 수집했지만 논문 제목(자료명/저자사항) 값이 비어 있습니다. "
                "아래 'API 검색 진단'의 수집 필드명을 확인해 주세요."
            )
        else:
            st.caption(f"논문·자료명이 확인된 목록: {title_count:,}건 / 수집 {len(df):,}건")
        if not filtered.empty:
            # 국회도서관에서 확인된 관리번호를 공식 상세정보 주소로 연결합니다.
            # PDF 바로 다운로드 링크가 아니며 권한은 국회도서관 사이트에서 판단합니다.
            display_df = add_access_links(filtered)
            st.dataframe(
                display_df, use_container_width=True, hide_index=True,
                column_config={
                    "자료명/저자사항": st.column_config.TextColumn(
                        "논문·자료명 / 저자사항", width="large",
                    ),
                    "국회도서관 상세·원문 확인": st.column_config.LinkColumn(
                        "📖 상세·원문 확인", width="medium", display_text="국회도서관에서 열기 ↗",
                        help="국회도서관 상세정보에서 원문보기/다운로드 제공 여부를 확인합니다.",
                    ),
                    "공개본 검색": st.column_config.LinkColumn(
                        "🔎 공개본 검색", width="medium", display_text="Scholar에서 찾기 ↗",
                        help="Google Scholar 검색 페이지로 이동합니다. 원문이 반드시 제공되는 것은 아닙니다.",
                    ),
                },
            )
            st.caption(
                "📖 상세·원문 확인: 국회도서관 공식 상세페이지로 이동합니다. "
                "원문 열람·다운로드 가능 여부는 해당 자료의 저작권·이용조건에 따라 다릅니다. "
                "공개본 검색은 Google Scholar의 제목 검색이며 PDF 제공을 보장하지 않습니다."
            )
        else:
            st.info("현재 선택한 유형과 일치하는 자료가 없습니다. 필터를 해제하면 전체 자료가 표시됩니다.")
        st.info("논문 분석 시 오른쪽 '논문 AI 요약' 탭에서 초록 또는 PDF를 추가해야 합니다.")
    elif not admin_key:
        st.info("관리자가 DATA_GO_KR_API_KEY를 설정하면 검색할 수 있습니다. 직접 업로드 분석은 가능합니다.")
    elif st.session_state.get("search_attempts"):
        st.caption("검색 요청은 실행되었습니다. 시도한 단어별 건수를 아래에서 확인하세요.")
    else:
        st.info("왼쪽에서 검색어를 입력하고 '논문 검색 실행' 버튼을 눌러 주세요.")

    if st.session_state.get("search_attempts"):
        with st.expander("🔧 API 검색 진단 (검색어·건수·XML 태그만 표시, 인증키 제외)"):
            attempts_df = pd.DataFrame(
                st.session_state.search_attempts,
                columns=["요청 검색어", "API 전체 건수", "수집된 자료 수"],
            )
            st.dataframe(attempts_df, hide_index=True, use_container_width=True)
            xml_diag = st.session_state.get("xml_diagnostics", [])
            if isinstance(df, pd.DataFrame) and not df.empty:
                st.markdown("**수집된 자료 필드 확인 (필드명과 값이 있는 건수만 표시)**")
                st.dataframe(
                    pd.DataFrame([
                        {"필드명": col,
                         "값이 있는 자료 수": int(df[col].astype(str).str.strip().ne("").sum())}
                        for col in df.columns
                    ]),
                    hide_index=True, use_container_width=True,
                )
            if xml_diag:
                st.markdown("**API XML 응답 구조 (인증키·논문 내용 제외)**")
                st.dataframe(pd.DataFrame(xml_diag), hide_index=True, use_container_width=True)
                if st.session_state.get("total_count", 0) > 0 and attempts_df["수집된 자료 수"].sum() == 0:
                    st.warning(
                        "검색 건수는 있으나 목록이 누락되었습니다. 위 'XML 태그 빈도'와 "
                        "'XML 요소 경로'를 확인해 주시면 실제 응답 구조에 맞춰 수정할 수 있습니다."
                    )
            st.caption(
                f"검색 대상: {st.session_state.get('search_field', '전체')} · "
                "실제 검색 건수가 0인 경우에만 검색어를 바꿔 보세요."
            )

    # Prominent only for real API 0 results; available as collapsed expander otherwise.
    fallback_df = st.session_state.get("paper_df")
    collected_count = (len(fallback_df) if isinstance(fallback_df, pd.DataFrame) else 0)
    zero_results = no_results_from_nanet(
        st.session_state.get("total_count", 0),
        collected_count,
        st.session_state.get("search_attempts", []),
    )
    if zero_results:
        st.warning(
            "\uad6d\ud68c\ub3c4\uc11c\uad00 API \uac80\uc0c9\uc5d0\uc11c \uc870\ud68c\ub41c \uc790\ub8cc\uac00 0\uac74\uc785\ub2c8\ub2e4. "
            "\ubbf8\ub4f1\ub85d\uc774\ub77c\uace0 \ub2e8\uc815\ud558\uc9c0 \ub9c8\uc138\uc694. "
            "\uc544\ub798 \ub300\ud559\ubcc4 \ub17c\ubb38\u00b7\uc6d0\ubb38 \ucc3e\uae30 \ub9c1\ud06c\ub97c \ud655\uc778\ud574 \ubcf4\uc138\uc694."
        )
    with st.expander(
        "\U0001f3db \ub300\ud559\ubcc4 \ub17c\ubb38\u00b7\uc6d0\ubb38 \ucc3e\uae30",
        expanded=zero_results,
    ):
        dc_university = st.session_state.get("dcollection_university", universities()[0])
        dc_query = st.session_state.get("dcollection_query", st.session_state.get("search_keyword", ""))
        links = make_dcollection_destinations(dc_university, dc_query)
        st.caption(
            "\uc67c\ucabd\uc758 '\ub300\ud559\ubcc4 \ub17c\ubb38\u00b7\uc6d0\ubb38 \ucc3e\uae30'\uc5d0\uc11c "
            "\ub300\ud559\uacfc \uac80\uc0c9\uc5b4\ub97c \ubc14\uafbc \uc218 \uc788\uc2b5\ub2c8\ub2e4."
        )
        st.write(f"\uc120\ud0dd\ud55c \ub300\ud559: **{dc_university}**")
        st.caption("\uc7ac\uac80\uc0c9\ud560 \uc81c\ubaa9/\ud0a4\uc6cc\ub4dc:")
        if links["keyword"]:
            st.code(links["keyword"], language=None)
        else:
            st.caption("\uac80\uc0c9\uc5b4\ub97c \uc785\ub825\ud558\uc138\uc694.")
        a, b = st.columns(2)
        with a:
            st.link_button(
                "🔎 입력 키워드로 외부 검색 결과 열기 ↗",
                links["web_search_url"], use_container_width=True,
                disabled=not bool(links["keyword"]),
            )
        with b:
            st.link_button(
                "🏫 dCollection 자료검색 페이지 열기 ↗",
                links["repository_search_url"], use_container_width=True,
            )
        st.link_button(
            "🏫 전국 dCollection 참여대학 목록 보기",
            links["directory_url"], use_container_width=True,
        )
        st.caption(f"실제 외부 검색 조건: {links['search_query']}")
        st.info(
            "첫 버튼은 입력 키워드를 이용하여 Google에서 선택 대학 사이트만 검색합니다. "
            "둘째 버튼은 학교 dCollection 검색 화면만 열며, 키워드가 자동 입력되지 않습니다. "
            "Google에 색인되지 않은 논문은 이 방식으로 발견되지 않을 수 있습니다."
        )
        if dc_university == ALL_UNIVERSITIES:
            st.info("학교를 지정하고 싶다면 참여기관 목록에서 정확한 대학 dCollection을 찾아보세요.")
        st.caption(
            "외부 웹검색 결과를 앱 안으로 자동 수집하지 않습니다. "
            "원문 공개 여부는 개별 대학 저장소에서 확인하고, 확보한 PDF는 AI 요약 탭에 직접 업로드해 주세요."
        )

with ai_tab:
    st.subheader("2. 논문 선택 및 근거 자료 업로드")
    st.radio("분석할 자료 준비 방법", ["검색 목록에서 선택", "논문 직접 업로드"],
             horizontal=True, key="paper_mode")
    if st.session_state.paper_mode == "검색 목록에서 선택":
        select_df = st.session_state.get("filtered_df")
        if not isinstance(select_df, pd.DataFrame) or select_df.empty:
            st.warning("검색 탭에서 자료를 검색하고 유형을 선택하거나 '논문 직접 업로드'로 전환하세요.")
            st.session_state.selected_idx = None
        else:
            options = list(range(len(select_df)))
            # 자료유형 필터를 바꾸면 기존 선택 번호가 범위를 벗어날 수 있습니다.
            if st.session_state.get("selected_idx") not in options:
                st.session_state.pop("selected_idx", None)
            st.selectbox(
                "검색된 자료 중 한 편을 선택", options, key="selected_idx",
                format_func=lambda i: (
                    f"{str(select_df.iloc[i].get('발행년', ''))} | "
                    f"{str(select_df.iloc[i].get('자료명/저자사항', ''))[:115]}"
                ),
            )
    else:
        st.text_input("논문 제목 (필수)", key="manual_title", placeholder="예: 데이터베이스 포렌식 관련 연구")
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("저자·발행처 (알면 입력)", key="manual_publisher")
        with col2:
            st.text_input("발행연도 (알면 입력)", key="manual_year", max_chars=4)

    paper, origin = current_paper()
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
    st.markdown("#### ① 논문 PDF 업로드")
    st.caption("PDF를 올리면 내용을 자동 추출합니다. 초록을 다시 복사해 붙여넣을 필요는 없습니다.")
    uploaded = st.file_uploader("논문 PDF 파일 업로드 (최대 15MB)", type=["pdf"])
    pdf_text = ""
    pdf_count = None
    if uploaded is not None:
        try:
            pdf_text, pdf_count = extract_pdf_text(uploaded.getvalue())
            if len(pdf_text.strip()) < 80:
                st.warning("PDF에서 읽을 수 있는 글자가 부족합니다. 스캔 PDF는 OCR을 지원하지 않으므로 아래에서 초록을 직접 입력하세요.")
            else:
                st.success(f"PDF {pdf_count}페이지 중 최대 30페이지에서 텍스트 추출 완료 ({len(pdf_text):,}자)")
        except ValueError as exc:
            st.error(str(exc))

    # 텍스트 입력은 PDF가 없거나 스캔 PDF일 때의 보조 수단으로 접어 둡니다.
    usable_pdf_text = pdf_text if len(pdf_text.strip()) >= 80 else ""
    with st.expander("✍️ PDF가 없거나 글자를 읽지 못할 때: 초록 직접 입력 (선택)",
                     expanded=bool(uploaded is not None and not usable_pdf_text)):
        abstract = st.text_area(
            "초록 또는 본문 발췌 붙여넣기 (선택)", height=155,
            placeholder="PDF를 확보하지 못했을 때 원문에서 확인한 초록을 붙여넣으세요.",
            help="PDF 텍스트 추출에 성공했다면 이 입력란은 비워 두셔도 됩니다.",
        )
        st.caption("PDF의 텍스트가 확보되어 있다면 이 입력란은 비워 두어도 AI 요약이 가능합니다.")

    evidence = prepare_evidence(abstract=abstract, pdf_text=usable_pdf_text)
    evidence_id = hashlib.sha256(evidence.encode("utf-8")).hexdigest() if evidence else ""
    paper_id = "" if paper is None else str(paper.get("controlno") or paper.get("자료명/저자사항"))
    st.markdown("#### ② 논문 확인 후 AI 요약")
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
    if st.button("✨ 6개 항목 AI 요약 생성", type="primary", disabled=not enabled):
        try:
            with st.spinner("제공한 초록·PDF의 내용만을 바탕으로 요약하고 있습니다..."):
                summary = summarize_paper(user_ai_key, paper["자료명/저자사항"], evidence, model=model)
            st.session_state.summary_result = summary
            st.session_state.summary_context = (paper_id, evidence_id)
            st.session_state.summary_origin = "+".join(filter(None, [
                "입력 초록" if abstract.strip() else "", "사용자 PDF" if pdf_text.strip() else ""
            ]))
        except Exception as exc:
            # OpenAI 에러 메세지에 사용자 입력이 섞여 있을 수 있어 유형만 표시
            st.error(f"AI 요약 생성 실패 ({type(exc).__name__}). API 키, 결제 상태, 모델 권한, 본문을 확인하세요.")

    summary_current = st.session_state.get("summary_result")
    if summary_current and st.session_state.get("summary_context") == (paper_id, evidence_id):
        st.subheader("6개 항목 · 6줄 요약")
        for i, (key, value) in enumerate(summary_current.items(), 1):
            st.write(f"**{i}. {key}:** {value}")
        st.code(summary_lines(summary_current), language=None)
        st.download_button("요약 텍스트(.txt) 다운로드", summary_lines(summary_current).encode("utf-8-sig"),
                           file_name="논문_6개항목_요약.txt", mime="text/plain")
        st.caption("AI 생성 요약입니다. 원문과 대조해 잘못되거나 과도한 주장이 없는지 확인하세요.")
    else:
        st.info("현재 선택한 논문과 근거 자료에 대한 요약이 없습니다. AI 키·논문·초록/PDF를 준비해 요약을 생성하세요.")

with trends_tab:
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

with riss_tab:
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

with sources_tab:
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

with submit_tab:
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
    context_ok = bool(selected and st.session_state.get("summary_context") == (
        str(selected.get("controlno") or selected.get("자료명/저자사항")), evidence_id
    ))
    summary_to_export = st.session_state.get("summary_result") if context_ok else None

    with st.expander("📚 자료 종류별 참고문헌 표기 기준 (필요할 때만 열기)", expanded=False):
        st.caption("이번 과제에 지정한 형식입니다. 제출 기관의 별도 인용 규정이 있으면 그 규정을 우선하세요.")
        for kind, template in REFERENCE_TEMPLATES.items():
            st.markdown(f"**{kind}**")
            st.code(template, language=None)
        st.caption("학위논문 표기 예시: " + THESIS_EXAMPLE)

    report_citation = None
    if selected:
        st.caption("참고문헌은 선택한 논문 서지정보를 토대로 보고서에 포함됩니다. 제출 전에 원문과 대조하여 수정하세요.")
        with st.expander("📝 참고문헌 확인·수정 (과제 제출 전)", expanded=False):
            report_citation = edit_citation(selected)
    else:
        st.info("참고문헌을 작성하려면 먼저 검색 목록에서 논문을 선택하거나 직접 업로드하세요.")

    if not report_df.empty:
        try:
            excel_data = create_excel(report_df, keyword_for_report,
                                      summary_to_export, selected, data_origin=origin,
                                      citation_record=report_citation)
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
                )
                st.download_button(
                    "📄 표지 포함 PDF 과제 보고서 다운로드", pdf_data,
                    file_name="논문_AI분석_과제보고서.pdf", mime="application/pdf",
                    type="primary", use_container_width=True,
                )
            except Exception as exc:
                st.error(f"PDF 보고서 생성 실패: {type(exc).__name__}")
    else:
        st.info("PDF 보고서를 만들려면 '논문 AI 요약' 탭에서 선택한 논문의 6개 항목 요약을 생성하세요.")

with help_tab:
    st.info("대학 dCollection 및 학회·협회·보고서 검색은 입력 키워드로 외부 검색 결과를 여는 기능입니다. 국회도서관 API의 앱 내부 검색과 구분됩니다.")
    st.subheader("이용 및 과제 제출 안내")
    st.markdown("""
**화면 구성**
- 왼쪽 사이드바: 연구 주제 검색, 검색조건·자료유형 필터, 개인 AI 키, 과제 표지 입력
- 오른쪽 메인: 검색 결과, AI 논문 요약, 연구 동향, RISS 서지 구축 통계, PDF·Excel 다운로드

**기능 구성**
- 국회도서관 API 논문 검색: 별도 비용 없는 공공데이터 API, 관리자 키 사용
- 자료 통계: 검색 결과 내 발행연도와 유형의 빈도 분석
- AI 요약: PDF를 우선 업로드하고 텍스트를 자동 추출하여 6개 항목 요약. PDF가 없거나 스캔본일 때만 접이식 초록 입력 사용
- RISS 종합목록: 기관코드·조사년도별 국내/국외 서지 구축 현황 및 Excel 다운로드 (논문 검색 기능 아님)
- 과제 제출: 학교·전공·이름·과목 표지, PDF 보고서, Excel 통계 및 자료유형별 참고문헌 표기

**주의 사항**
- 원우 개인 OpenAI API 키는 암호형 입력창으로 받으며 파일과 데이터베이스에 저장하지 않습니다. 브라우저 세션이 유지되는 동안 Streamlit 서버가 처리할 수 있습니다. 사용 후 창을 닫으세요.
- 업로드한 PDF 텍스트는 OpenAI API에 전달됩니다. 저작권·개인정보·연구윤리 및 과목별 AI 활용 기준을 확인하세요.
- 스캔본 PDF는 OCR 기능이 없어 초록을 복사하여 넣어야 합니다. PDF 전체가 아니라 최대 30페이지의 일부 발췌 텍스트만 AI에 전달합니다.
- API는 서지 목록 중심이며 논문 초록·본문을 자동으로 제공한다고 보장할 수 없습니다.
- 참고문헌 편집과 자료별 표기 기준은 '과제 보고서' 탭에서 펼쳐 확인할 수 있습니다. 학술지 논문·학위논문·기관 연구보고서의 과제용 형식 중 선택합니다. 원문에 없는 서지정보는 '미확인'으로 표시하므로 제출 전에 반드시 검증하고 수정해야 합니다.
- 공개 접속 주소를 아는 누구나 이용할 수 있습니다. 회원별 사용기록·개인 계정 기능은 구현하지 않았습니다.
""")
    st.markdown(f"**데이터 출처:** [{API_NAME}]({SOURCE_URL}) · [{RISS_NAME}]({RISS_SOURCE_URL})")
    st.caption("국회도서관 API 요청형식: /basic?serviceKey=...&pageno=1&displaylines=10&search=전체,키워드")
