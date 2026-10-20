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
    make_reference, prepare_evidence, search_candidates, search_papers, select_type,
    summarize_paper, summary_lines,
)
from reporting import create_excel, create_pdf_report

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


st.title("🎓 대학원 AI 논문 연구 도우미")
st.caption("논문 검색 → 연구 동향 분석 → 근거 기반 AI 6줄 요약 → 과제 제출 보고서")

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
        if len(recent) >= 12:
            st.session_state.search_notice = (
                "error", "이 브라우저 세션은 1시간에 최대 12회 검색할 수 있습니다."
            )
        else:
            try:
                candidates = search_candidates(keyword, automatic_retry)
                attempts = []
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
                        )
                        attempts.append((candidate, total, len(result_df)))
                        final_total, final_df, used_keyword = total, result_df, candidate
                        if not result_df.empty or total > 0:
                            break
                st.session_state.search_events = recent + [now] * len(attempts)
                st.session_state.search_attempts = attempts
                st.session_state.paper_df = final_df
                st.session_state.search_keyword = keyword.strip()
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
                        f"API에서는 전체 {final_total:,}건이라고 응답했으나, 자료 목록(record)이 "
                        "파싱되지 않았습니다. 제공기관의 XML 응답 구조 확인이 필요합니다.",
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

    # 검색과 무관하게 여러 탭이 같은 필터링 결과를 사용합니다.
    df = st.session_state.get("paper_df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        available_types = sorted(str(t) for t in df["DB"].unique() if str(t).strip())
        chosen_types = st.multiselect(
            "검색 자료유형 필터", available_types, default=available_types,
            key="sidebar_types", help="책이 포함될 수 있으므로 학위논문/학술기사를 골라 보세요."
        )
        filtered = select_type(df, chosen_types) if chosen_types else df.iloc[0:0].copy()
        st.session_state.filtered_df = filtered
        st.caption(f"선택된 자료: {len(filtered):,}건")
    else:
        st.session_state.filtered_df = pd.DataFrame()

    st.divider()
    st.header("🤖 개인 AI 설정")
    user_ai_key = st.text_input(
        "본인의 OpenAI API 키", type="password",
        help="AI 요약에만 사용합니다. 프로젝트 파일이나 DB에 저장하지 않습니다.",
        placeholder="sk-...",
    )
    model = st.selectbox("AI 요약 모델", ["gpt-4.1-mini", "gpt-4o-mini"])
    st.caption("논문 검색·통계는 OpenAI 키 없이도 이용할 수 있습니다.")

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
search_tab, ai_tab, trends_tab, submit_tab, help_tab = st.tabs(
    ["📚 검색 결과", "🤖 논문 AI 요약", "📊 연구 동향", "📄 과제 보고서", "ℹ️ 이용 안내"]
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
        if not filtered.empty:
            st.dataframe(filtered, use_container_width=True, hide_index=True)
        else:
            st.info("왼쪽 자료유형 필터에서 하나 이상 선택하세요.")
        st.info("논문 분석 시 오른쪽 '논문 AI 요약' 탭에서 초록 또는 PDF를 추가해야 합니다.")
    elif not admin_key:
        st.info("관리자가 DATA_GO_KR_API_KEY를 설정하면 검색할 수 있습니다. 직접 업로드 분석은 가능합니다.")
    elif st.session_state.get("search_attempts"):
        st.caption("검색 요청은 실행되었습니다. 시도한 단어별 건수를 아래에서 확인하세요.")
    else:
        st.info("왼쪽에서 검색어를 입력하고 '논문 검색 실행' 버튼을 눌러 주세요.")

    if st.session_state.get("search_attempts"):
        with st.expander("🔧 API 검색 진단 (검색어·건수만 표시, 인증키 제외)"):
            attempts_df = pd.DataFrame(
                st.session_state.search_attempts,
                columns=["요청 검색어", "API 전체 건수", "수집된 자료 수"],
            )
            st.dataframe(attempts_df, hide_index=True, use_container_width=True)
            st.caption(
                f"검색 대상: {st.session_state.get('search_field', '전체')} · "
                "실제 결과가 0건이면 다른 검색어 또는 검색 대상을 사용하세요."
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
        st.markdown(f"**선택 논문:** {paper.get('자료명/저자사항', '')}")
        with st.expander("자동 생성 참고문헌(임시) 확인"):
            st.write(make_reference(paper))
            st.caption("원본 서지정보에 없는 DOI/쪽수/학술지 정보는 생성하지 않습니다.")

    abstract = st.text_area("초록 또는 본문 발췌 붙여넣기", height=155,
                            placeholder="원문에서 확인된 초록을 붙여넣어 주세요. 논문 제목만으로는 분석하지 않습니다.")
    uploaded = st.file_uploader("논문 PDF 파일 업로드 (선택, 최대 15MB)", type=["pdf"])
    pdf_text = ""
    pdf_count = None
    if uploaded is not None:
        try:
            pdf_text, pdf_count = extract_pdf_text(uploaded.getvalue())
            if len(pdf_text.strip()) < 80:
                st.warning("PDF에서 읽을 수 있는 텍스트가 부족합니다. 스캔 PDF는 OCR을 지원하지 않으므로 초록을 직접 입력하세요.")
            else:
                st.success(f"PDF {pdf_count}페이지 중 최대 30페이지에서 텍스트 추출 완료 ({len(pdf_text):,}자)")
        except ValueError as exc:
            st.error(str(exc))

    evidence = prepare_evidence(abstract=abstract, pdf_text=pdf_text)
    evidence_id = hashlib.sha256(evidence.encode("utf-8")).hexdigest() if evidence else ""
    paper_id = "" if paper is None else str(paper.get("controlno") or paper.get("자료명/저자사항"))
    confirmed = st.checkbox("선택한 논문과 입력한 초록/PDF가 같은 논문임을 확인했습니다.")
    enabled = bool(paper and confirmed and len(evidence.strip()) >= 40 and user_ai_key.strip())
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

with submit_tab:
    st.subheader("4. 과제 보고서 다운로드")
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

    if not report_df.empty:
        try:
            excel_data = create_excel(report_df, keyword_for_report,
                                      summary_to_export, selected, data_origin=origin)
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
                    data_origin=origin,
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
    st.subheader("이용 및 과제 제출 안내")
    st.markdown("""
**화면 구성**
- 왼쪽 사이드바: 연구 주제 검색, 검색조건·자료유형 필터, 개인 AI 키, 과제 표지 입력
- 오른쪽 메인: 검색 결과, AI 논문 요약, 연구 동향 차트, PDF·Excel 다운로드

**기능 구성**
- 국회도서관 API 논문 검색: 별도 비용 없는 공공데이터 API, 관리자 키 사용
- 자료 통계: 검색 결과 내 발행연도와 유형의 빈도 분석
- AI 요약: 사용자가 붙여넣은 초록 또는 직접 업로드한 PDF 텍스트를 근거로 6개 항목 요약
- 과제 제출: 학교·전공·이름·과목 표지, PDF 보고서, Excel 통계 및 참고문헌

**주의 사항**
- 원우 개인 OpenAI API 키는 암호형 입력창으로 받으며 파일과 데이터베이스에 저장하지 않습니다. 브라우저 세션이 유지되는 동안 Streamlit 서버가 처리할 수 있습니다. 사용 후 창을 닫으세요.
- 업로드한 PDF 텍스트는 OpenAI API에 전달됩니다. 저작권·개인정보·연구윤리 및 과목별 AI 활용 기준을 확인하세요.
- 스캔본 PDF는 OCR 기능이 없어 초록을 복사하여 넣어야 합니다. PDF 전체가 아니라 최대 30페이지의 일부 발췌 텍스트만 AI에 전달합니다.
- API는 서지 목록 중심이며 논문 초록·본문을 자동으로 제공한다고 보장할 수 없습니다.
- 표에 표시된 논문 제목/저자사항은 결합 필드이고 참고문헌은 임시 표기입니다. 정식 참고문헌 양식은 원문 확인 후 수정해야 합니다.
- 공개 접속 주소를 아는 누구나 이용할 수 있습니다. 회원별 사용기록·개인 계정 기능은 구현하지 않았습니다.
""")
    st.markdown(f"**데이터 출처:** [{API_NAME}]({SOURCE_URL})")
    st.caption("국회도서관 API 요청형식: /basic?serviceKey=...&pageno=1&displaylines=10&search=전체,키워드")
