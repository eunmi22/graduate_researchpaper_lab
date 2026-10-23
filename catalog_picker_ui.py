"""자료 찾기 전용 단계 안내와 대분류→세부자료 선택 화면.

API 재호출 없이 현재 수집 자료를 사용한다. 개인 자료의 전역 캐시는 없다.
Streamlit 객체는 인수로 받아 순수 상태/컨트롤러 테스트를 지원한다.
"""
from __future__ import annotations

from html import escape
from collections.abc import Callable
import pandas as pd
from catalog_identity import (
    identity_rows, ROWKEY, TITLE, AUTHOR, YEAR, CONTROL, PUBLISHER, KIND, LINK, REFERENCE, REASON,
)
from nanet_metadata import THESIS, ARTICLE, BOOK, UNKNOWN
from catalog_picker import (
    CATEGORIES, ICONS, CATEGORY_WIDGET, RECORD_WIDGET,
    prepare_category, prepare_record, remember_record, category_label, record_label, reading_target,
)

PICKER_CSS = """
<style>
.paper-flow {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:8px 0 20px;}
.paper-flow-step {border:1px solid #c9d8eb;border-radius:12px;padding:14px 16px;background:#f5f8fe;color:#17365d;}
.paper-flow-step strong {display:block;font-size:1.05rem;margin-bottom:5px;}
.paper-flow-step span {font-size:.9rem;line-height:1.5;color:#3d5572;}
.paper-flow-no {display:inline-block!important;background:#244e91;color:#fff!important;border-radius:99px;padding:2px 9px;margin-right:6px;}
.st-key-catalog_selection_panel {border:2px solid #2563eb!important;border-radius:18px!important;background:#f2f7ff!important;padding:22px!important;box-shadow:0 4px 18px rgba(37,99,235,.08);}
.st-key-catalog_selection_panel [data-testid="stWidgetLabel"] p {font-size:1.12rem;font-weight:750;color:#17365d;}
.st-key-catalog_selection_panel [data-baseweb="select"]>div {min-height:56px;border:1px solid #9fbce9;background:#fff;color:#17365d;}
.st-key-catalog_selection_panel [data-testid="stButton"] button {min-height:52px;font-size:1.08rem;font-weight:700;}
.st-key-catalog_selection_panel [data-testid="stLinkButton"] a {min-height:52px;background:#fff;color:#17365d;}
.st-key-catalog_selection_panel [data-testid="stMarkdownContainer"] {color:#17365d;}
.st-key-catalog_selection_panel button[kind="primary"] p {color:#fff!important;}
.picker-kicker {color:#2459a6;font-weight:800;letter-spacing:.06em;font-size:.85rem;margin-bottom:8px;}
.picker-title {font-size:1.55rem;font-weight:850;color:#17365d;margin:0 0 8px;line-height:1.4;}
.picker-subtitle {font-size:1rem;line-height:1.65;color:#3d5572;margin-bottom:14px;}
.picker-detail {background:#fff;color:#17365d;border:1px solid #cadaef;border-left:5px solid #2563eb;border-radius:10px;padding:18px;margin:8px 0;overflow-wrap:anywhere;}
.picker-kind {display:inline-block;color:#174c91;background:#e7f0ff;border-radius:6px;font-size:.86rem;font-weight:750;padding:4px 9px;margin-bottom:10px;}
.picker-fulltitle {font-size:1.3rem;font-weight:750;line-height:1.65;margin-bottom:10px;white-space:pre-wrap;}
.picker-meta {color:#465c75;font-size:.96rem;line-height:1.8;}
.picker-reference {border-top:1px solid #e3eaf4;margin-top:12px;padding-top:12px;line-height:1.7;color:#253e5b;font-size:.95rem;}
@media(max-width:800px){.paper-flow{grid-template-columns:repeat(2,minmax(0,1fr));}.st-key-catalog_selection_panel{padding:15px!important;}.picker-title{font-size:1.3rem;}}
@media(max-width:420px){.paper-flow{grid-template-columns:1fr;}.picker-fulltitle{font-size:1.1rem;}}
</style>
"""


def render_search_guide(st) -> None:
    """상태를 추측하지 않고 사용자가 수행할 순서를 안내한다."""
    st.markdown(PICKER_CSS, unsafe_allow_html=True)
    st.markdown("""
<div class="paper-flow" aria-label="자료 찾기 이용 순서">
 <div class="paper-flow-step"><strong><span class="paper-flow-no">1</span>주제 검색</strong><span>검색어를 입력하고 검색 실행</span></div>
 <div class="paper-flow-step"><strong><span class="paper-flow-no">2</span>대분류 선택</strong><span>학위논문 · 학술기사 · 도서자료</span></div>
 <div class="paper-flow-step"><strong><span class="paper-flow-no">3</span>자료 선택·확인</strong><span>콤보박스에서 한 편 선택</span></div>
 <div class="paper-flow-step"><strong><span class="paper-flow-no">4</span>논문 읽기</strong><span>02로 이동한 뒤 PDF·초록 준비</span></div>
</div>
""", unsafe_allow_html=True)
    st.caption("검색·자료 선택에는 개인 OpenAI 키가 필요하지 않습니다. AI 요약을 실행할 때만 왼쪽에 개인 키를 입력하세요.")


def detail_html(item: dict) -> str:
    """동적 서지정보는 HTML 이스케이프 후 표시한다. 긴 제목은 줄바꿈한다."""
    text = {key: escape(str(item.get(key, "")), quote=True) for key in
            (TITLE, AUTHOR, YEAR, CONTROL, PUBLISHER, KIND, REFERENCE)}
    return (f'<div class="picker-detail">'
            f'<div class="picker-kind">{text[KIND]} · 선택 자료</div>'
            f'<div class="picker-fulltitle">{text[TITLE]}</div>'
            f'<div class="picker-meta">저자: {text[AUTHOR]} &nbsp;|&nbsp; 발행연도: {text[YEAR]}<br>'
            f'발행처·대학: {text[PUBLISHER]}<br>자료 관리번호: {text[CONTROL]}</div>'
            f'<div class="picker-reference"><strong>정식 참고문헌</strong><br>{text[REFERENCE]}</div>'
            '</div>')


def render_catalog_picker(st, frame: pd.DataFrame, on_read: Callable[[str], None]) -> dict | None:
    """강조 패널. 대분류는 서버 검색 조건이 아니라 수집된 자료의 조회 필터다."""
    items = identity_rows(frame)
    _, counts = prepare_category(st.session_state, items)
    with st.container(border=True, key="catalog_selection_panel"):
        st.markdown('<div class="picker-kicker">다음 할 일 · STEP 2–4</div>'
                    '<div class="picker-title">📖 읽을 논문·자료를 선택하세요</div>'
                    '<div class="picker-subtitle">먼저 <strong>대분류</strong>를 고르면 해당 자료만 아래 선택창에 나옵니다.<br>'
                    '자료를 선택한 뒤 제목과 참고문헌을 확인하고 <strong>「02. 논문 읽기 시작」</strong>을 누르세요.</div>',
                    unsafe_allow_html=True)
        columns = st.columns([1, 2.5])
        with columns[0]:
            category = st.selectbox("① 대분류 선택", CATEGORIES, key=CATEGORY_WIDGET, index=None,
                format_func=lambda value: category_label(value, counts),
                help="API 검색을 다시 실행하거나 자료유형을 수동 지정하지 않습니다. 자동분류된 수집 자료 중 볼 유형만 선택합니다.")
        candidates = prepare_record(st.session_state, items, category)
        mapping = {item[ROWKEY]: item for item in candidates}
        with columns[1]:
            chosen = st.selectbox("② 세부 자료 선택 (제목·저자·연도·관리번호)", list(mapping),
                index=None, key=RECORD_WIDGET, disabled=not bool(mapping),
                placeholder="목록을 열어 읽을 자료를 선택하세요",
                format_func=lambda value: record_label(mapping[value]),
                help="선택창을 클릭한 뒤 제목, 저자 또는 관리번호로 목록을 찾을 수 있습니다. 전체 제목은 아래 카드에 표시됩니다.")
        # 알 수 없는 위젯값은 안전하게 해제한다. 다른 유형의 자료가 섞이지 않는다.
        if chosen not in mapping:
            chosen = None
        remember_record(st.session_state, category, chosen)
        st.caption(f"현재 수집한 {len(items):,}건 중 {category} {len(candidates):,}건 · 이 선택은 추가 API 호출을 하지 않습니다.")
        if not candidates:
            st.info("현재 수집한 목록에는 이 유형의 자료가 없습니다. 다른 대분류를 선택하거나 검색 페이지를 추가로 가져오세요.")
            return None
        item = mapping.get(chosen)
        if item is None:
            st.info("다음 단계: 오른쪽 「② 세부 자료 선택」을 열어 한 편을 선택하세요. 자료를 고르면 전체 제목과 이동 버튼이 나타납니다.")
            st.button("📖 02. 논문 읽기 시작", type="primary", use_container_width=True,
                      disabled=True, key="p0_to_reading")
            return None
        st.markdown("**③ 선택한 자료 확인**")
        st.markdown(detail_html(item), unsafe_allow_html=True)
        target = reading_target(item)
        if category == BOOK:
            st.info("도서자료는 참고용입니다. 공식 상세정보에서 원문·소장정보를 확인하세요. 학위논문·학술기사를 고르면 02 논문 읽기를 시작할 수 있습니다.")
        elif category == UNKNOWN:
            st.warning("자료유형을 확정할 근거가 부족하거나 서로 충돌합니다. 공식 상세정보를 확인할 수 있지만 논문으로 자동 전달하지 않습니다.")
            st.write("미확인 이유: " + str(item.get(REASON) or "분류 근거 부족"))
        elif not target:
            st.warning("공식 관리번호가 확인되지 않아 잘못된 자료 전달을 막았습니다. 02에서 PDF를 직접 업로드하거나 미확인 자료의 상세정보를 확인하세요.")
        else:
            st.success("선택 완료! 오른쪽 「02. 논문 읽기 시작」을 누르세요. PDF가 없어도 이동할 수 있으며, AI 요약 전 PDF 또는 초록이 필요합니다.")
        left, right = st.columns(2)
        with left:
            if item.get(LINK):
                st.link_button("🔗 공식 상세정보·원문 확인", item[LINK], use_container_width=True)
            else:
                st.caption("공식 상세정보 링크 미확인")
        with right:
            st.button("📖 02. 논문 읽기 시작", type="primary", use_container_width=True,
                disabled=not bool(target), on_click=on_read, args=(target,), key="p0_to_reading")
        st.caption("상세정보 링크는 PDF 자동 다운로드가 아닙니다. 원문 제공 여부와 이용 권한은 연결된 사이트에서 확인하세요.")
        return item