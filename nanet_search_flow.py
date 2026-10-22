"""국회도서관 /basic 검색: 학위논문 → 학술기사 → 도서자료 순서로 목록 유지.

API 원래 자료유형을 바꾸거나 누락된 자료의 유형을 추정하지 않습니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from paperlab import (
    PaperAPIError, classify_catalog_record, search_candidates, search_papers,
)


@dataclass
class LiteratureSearchResult:
    confirmed: pd.DataFrame = field(default_factory=pd.DataFrame)
    unverified: pd.DataFrame = field(default_factory=pd.DataFrame)
    total: int = 0
    raw_rows: int = 0
    excluded_books: int = 0  # 이전 버전 테스트 호환: 실제로는 제외하지 않고 books에 저장
    books: pd.DataFrame = field(default_factory=pd.DataFrame)
    catalog: pd.DataFrame = field(default_factory=pd.DataFrame)
    last_page: int = 0
    used_keyword: str = ""
    attempts: list[tuple[str, int, int]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    page_calls_budgeted: int = 0


# 공식 DB 필드로 확인된 세 자료유형. 확인되지 않은 자료는 네 번째로 분리합니다.
CATEGORY_ORDER = ("학위논문", "학술기사", "도서자료", "자료유형 미확인")
RANK_BY_CATEGORY = {name: i for i, name in enumerate(CATEGORY_ORDER)}


def catalog_category(row: dict) -> str:
    """자료유형의 출처가 명확할 때만 세 그룹에 배치하고, 그 외는 미확인으로 분류."""
    category = classify_catalog_record(row)
    # '기타자료'에는 신문·잡지·영상도 포함될 수 있습니다.
    # DB 유형에 도서/단행본/전자책이 명시된 경우에만 도서자료로 표시합니다.
    if category == "기타자료":
        raw_type = str(row.get("DB", "") or "").replace(" ", "").lower()
        if any(token in raw_type for token in ("도서", "단행본", "전자책", "ebook")):
            return "도서자료"
        return "자료유형 미확인"
    return {
        "학위논문": "학위논문",
        "학술논문": "학술기사",
        "기타자료": "도서자료",
        "미확인": "자료유형 미확인",
    }[category]


def sort_catalog_records(frame: pd.DataFrame) -> pd.DataFrame:
    """학위논문 > 학술기사 > 도서자료 > 유형 미확인. 기존 결과 내 순서는 유지."""
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    ordered = frame.copy()
    if ordered.empty:
        ordered["자료분류"] = pd.Series(dtype=str)
        return ordered.reset_index(drop=True)
    ordered["자료분류"] = ordered.apply(lambda row: catalog_category(row.to_dict()), axis=1)
    ordered["_우선순위"] = ordered["자료분류"].map(RANK_BY_CATEGORY)
    ordered = ordered.sort_values("_우선순위", kind="stable")
    return ordered.drop(columns=["_우선순위"]).reset_index(drop=True)


def partition_catalog_records(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """학술논문용 목록 / 확인 대기 / 도서자료 / 전체 순서 정렬 목록."""
    ordered = sort_catalog_records(frame)
    if ordered.empty:
        return ordered.copy(), ordered.copy(), ordered.copy(), ordered
    classes = ordered["자료분류"]
    papers = ordered[classes.isin(("학위논문", "학술기사"))].copy().reset_index(drop=True)
    unverified = ordered[classes.eq("자료유형 미확인")].copy().reset_index(drop=True)
    books = ordered[classes.eq("도서자료")].copy().reset_index(drop=True)
    return papers, unverified, books, ordered


def merge_catalog_pages(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """추가 페이지를 병합한 뒤 논문·미확인·도서 및 전체를 재정렬합니다.

    관리번호로 확인되는 중복만 제거하며, 관리번호가 없는 행은 버리지 않습니다.
    이미 사용자가 제목을 확인·수정한 자료는 기존 값을 우선 보존합니다.
    """
    frames = [frame for frame in (existing, incoming) if isinstance(frame, pd.DataFrame) and not frame.empty]
    if not frames:
        return partition_catalog_records(pd.DataFrame())
    combined = pd.concat(frames, ignore_index=True).fillna("")
    if "controlno" in combined:
        control = combined["controlno"].astype(str).str.strip()
        known = combined[control.ne("")].drop_duplicates(subset=["controlno"], keep="first")
        unknown = combined[control.eq("")]
        combined = pd.concat([known, unknown], ignore_index=True)
    return partition_catalog_records(combined)

def split_catalog_records(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """이전 버전 호환: 학술자료·미확인·도서 및 기타 수를 반환합니다.

    실제 전체 목록과 도서자료는 partition_catalog_records로 확인합니다.
    """
    if raw is None or raw.empty:
        blank = raw.iloc[0:0].copy() if isinstance(raw, pd.DataFrame) else pd.DataFrame()
        return blank, blank.copy(), 0
    classifications = raw.apply(lambda row: classify_catalog_record(row.to_dict()), axis=1)
    confirmed = raw[classifications.isin({"학술논문", "학위논문"})].copy().reset_index(drop=True)
    unverified = raw[classifications.eq("미확인")].copy().reset_index(drop=True)
    excluded_books = int(classifications.eq("기타자료").sum())
    return confirmed, unverified, excluded_books


def search_literature_basic(
    api_key: str,
    keyword: str,
    *,
    pages: int = 2,
    per_page: int = 20,
    search_field: str = "전체",
    automatic_retry: bool = True,
    diagnostics: list[dict] | None = None,
    max_page_calls: int = 12,
    fetch: Callable = search_papers,
) -> LiteratureSearchResult:
    """기존 통합검색만 호출하며 유형 미확인을 0건 결과로 오인하지 않습니다.

    - 처음 검색에서 학술 자료가 없고 자동 재검색을 선택했다면 핵심 단어로 한 번 확장.
    - API가 total>0으로 응답했는데 목록 파싱이 0개이면 검색어 문제로 처리하지 않음.
    - 기존 검색어에서 찾은 미분류 자료를 버리지 않고, 확장 검색 실패 시 보존.
    - 1시간 검색 제한을 위해 페이지 수를 보수적으로 계산합니다.
    """
    result = LiteratureSearchResult(used_keyword=" ".join(str(keyword or "").split()))
    candidates = search_candidates(keyword, automatic_retry)
    if max_page_calls < 1:
        result.errors.append("남은 검색 요청 한도가 없습니다.")
        return result

    best_score = -1
    pending_frames: list[pd.DataFrame] = []
    for candidate in candidates:
        if result.page_calls_budgeted + pages > max_page_calls:
            result.errors.append("추가 검색을 위한 요청 한도가 부족합니다.")
            break
        # 개인 API 키는 어떤 진단 자료에도 기록하지 않습니다.
        result.page_calls_budgeted += pages
        diagnostic_start = len(diagnostics) if diagnostics is not None else 0
        try:
            total, raw = fetch(
                api_key, candidate, pages=pages, per_page=per_page,
                search_field=search_field, diagnostics=diagnostics,
            )
        except (PaperAPIError, ValueError) as exc:
            result.errors.append(f"통합검색 실패: {exc}")
            # URL/인증/서비스 오류라면 다른 키워드로 반복 호출하지 않습니다.
            break
        if not isinstance(raw, pd.DataFrame):
            result.errors.append("검색 결과 형식을 해석하지 못했습니다.")
            break

        confirmed, unverified, excluded = split_catalog_records(raw)
        _academic, pending_for_review, books_for_display, sorted_catalog = partition_catalog_records(raw)
        result.attempts.append((candidate, total, len(confirmed)))
        if not pending_for_review.empty:
            pending_frames.append(pending_for_review)
        # 원래 키워드에서 발견한 자료가 확장 검색의 0건 응답 때문에 사라지지 않게 함.
        score = (3 if not confirmed.empty else 2 if not unverified.empty
                 else 1 if len(raw) else 0)
        if score > best_score:
            best_score = score
            result.used_keyword = candidate
            result.total = total
            result.raw_rows = len(raw)
            result.excluded_books = excluded
            result.confirmed = confirmed
            result.books = books_for_display
            result.catalog = sorted_catalog
            # 실제 호출 페이지가 진단 정보에 있을 때 그 값을 우선 사용합니다.
            recent_diagnostics = diagnostics[diagnostic_start:] if diagnostics is not None else []
            observed_pages = [record.get("페이지", 0) for record in recent_diagnostics]
            result.last_page = max(observed_pages, default=max(1, (len(raw) + per_page - 1) // per_page))
        if not confirmed.empty:
            break
        # total>0인데 row=0이면 파서 이슈일 가능성이 있어 검색어를 확대하지 않습니다.
        if total > 0 and raw.empty:
            result.errors.append(
                "검색 건수는 있으나 목록 레코드를 받지 못했습니다. XML 진단을 확인하세요."
            )
            break
        # 자동 재검색 해제 또는 마지막 후보면 여기서 종료.
    if pending_frames:
        pending = pd.concat(pending_frames, ignore_index=True)
        if "controlno" in pending.columns:
            pending = pending.drop_duplicates(subset=["controlno"], keep="first")
        result.unverified = pending.reset_index(drop=True)
    return result
