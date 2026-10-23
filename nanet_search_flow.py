"""P0 search orchestration. One query, one catalogue; no silent mixed-query pools."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable
import pandas as pd
from paperlab import PaperAPIError, search_candidates, search_papers
from nanet_metadata import (
    CATEGORY_ORDER, UNKNOWN, clean_text, classify_record, normalize_frame,
    merge_records, control_number,
)
RANK_BY_CATEGORY = {name: i for i, name in enumerate(CATEGORY_ORDER)}

@dataclass
class LiteratureSearchResult:
    confirmed: pd.DataFrame = field(default_factory=pd.DataFrame)
    unverified: pd.DataFrame = field(default_factory=pd.DataFrame)
    total: int = 0
    raw_rows: int = 0
    excluded_books: int = 0  # Compatibility field; books are displayed, not discarded.
    books: pd.DataFrame = field(default_factory=pd.DataFrame)
    catalog: pd.DataFrame = field(default_factory=pd.DataFrame)
    last_page: int = 0
    next_page: int = 1
    used_keyword: str = ""
    attempts: list[tuple[str, int, int]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    page_calls_budgeted: int = 0
    exhausted: bool = False
    stalled: bool = False


def catalog_category(row: dict) -> str:
    return classify_record(row).category


def sort_catalog_records(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = normalize_frame(frame)
    if ordered.empty:
        return ordered.reset_index(drop=True)
    ordered["_category_rank"] = ordered["자료분류"].map(RANK_BY_CATEGORY)
    if "API순번" in ordered:
        ordered["_source_rank"] = pd.to_numeric(ordered["API순번"], errors="coerce")
        ordered = ordered.sort_values(["_category_rank", "_source_rank"], kind="stable", na_position="last")
        ordered = ordered.drop(columns=["_source_rank"])
    else:
        ordered = ordered.sort_values("_category_rank", kind="stable")
    return ordered.drop(columns=["_category_rank"]).reset_index(drop=True)


def partition_catalog_records(frame: pd.DataFrame):
    ordered = sort_catalog_records(frame)
    classes = ordered["자료분류"]
    return (
        ordered[classes.isin(("학위논문", "학술기사"))].copy().reset_index(drop=True),
        ordered[classes.eq(UNKNOWN)].copy().reset_index(drop=True),
        ordered[classes.eq("도서자료")].copy().reset_index(drop=True),
        ordered,
    )


def merge_catalog_pages(existing: pd.DataFrame, incoming: pd.DataFrame):
    # Merge only pages for the same query; changing page size starts a new search.
    for field_name in ("검색어", "검색항목"):
        a = {clean_text(v) for v in existing.get(field_name, []) if clean_text(v)}
        b = {clean_text(v) for v in incoming.get(field_name, []) if clean_text(v)}
        if a and b and a != b:
            raise ValueError("검색 조건이 다른 페이지는 합치지 않습니다. 새 검색을 실행하세요.")
    return partition_catalog_records(merge_records(existing, incoming))


def split_catalog_records(raw: pd.DataFrame):
    # Preserve input order for compatibility callers; UI uses sorted catalogue.
    normalized = normalize_frame(raw)
    classes = normalized["자료분류"]
    papers = normalized[classes.isin(("학위논문", "학술기사"))].reset_index(drop=True)
    unknown = normalized[classes.eq(UNKNOWN)].reset_index(drop=True)
    return papers, unknown, int(classes.eq("도서자료").sum())


def search_literature_basic(api_key: str, keyword: str, *, pages: int = 2,
                            per_page: int = 20, search_field: str = "전체",
                            automatic_retry: bool = False,
                            diagnostics: list[dict] | None = None,
                            max_page_calls: int = 12, fetch: Callable | None = None):
    """Fallback is opt-in and ONLY runs after a real zero-result API response.

    An absence of academic records in the currently fetched pages is not a
    zero-result search. Partial failures keep the successful pages and next retry.
    """
    candidates = search_candidates(keyword, automatic_retry)
    result = LiteratureSearchResult(used_keyword=candidates[0])
    if max_page_calls < 1:
        result.errors.append("남은 검색 요청 한도가 없습니다.")
        return result
    get_pages = fetch or search_papers
    for candidate in candidates:
        if result.page_calls_budgeted + pages > max_page_calls:
            result.errors.append("추가 검색을 위한 요청 한도가 부족합니다.")
            break
        before = len(diagnostics) if diagnostics is not None else 0
        try:
            total, raw = get_pages(api_key, candidate, pages=pages, per_page=per_page,
                                   search_field=search_field, diagnostics=diagnostics)
        except (PaperAPIError, ValueError) as exc:
            # Do not retain an exception object containing a prepared URL / secret key.
            message = str(exc).replace(str(api_key), "[인증키 제외]")
            result.errors.append("통합검색 실패: " + message)
            recent = diagnostics[before:] if diagnostics is not None else []
            result.page_calls_budgeted += sum(int(d.get("요청 횟수", 1)) for d in recent) or 1
            break
        if not isinstance(raw, pd.DataFrame):
            result.errors.append("검색 결과 형식을 해석하지 못했습니다.")
            break
        recent = diagnostics[before:] if diagnostics is not None else []
        result.page_calls_budgeted += int(raw.attrs.get("request_count", len(recent) or pages))
        normalized = normalize_frame(raw)
        papers, pending, books, catalog = partition_catalog_records(normalized)
        result.used_keyword = candidate
        result.total = total
        result.raw_rows = int(raw.attrs.get("raw_rows", len(raw)))
        result.attempts.append((candidate, total, len(catalog)))
        result.confirmed = papers
        result.unverified = pending
        result.books = books
        result.catalog = catalog
        result.excluded_books = len(books)
        result.last_page = int(raw.attrs.get("last_page", max((d.get("페이지", 0) for d in recent), default=1)))
        result.next_page = int(raw.attrs.get("next_page", result.last_page + 1))
        result.exhausted = bool(raw.attrs.get("exhausted", total == 0))
        result.stalled = bool(raw.attrs.get("stalled", False))
        result.errors.extend(raw.attrs.get("errors", []))
        if total > 0 or not raw.empty or result.errors:
            if total > 0 and raw.empty and not result.errors:
                result.errors.append("검색 건수는 있으나 목록 레코드를 받지 못했습니다. XML 진단을 확인하세요.")
                result.stalled = True
            break
    return result


def compare_web_reference(catalog: pd.DataFrame, web_records: list[dict]) -> tuple[pd.DataFrame, dict]:
    """Compare only supplied official-page samples; not a claim about all search hits."""
    api_rows = {control_number(r): r for r in normalize_frame(catalog).to_dict("records") if control_number(r)}
    output = []
    seen = set()
    for index, ref in enumerate(web_records, 1):
        ident = control_number(ref)
        if not ident or ident in seen:
            continue
        seen.add(ident)
        actual = api_rows.get(ident)
        title = clean_text(ref.get("title") or ref.get("자료명/저자사항"))
        category = clean_text(ref.get("category") or ref.get("자료분류"))
        output.append({
            "관리번호": ident, "웹 확인 순번": index,
            "API 순번": actual.get("API순번", "") if actual else "",
            "현재 수집 목록": "있음" if actual else "미수집 (API 전체 부재 아님)",
            "웹 제목": title, "API 제목": actual.get("자료명/저자사항", "") if actual else "",
            "제목 일치": "미검증" if not title or not actual else ("동일" if title == clean_text(actual.get("자료명/저자사항")) else "표기 차이 확인"),
            "웹 자료유형": category, "API 자료분류": actual.get("자료분류", "") if actual else "",
        })
    matched = sum(row["현재 수집 목록"] == "있음" for row in output)
    return pd.DataFrame(output), {"비교 기준 관리번호 수": len(output), "현재 수집 목록에서 확인": matched,
                                  "미수집": len(output) - matched,
                                  "표본 포함률": matched / len(output) if output else None}
