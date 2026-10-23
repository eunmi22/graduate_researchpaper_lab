"""P0-only search UI. The existing research/AI/reporting screens remain unchanged."""
from __future__ import annotations
import json
import time
import pandas as pd
import streamlit as st
from paperlab import search_papers, PaperAPIError, add_access_links
from nanet_metadata import CATEGORY_ORDER, UNKNOWN, clean_text, control_number
from nanet_search_flow import (
    search_literature_basic, partition_catalog_records, merge_catalog_pages,
    compare_web_reference,
)
from nanet_enrich import enrich_catalog
from citation_styles import suggested_citation, format_reference
from catalog_identity import (
    identity_rows, identity_table, filter_identities, ROWKEY,
    CONTROL, TITLE, AUTHOR, YEAR, PUBLISHER, KIND, REASON, LINK, REFERENCE,
)


UI_BUILD = "2.3.5-P0-ID"
STATE_VERSION = "p0-2-id"


def _initialize():
    if st.session_state.get("p0_state_version") == STATE_VERSION:
        return
    # Re-normalize old in-session search records instead of discarding them.
    catalog = st.session_state.get("catalog_df", pd.DataFrame())
    if not isinstance(catalog, pd.DataFrame) or catalog.empty:
        older = [st.session_state.get(k) for k in ("paper_df", "unverified_df", "books_df")]
        older = [f for f in older if isinstance(f, pd.DataFrame) and not f.empty]
        catalog = pd.concat(older, ignore_index=True) if older else pd.DataFrame()
    _set_catalog(catalog)
    if catalog.empty:
        for key in ("search_notice", "search_attempts", "xml_diagnostics", "selected_idx", "saved_selected_idx"):
            st.session_state.pop(key, None)
        st.session_state.total_count = 0
    else:
        st.session_state.p0_migrated_rows = len(catalog)
    # Preserve research notes, PDF evidence, personal settings and pagination state.
    st.session_state.p0_state_version = STATE_VERSION


def _set_catalog(frame: pd.DataFrame):
    old = st.session_state.get("filtered_df", pd.DataFrame())
    selected = st.session_state.get("selected_idx", st.session_state.get("saved_selected_idx"))
    ident = ""
    if isinstance(old, pd.DataFrame) and isinstance(selected, int) and 0 <= selected < len(old):
        ident = control_number(old.iloc[selected].to_dict())
    papers, unknown, books, ordered = partition_catalog_records(frame)
    st.session_state.catalog_df = ordered
    st.session_state.catalog_filtered_df = ordered
    st.session_state.paper_df = papers
    st.session_state.filtered_df = papers.copy()
    st.session_state.unverified_df = unknown
    st.session_state.books_df = books
    if ident and "controlno" in papers:
        matches = papers.index[papers["controlno"].eq(ident)].tolist()
        if matches:
            st.session_state.selected_idx = int(matches[0])
            st.session_state.saved_selected_idx = int(matches[0])
        else:
            st.session_state.pop("selected_idx", None)
            st.session_state.pop("saved_selected_idx", None)


def _recent_calls():
    now = time.monotonic()
    return now, [t for t in st.session_state.get("search_events", []) if now - t < 3600]


def _enrich(frame: pd.DataFrame):
    if not st.session_state.get("p0_auto_enrich", True):
        return frame
    cache = st.session_state.setdefault("p0_metadata_cache", {})
    result = enrich_catalog(frame, cache=cache, limit=5)
    st.session_state.p0_enrichment = {
        "요청 건수": result.attempted, "보완 건수": result.changed,
        "남은 확인 필요 자료": result.remaining, "안내": result.errors,
    }
    return result.data


def _clear_search():
    _set_catalog(pd.DataFrame())
    for key in ("selected_idx", "saved_selected_idx", "summary_result", "summary_context"):
        st.session_state.pop(key, None)
    st.session_state.total_count = 0
    st.session_state.search_raw_count = 0
    st.session_state.search_used_keyword = ""
    st.session_state.search_next_page = 1
    st.session_state.search_attempts = []
    st.session_state.search_errors = []
    st.session_state.xml_diagnostics = []
    st.session_state.search_exhausted = False
    st.session_state.search_stalled = False
    st.session_state.p0_enrichment = {}
    st.session_state.pop("search_notice", None)


def render_search_controls(admin_key: str):
    _initialize()
    st.subheader("🔎 국회도서관 자료 검색")
    st.caption("기존 /basic API 유지 · 자료유형 자동분류 · 검색에는 개인 OpenAI 키가 필요하지 않습니다.")
    if not admin_key:
        st.warning("관리자 설정의 DATA_GO_KR_API_KEY가 필요합니다. PDF 직접 분석은 02 메뉴에서 이용하세요.")
    with st.form("search_form", clear_on_submit=False):
        keyword = st.text_input("검색할 논문 주제", value=st.session_state.get("search_keyword", "데이터베이스 포렌식"))
        c1, c2 = st.columns(2)
        with c1:
            pages = st.selectbox("검색 페이지 수", [1, 2, 3, 4, 5], index=1)
        with c2:
            per_page = st.selectbox("페이지당 검색 건수", [5, 10, 15, 20], index=3)
        with st.expander("검색 방식·서지정보 보완 설정", expanded=False):
            search_field = st.selectbox("검색 대상", ["전체", "기본검색", "자료명", "키워드", "저자", "발행자"],
                help="공식 명세의 검색항목입니다. 웹사이트의 '기본검색'과 대조할 때 같은 항목으로 맞추세요. 순위의 완전 일치는 보장하지 않습니다.")
            automatic_retry = st.checkbox("API 결과가 실제 0건일 때만 핵심 단어로 다시 검색", value=False)
            auto_enrich = st.checkbox("누락 제목·유형을 공개 상세정보로 자동 보완 (검색당 최대 5건)", value=True)
            st.caption("자료유형을 선택할 필요가 없습니다. API 자료유형과 관리번호를 먼저 판별하고, 필요한 자료만 공식 상세정보를 확인합니다.")
        submitted = st.form_submit_button("🔎 논문 검색 실행", type="primary", disabled=not bool(admin_key), use_container_width=True)
    if submitted:
        _clear_search()
        st.session_state.p0_auto_enrich = auto_enrich
        st.session_state.search_keyword = keyword.strip()
        st.session_state.search_used_keyword = keyword.strip()
        st.session_state.search_field = search_field
        st.session_state.search_per_page = per_page
        now, recent = _recent_calls()
        # A local protective budget, explicitly not the provider's account quota.
        remaining = 60 - len(recent)
        if remaining < pages * 2:
            st.session_state.search_notice = ("warning", "앱 세션 보호 한도(최대 60요청/시간)가 부족합니다. 페이지 수를 줄여 주세요.")
        else:
            diagnostics = []
            try:
                with st.spinner("API 목록을 읽고 제목과 자료유형을 정리합니다..."):
                    outcome = search_literature_basic(admin_key, keyword, pages=pages,
                        per_page=per_page, search_field=search_field, automatic_retry=automatic_retry,
                        diagnostics=diagnostics, max_page_calls=remaining // 2)
                    data = _enrich(outcome.catalog)
                _set_catalog(data)
                st.session_state.search_events = recent + [now] * outcome.page_calls_budgeted
                st.session_state.search_attempts = outcome.attempts
                st.session_state.search_errors = outcome.errors
                st.session_state.xml_diagnostics = diagnostics
                st.session_state.total_count = outcome.total
                st.session_state.search_raw_count = outcome.raw_rows
                st.session_state.search_used_keyword = outcome.used_keyword
                st.session_state.search_next_page = outcome.next_page
                st.session_state.search_exhausted = outcome.exhausted
                st.session_state.search_stalled = outcome.stalled
                if outcome.errors:
                    st.session_state.search_notice = ("warning", "일부 요청을 완료하지 못했습니다. 성공한 자료는 보존했으며, 진단에서 실패 페이지를 확인할 수 있습니다.")
                elif data.empty:
                    st.session_state.search_notice = ("info", "해당 조건의 수집 결과가 없습니다. API 전체 건수와 진단을 확인하세요.")
                else:
                    st.session_state.search_notice = ("success", f"현재 {len(data):,}건 수집·자동분류 완료. API 전체 검색 건수는 {outcome.total:,}건입니다.")
            except (PaperAPIError, ValueError) as exc:
                st.session_state.search_events = recent + [now] * sum(int(d.get("요청 횟수", 1)) for d in diagnostics)
                safe = str(exc).replace(str(admin_key), "[인증키 제외]")
                st.session_state.search_errors = [safe]
                st.session_state.xml_diagnostics = diagnostics
                st.session_state.search_notice = ("error", safe)
    catalog = st.session_state.get("catalog_df", pd.DataFrame())
    total = int(st.session_state.get("total_count", 0))
    next_page = int(st.session_state.get("search_next_page", 1))
    page_size = int(st.session_state.get("search_per_page", 20))
    exhausted = bool(st.session_state.get("search_exhausted", False))
    stalled = bool(st.session_state.get("search_stalled", False))
    if not catalog.empty and not exhausted and not stalled:
        batch = min(5, max(1, (total + page_size - 1) // page_size - next_page + 1))
        if st.button(f"📥 다음 검색 페이지 가져오기 ({next_page}페이지부터 최대 {batch}페이지)", key="p0_load_more", disabled=not bool(admin_key)):
            now, recent = _recent_calls()
            batch = min(batch, max(0, (60-len(recent)) // 2))
            if batch < 1:
                st.warning("앱 세션 검색 보호 한도에 도달했습니다.")
            else:
                diagnostics = []
                try:
                    with st.spinner("같은 검색 조건으로 다음 페이지를 수집합니다..."):
                        new_total, extra = search_papers(admin_key,
                            st.session_state.get("search_used_keyword", ""), pages=batch,
                            per_page=page_size, search_field=st.session_state.get("search_field", "전체"),
                            start_page=next_page, diagnostics=diagnostics)
                        status = extra.attrs.copy()
                        extra = _enrich(extra)
                        _, _, _, merged = merge_catalog_pages(catalog, extra)
                    if len(merged) == len(catalog) and not extra.empty:
                        status["stalled"] = True
                        status.setdefault("errors", []).append("추가 페이지가 이미 수집한 관리번호만 반환하여 자동 반복을 멈췄습니다.")
                    _set_catalog(merged)
                    st.session_state.total_count = new_total
                    st.session_state.search_next_page = status.get("next_page", next_page)
                    st.session_state.search_exhausted = status.get("exhausted", False)
                    st.session_state.search_stalled = status.get("stalled", False)
                    st.session_state.search_errors = status.get("errors", [])
                    st.session_state.xml_diagnostics += diagnostics
                    st.session_state.search_events = recent + [now] * status.get("request_count", batch)
                    st.session_state.search_notice = ("warning" if status.get("errors") else "success",
                        f"중복 제거 후 {len(merged):,}건을 표시합니다. 추가 수집 {len(merged)-len(catalog):,}건.")
                    st.rerun()
                except (PaperAPIError, ValueError) as exc:
                    st.session_state.search_events = recent + [now] * sum(int(d.get("요청 횟수", 1)) for d in diagnostics)
                    st.session_state.search_errors = [str(exc).replace(str(admin_key), "[인증키 제외]")]
                    st.session_state.xml_diagnostics += diagnostics
                    st.warning("추가 페이지 요청 실패: 기존 결과와 실패 페이지 위치를 유지했습니다. 다시 시도할 수 있습니다.")
    if stalled:
        st.warning("목록 누락 또는 반복 페이지를 감지해 추가 자동 요청을 멈췄습니다. 아래 진단을 확인하세요.")


def _go_reading(control: str):
    frame = st.session_state.get("paper_df", pd.DataFrame())
    if frame.empty or "controlno" not in frame:
        return
    matches = frame.index[frame["controlno"].eq(control)].tolist()
    if not matches:
        return
    st.session_state.filtered_df = frame.copy()
    st.session_state.selected_idx = int(matches[0])
    st.session_state.saved_selected_idx = int(matches[0])
    st.session_state.paper_mode = "검색 목록에서 선택"
    st.session_state.saved_paper_mode = "검색 목록에서 선택"
    st.session_state.v23_main_menu = "02. 논문 읽기"


def _show_group(frame: pd.DataFrame, heading: str):
    st.markdown(f"#### {heading} ({len(frame):,}건)")
    if frame.empty:
        st.caption("현재 수집한 페이지에는 이 유형의 자료가 없습니다.")
        return
    # Reuse links on imported old results without creating duplicate columns.
    frame = frame.drop(columns=["국회도서관 상세·원문 확인", "공개본 검색"], errors="ignore")
    display = add_access_links(frame)
    display = identity_table(display)
    st.dataframe(display, hide_index=True, use_container_width=True,
        column_config={
            CONTROL: st.column_config.TextColumn(CONTROL, width="medium"),
            TITLE: st.column_config.TextColumn("제목 / 저자사항", width="large"),
            AUTHOR: st.column_config.TextColumn(AUTHOR, width="medium"),
            REASON: st.column_config.TextColumn(REASON, width="large"),
            REFERENCE: st.column_config.TextColumn(REFERENCE, width="large"),
            LINK: st.column_config.LinkColumn(LINK, display_text="국회도서관에서 열기 ↗"),
        })


def _choose_identity(items: list[dict], *, widget_key: str, memory_key: str, label: str):
    """Use a stable ID as the value, not a possibly duplicated title or row number."""
    mapping = {item[ROWKEY]: item for item in items}
    options = list(mapping)
    if not options:
        return None
    current = st.session_state.get(widget_key, st.session_state.get(memory_key))
    if current not in mapping:
        remembered = st.session_state.get(memory_key)
        current = remembered if remembered in mapping else options[0]
    st.session_state[widget_key] = current
    chosen = st.selectbox(label, options, key=widget_key,
        format_func=lambda value: mapping[value]["label"],
        help="관리번호 | 제목 | 저자 | 발행연도로 표시합니다. 같은 제목도 관리번호로 구분합니다.")
    st.session_state[memory_key] = chosen
    return mapping[chosen]


def _inspect_pending(frame: pd.DataFrame):
    st.caption("자동분류 근거가 부족하거나 충돌한 자료만 보여줍니다. 수동 유형 선택·확인 체크는 필요하지 않습니다.")
    query = st.text_input("목록에서 찾기 (관리번호·제목·저자·발행처)", key="p0_pending_query")
    items = filter_identities(identity_rows(frame), query)
    st.caption(f"미확인 자료 {len(frame):,}건 중 현재 표시 {len(items):,}건")
    if not items:
        st.info("입력한 관리번호나 제목과 일치하는 자료가 없습니다.")
        return
    subset = pd.DataFrame([item["record"] for item in items])
    _show_group(subset, "4. 자료유형 미확인")
    selected = _choose_identity(items, widget_key="p0_pending_select", memory_key="p0_pending_selected",
        label="확인할 자료 선택 (관리번호·제목·저자·연도)")
    if selected is None:
        return
    st.markdown("**선택한 자료의 전체 정보**")
    for field in (CONTROL, TITLE, AUTHOR, YEAR, PUBLISHER, KIND, REASON):
        st.write(f"{field}: {selected[field]}")
    st.markdown("**정식 참고문헌**")
    st.write(selected[REFERENCE])
    if selected[LINK]:
        st.link_button("선택한 자료의 공식 상세정보 열기", selected[LINK])
        if st.button("선택 자료 공개 서지정보 자동 보완", key="p0_pending_enrich"):
            cache = st.session_state.setdefault("p0_metadata_cache", {})
            result = enrich_catalog(pd.DataFrame([selected["record"]]), cache=cache, limit=1)
            catalog = st.session_state.get("catalog_df", pd.DataFrame())
            _, _, _, merged = merge_catalog_pages(catalog, result.data)
            _set_catalog(merged)
            st.session_state.p0_identity_notice = (
                f"선택 자료 자동 보완: 요청 {result.attempted}건, 변경 {result.changed}건. "
                + (" / ".join(result.errors) if result.errors else "확인된 공개 정보만 반영했습니다.")
            )
            st.rerun()
    else:
        st.info("공식 관리번호가 확인되지 않아 다른 자료로 잘못 연결하지 않도록 상세링크를 만들지 않았습니다.")


def render_search_results(admin_key: str):
    _initialize()
    st.caption(f"검색 화면 빌드: {UI_BUILD} | 관리번호·제목 함께 표시 | 수동 분류 폼 없음")
    if st.session_state.get("p0_identity_notice"):
        st.info(st.session_state.pop("p0_identity_notice"))
    st.subheader("📋 검색 결과 — 학위논문 → 학술기사 → 도서자료")
    notice = st.session_state.get("search_notice")
    if notice:
        getattr(st, notice[0])(notice[1])
    catalog = st.session_state.get("catalog_df", pd.DataFrame())
    total = int(st.session_state.get("total_count", 0))
    classes = catalog.get("자료분류", pd.Series(dtype=str))
    searched = bool(st.session_state.get("search_attempts") or st.session_state.get("xml_diagnostics") or st.session_state.get("search_errors"))
    if searched or not catalog.empty:
        m = st.columns(6)
        m[0].metric("API 전체 검색 건수", f"{total:,}건")
        m[1].metric("현재 수집·중복제거", f"{len(catalog):,}건")
        for i, label in enumerate(CATEGORY_ORDER, 2):
            m[i].metric(label, f"{int(classes.eq(label).sum()):,}건")
    if catalog.empty:
        if searched:
            st.info("이번 검색에서 표시할 목록을 확보하지 못했습니다. API 전체 건수와 아래 검색 진단을 확인하세요.")
        else:
            st.info("검색어를 입력하고 '논문 검색 실행'을 눌러 주세요.")
    else:
        st.caption(f"실제 검색어: {st.session_state.get('search_used_keyword', '')} · 검색 대상: {st.session_state.get('search_field', '전체')} · 유형별 건수는 현재 수집 자료 기준입니다.")
        st.caption("각 유형 안에서는 API가 반환한 순서를 유지합니다. 이 순서가 공식 웹사이트의 '정확도' 순위와 같다고 확인된 것은 아닙니다.")
        for category, heading in (("학위논문", "🎓 1. 학위논문"), ("학술기사", "📄 2. 학술기사"), ("도서자료", "📚 3. 도서자료")):
            _show_group(catalog[classes.eq(category)], heading)
        pending = catalog[classes.eq(UNKNOWN)]
        if not pending.empty:
            with st.expander(f"⚠ 자료유형 미확인 목록 ({len(pending)}건) — 근거 부족·충돌만 표시", expanded=False):
                _inspect_pending(pending)
        papers = st.session_state.get("paper_df", pd.DataFrame())
        eligible = papers[papers["controlno"].map(bool)] if not papers.empty else papers
        if not eligible.empty:
            item = _choose_identity(identity_rows(eligible), widget_key="p0_read_control", memory_key="p0_read_selected",
                label="읽을 논문 선택 (관리번호·제목·저자·연도)")
            if item is not None:
                st.write(f"선택 논문: {item[TITLE]}")
                selected = control_number(item["record"])
                st.button("📖 선택 논문을 02. 논문 읽기로 보내기", on_click=_go_reading, args=(selected,), key="p0_to_reading")
        st.caption("학술기사 분류는 동료심사 여부를 보증하지 않습니다. 도서자료는 논문 선택 목록에 전달하지 않습니다.")
        enrichment = st.session_state.get("p0_enrichment", {})
        if enrichment:
            st.caption(f"공개 상세정보 보완: 이번 요청 {enrichment.get('요청 건수', 0)}건 / 변경 {enrichment.get('보완 건수', 0)}건. 로그인·차단·비공개 원문을 우회하지 않습니다.")
            for message in enrichment.get("안내", [])[:3]:
                st.caption(message)
            if enrichment.get("남은 확인 필요 자료", 0):
                if st.button("누락 서지정보 추가 자동 보완 (최대 5건)", key="p0_enrich_more"):
                    st.session_state.p0_auto_enrich = True
                    _set_catalog(_enrich(catalog))
                    st.rerun()
    if st.session_state.get("xml_diagnostics") or st.session_state.get("search_errors") or not catalog.empty:
        with st.expander("🔧 API 검색 진단 · 공식 웹 결과 비교", expanded=False):
            st.caption("261건은 과거 화면의 값이며 고정하지 않습니다. 같은 검색어·검색 범위·조회 시점으로 대조하세요.")
            for error in st.session_state.get("search_errors", []):
                st.warning(error)
            diagnostics = st.session_state.get("xml_diagnostics", [])
            if diagnostics:
                st.dataframe(pd.DataFrame(diagnostics), hide_index=True, use_container_width=True)
            if not catalog.empty:
                original = catalog.copy()
                if "API순번" in original:
                    original = original.assign(_order=pd.to_numeric(original["API순번"], errors="coerce")).sort_values("_order", kind="stable").drop(columns="_order")
                st.markdown("**API 응답 원순서 (유형별 정렬 이전)**")
                audit_cols = [c for c in ("API순번", "API페이지", "controlno", "자료명/저자사항", "DB", "상세자료유형", "자료분류", "분류출처", "분류상태") if c in original]
                st.dataframe(original[audit_cols], hide_index=True, use_container_width=True)
                st.markdown("**선택: 공식 웹사이트에서 확인한 표본 비교**")
                sample = st.text_area("관리번호 | 제목 | 자료유형 (한 줄에 한 자료, 선택 사항)", key="p0_web_sample",
                    placeholder="공식 웹 화면에서 확인한 자료만 입력합니다. 전체 261건을 대조했다고 간주하지 않습니다.")
                if sample.strip():
                    records = []
                    for line in sample[:50_000].splitlines()[:500]:
                        fields = line.split("|", 2)
                        records.append({"controlno": fields[0].strip(), "title": fields[1].strip() if len(fields)>1 else "",
                                        "category": fields[2].strip() if len(fields)>2 else ""})
                    comparison, metrics = compare_web_reference(catalog, records)
                    st.write(metrics)
                    st.dataframe(comparison, hide_index=True, use_container_width=True)
                    st.caption("표본 포함률은 입력한 관리번호 중 현재 수집 목록에 있는 비율입니다. 전체 결과 동일성이나 검색 재현율이 아닙니다.")
            report = {"version": STATE_VERSION, "query": st.session_state.get("search_used_keyword", ""),
                "field": st.session_state.get("search_field", ""), "api_total": st.session_state.get("total_count", 0),
                "collected": len(catalog), "pages": diagnostics, "errors": st.session_state.get("search_errors", []),
                "ui_build": UI_BUILD,
                "record_identification": identity_table(catalog).fillna("").to_dict("records")}
            st.caption("진단 JSON에는 관리번호·제목·분류 근거가 포함됩니다. 민감한 검색어나 자료가 있으면 공유 전 확인하세요.")
            st.download_button("키를 제외한 검색 진단 JSON", json.dumps(report, ensure_ascii=False, indent=2, default=str),
                               file_name="search_diag.json", mime="application/json", key="p0_diag_download")
