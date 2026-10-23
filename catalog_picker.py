"""자료유형별 선택 상태. API 검색·분류는 바꾸지 않고 결과만 필터링한다.

Streamlit 위젯값과 지속할 선택값을 분리한다. 화면 이동, 추가 페이지,
제목 보완, 같은 제목의 다른 자료를 모두 행번호 대신 내부 식별자로 구분한다.
"""
from __future__ import annotations

from collections.abc import MutableMapping

from catalog_identity import ROWKEY, KIND, TITLE, AUTHOR, YEAR, CONTROL
from nanet_metadata import THESIS, ARTICLE, BOOK, UNKNOWN, control_number

CATEGORIES = (THESIS, ARTICLE, BOOK, UNKNOWN)
ICONS = {THESIS: "🎓", ARTICLE: "📄", BOOK: "📚", UNKNOWN: "❔"}
CATEGORY_WIDGET = "_p0_picker_category"
RECORD_WIDGET = "_p0_picker_record"
CATEGORY_MEMORY = "p0_picker_category"
RECORD_MEMORY = "p0_picker_records"
LAST_CATEGORY = "p0_picker_last_category"
MIGRATED = "p0_picker_initialized"


def category_counts(items: list[dict]) -> dict[str, int]:
    """수집된 목록만 집계하며 API 전체 검색 건수는 사용하지 않는다."""
    return {kind: sum(item.get(KIND) == kind for item in items) for kind in CATEGORIES}


def category_items(items: list[dict], category: str) -> list[dict]:
    """입력 목록의 순서를 보존한다. 원본 자료분류를 변경하지 않는다."""
    return [item for item in items if item.get(KIND) == category]


def category_label(category: str, counts: dict[str, int]) -> str:
    return f"{ICONS.get(category, '')} {category} · {counts.get(category, 0):,}건"


def record_label(item: dict) -> str:
    """제목을 앞에 배치한다. 잘린 제목 전체는 선택 카드에서 확인한다."""
    title = str(item.get(TITLE) or "제목 미확인")
    if len(title) > 85:
        title = title[:84] + "…"
    author = str(item.get(AUTHOR) or "저자 미확인")
    if len(author) > 32:
        author = author[:31] + "…"
    label = f"{title} | {author} | {item.get(YEAR) or '연도 미확인'} | {item.get(CONTROL) or '관리번호 미확인'}"
    # 관리번호가 없거나 중복일 때에도 다른 행과 구별되는 표시를 제공한다.
    key = str(item.get(ROWKEY, ""))
    if key.startswith("local:") or "#" in key:
        label += " | 목록 식별 " + key[-10:]
    return label


def prepare_category(state: MutableMapping, items: list[dict]) -> tuple[str, dict[str, int]]:
    """위젯을 그리기 전에 호출한다. 이전 버전의 정상 선택도 1회 복원한다."""
    counts = category_counts(items)
    mapping = {item[ROWKEY]: item for item in items}
    if not state.get(MIGRATED):
        previous = state.get("p0_read_selected")
        if previous in mapping:
            kind = mapping[previous][KIND]
            if kind in CATEGORIES:
                state[CATEGORY_MEMORY] = kind
                state[RECORD_MEMORY] = {kind: previous}
        state[MIGRATED] = True
    fallback = next((kind for kind in CATEGORIES if counts[kind]), THESIS)
    category = state.get(CATEGORY_WIDGET, state.get(CATEGORY_MEMORY, fallback))
    if category not in CATEGORIES:
        category = fallback
    state[CATEGORY_WIDGET] = category
    return category, counts


def prepare_record(state: MutableMapping, items: list[dict], category: str) -> list[dict]:
    """대분류가 바뀌면 그 유형의 선택만 복원하고, 다른 유형의 선택은 제거한다."""
    candidates = category_items(items, category)
    valid = {item[ROWKEY] for item in candidates}
    remembered = dict(state.get(RECORD_MEMORY, {}))
    if state.get(LAST_CATEGORY) != category:
        choice = remembered.get(category)
    else:
        choice = state.get(RECORD_WIDGET, remembered.get(category))
    if choice not in valid:
        choice = None
        remembered.pop(category, None)
    state[RECORD_WIDGET] = choice
    state[RECORD_MEMORY] = remembered
    state[CATEGORY_MEMORY] = category
    state[LAST_CATEGORY] = category
    return candidates


def remember_record(state: MutableMapping, category: str, chosen: str | None) -> None:
    """이미 생성된 위젯 키는 수정하지 않는다. 지속할 데이터만 저장한다."""
    memory = dict(state.get(RECORD_MEMORY, {}))
    if chosen is None:
        memory.pop(category, None)
    else:
        memory[category] = chosen
    state[RECORD_MEMORY] = memory
    state[CATEGORY_MEMORY] = category


def clear_picker(state: MutableMapping) -> None:
    """새 검색에만 선택을 초기화한다. PDF·노트·API 키는 건드리지 않는다."""
    for key in (CATEGORY_WIDGET, RECORD_WIDGET, CATEGORY_MEMORY, RECORD_MEMORY,
                LAST_CATEGORY, MIGRATED, "p0_read_control", "p0_read_selected"):
        state.pop(key, None)


def reading_target(item: dict | None) -> str:
    """책과 미확인 자료는 논문 분석 대상으로 자동 전달하지 않는다."""
    if not item or item.get(KIND) not in (THESIS, ARTICLE):
        return ""
    return control_number(item.get("record", {}))