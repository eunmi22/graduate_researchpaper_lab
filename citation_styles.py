"""대학원 과제 보고서용 자료유형별 참고문헌 표기 및 서지정보 검증.

사용자가 정한 과제 표기 규칙으로, APA/IEEE 공식 인용양식이라고 주장하지 않습니다.
외부 API에 누락된 자료는 채워 넣지 않고 [항목 미확인]으로 표시합니다.
"""

from __future__ import annotations

import html
import re
from typing import Mapping

JOURNAL = "학술지 논문"
THESIS = "석사·박사 학위논문"
REPORT = "기관 연구보고서"
BOOK = "단행본"
UNKNOWN = "자료유형 확인 필요"
REFERENCE_TYPES = (JOURNAL, THESIS, REPORT, BOOK)

REFERENCE_TEMPLATES = {
    JOURNAL: '[저자], “[논문 제목]”, [학술지명], [권], [호], [수록 페이지], [발행 연월]. DOI: [식별번호].',
    THESIS: '[저자], “[논문 제목]”, [석사학위논문 또는 박사학위논문], [학위수여 대학·대학원], [학위수여 연월].',
    REPORT: '[저자 또는 기관명], “[보고서 제목]”, [발행기관], [보고서 번호], [발행 연월]. [DOI 또는 URL].',
    BOOK: '[저자], 『[도서 제목]』, [출판사], [발행 연월].',
}
THESIS_EXAMPLE = '김수용, “Amazon RDS 데이터베이스 디지털포렌식 조사 기법 연구”, 석사학위논문, 고려대학교 대학원, 2026년 8월.'


def _text(value: object) -> str:
    """문자열 정리. Excel/판다스의 NaN도 빈 문자열로 취급."""
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"<[^>]*>", "", value)
    value = " ".join(value.split()).strip()
    if value.lower() in {"nan", "none", "nat"}:
        return ""
    return value[:1500]


def _first(row: Mapping, *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key, ""))
        if value:
            return value
    return ""



def _parse_bibliographic_date(*statements: str) -> str:
    """발행사항에 실제 기재된 연월일만 표준 한글 날짜로 변환."""
    for source in statements:
        # '서울 : 학회, 2026. 4. 30' / '제2호 (2026년 4월)' 두 형식 지원.
        matched = re.search(
            r"(?<!\d)((?:19|20)\d{2})\s*(?:년|[.\-/])\s*(\d{1,2})"
            r"\s*(?:월|[.\-/])?\s*(\d{1,2})?\s*(?:일)?",
            source or "",
        )
        if matched:
            y, m, d = matched.groups()
            if 1 <= int(m) <= 12 and (not d or 1 <= int(d) <= 31):
                return f"{y}년 {int(m)}월" + (f" {int(d)}일" if d else "")
    return ""


def _parse_journal_details(raw: str) -> dict[str, str]:
    """수록지명에 직접 적힌 학술지·권·호·쪽수만 구조화, 추측 금지."""
    raw = _text(raw)
    result = {"journal": "", "volume": "", "issue": "", "pages": ""}
    if not raw:
        return result
    volume = re.search(r"제?\s*(\d+)\s*권", raw)
    issue = re.search(r"제?\s*(\d+)\s*호", raw)
    pages = re.search(r"(?:pp?\.?|p\.|페이지)\s*(\d+\s*[-–~]\s*\d+)", raw, re.I)
    prefix = re.split(r"제?\s*\d+\s*(?:권|호)|\(\s*(?:19|20)\d{2}", raw, maxsplit=1)[0]
    journal = prefix.split("=")[0].strip(" .,;:")
    result["journal"] = journal or raw
    if volume:
        result["volume"] = f"제{volume.group(1)}권"
    if issue:
        result["issue"] = f"제{issue.group(1)}호"
    if pages:
        result["pages"] = re.sub(r"\s+", "", pages.group(1)).replace("~", "-") + "쪽"
    return result

def guess_reference_type(row: Mapping) -> str:
    """자료유형을 명시적 서지 분류로만 판단; 모호하면 미확인 유지."""
    kind = _first(row, "자료유형", "DB", "document_type").lower()
    if any(token in kind for token in ("학위논문", "석사학위", "박사학위")):
        return THESIS
    if any(token in kind for token in ("학술지", "학술기사", "학술논문", "journal", "article")):
        return JOURNAL
    if any(token in kind for token in ("도서", "단행본", "ebook", "전자책")):
        return BOOK
    if any(token in kind for token in ("연구보고서", "기관보고서", "research report")):
        return REPORT
    # 단순 국내기사·국외기사는 학술지 수록정보가 있어야 학술논문으로 인정.
    if kind in ("국내기사", "국외기사", "기사"):
        journal = _first(row, "수록지명", "학술지명")
        if any(token in journal.lower() for token in ("논문", "학술", "journal", "권", "호")):
            return JOURNAL
    return UNKNOWN


def _parse_combined_title_and_author(combined: str) -> tuple[str, str]:
    """국회도서관의 '제목 /저자'를 보수적으로 분리. 잘못 분리할 가능성이 있으면 분리하지 않음."""
    raw = _text(combined)
    match = re.match(r"^(.*?)\s+/\s*(\S.*)$", raw)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return raw, ""


def suggested_citation(row: Mapping) -> dict[str, str]:
    """API에서 확인된 서지정보로만 초기값 제안. 누락 정보는 사용자 편집 대상으로 둠."""
    combined = _first(row, "자료명/저자사항", "제목", "논문제목", "title")
    title, author_from_combined = _parse_combined_title_and_author(combined)
    year = _first(row, "발행년", "발행연도", "year")
    date_value = _first(row, "발행 연월", "발행연월", "학위수여 연월", "date")
    if not date_value:
        date_value = _parse_bibliographic_date(
            _first(row, "발행자", "발행사항", "publisher"),
            _first(row, "수록지명", "학술지명", "journal"),
        )
    if not date_value and year:
        year_match = re.fullmatch(r"(19\d{2}|20\d{2})", year)
        date_value = f"{year}년 (월 미확인)" if year_match else year
    kind = guess_reference_type(row)
    journal_data = _parse_journal_details(_first(row, "수록지명", "학술지명", "journal"))
    degree = _first(row, "학위종류", "degree_type")
    if not degree:
        raw_type = _first(row, "DB", "자료유형")
        if "박사" in raw_type:
            degree = "박사학위논문"
        elif "석사" in raw_type:
            degree = "석사학위논문"
    publisher = _first(row, "발행기관", "발행자", "publisher")
    if kind == BOOK and publisher:
        # '서울 : 출판사, 2026' -> '출판사': 원문에 적힌 부분만 사용합니다.
        publisher = re.sub(r"^.{1,25}?\s*:\s*", "", publisher)
        publisher = re.sub(r",?\s*(?:19|20)\d{2}(?:[.\-/]\s*\d{1,2})*(?:\s*[.]?\s*\d{1,2})?\s*$", "", publisher).strip(" ,")
    return {
        "type": kind,
        "author": _first(row, "저자", "저자명", "author") or author_from_combined,
        "title": title,
        "publication_date": date_value,
        "journal": _first(row, "학술지명", "journal") or journal_data["journal"],
        "volume": _first(row, "권", "volume") or journal_data["volume"],
        "issue": _first(row, "호", "issue") or journal_data["issue"],
        "pages": _first(row, "수록 페이지", "페이지", "pages") or journal_data["pages"],
        "doi": _first(row, "DOI", "doi"),
        "degree": degree,
        "university": _first(row, "학위수여 대학·대학원", "학위수여기관", "수여대학", "university"),
        "publisher": publisher,
        "report_number": _first(row, "보고서 번호", "보고서번호", "report_number"),
        "url": _first(row, "원문URL", "원문링크", "URL", "url"),
    }


def complete_citation(row: Mapping, edits: Mapping | None = None) -> dict[str, str]:
    """API 값으로 초기화하고 사용자가 확인/수정한 필드로 덮어쓰기."""
    record = suggested_citation(row)
    if edits:
        for key in record:
            if key in edits:
                record[key] = _text(edits[key])
    if record["type"] not in (*REFERENCE_TYPES, UNKNOWN):
        record["type"] = UNKNOWN
    if record["degree"] and record["degree"] not in ("석사학위논문", "박사학위논문"):
        record["degree"] = ""
    return record


def format_reference(record: Mapping) -> str:
    """사용자 지정 3종 표기 방식. 빠진 값은 미확인으로 남겨 허위 인용 방지."""
    kind = _first(record, "type")

    def field(key: str, label: str) -> str:
        return _text(record.get(key, "")) or f"[{label} 미확인]"

    author = field("author", "저자")
    title = field("title", "제목")
    date_value = field("publication_date", "발행 연월")
    if kind == JOURNAL:
        journal = field("journal", "학술지명")
        volume = field("volume", "권")
        issue = field("issue", "호")
        pages = field("pages", "수록 페이지")
        doi = field("doi", "DOI")
        return f'{author}, “{title}”, {journal}, {volume}, {issue}, {pages}, {date_value}. DOI: {doi}.'
    if kind == THESIS:
        degree = field("degree", "학위종류")
        university = field("university", "학위수여 대학·대학원")
        return f'{author}, “{title}”, {degree}, {university}, {date_value}.'
    if kind == BOOK:
        publisher = field("publisher", "출판사")
        return f'{author}, 『{title}』, {publisher}, {date_value}.'
    if kind == REPORT:
        publisher = field("publisher", "발행기관")
        number = field("report_number", "보고서 번호")
        location = _first(record, "doi") or _first(record, "url") or "[DOI/URL 미확인]"
        return f'{author}, “{title}”, {publisher}, {number}, {date_value}. {location}.'
    return (
        f'[자료유형 미확인] {author}, “{title}”, {date_value}. '
        '학술지 논문·학위논문·기관 연구보고서 중 올바른 유형을 선택해야 합니다.'
    )


def missing_citation_fields(record: Mapping) -> list[str]:
    """보고서 제출 전 확인할 필수/표기 필드를 반환."""
    kind = _first(record, "type")
    fields = {
        JOURNAL: (("author", "저자"), ("title", "제목"), ("journal", "학술지명"),
                  ("volume", "권"), ("issue", "호"), ("pages", "수록 페이지"),
                  ("publication_date", "발행 연월"), ("doi", "DOI")),
        THESIS: (("author", "저자"), ("title", "제목"), ("degree", "학위종류"),
                 ("university", "학위수여 대학·대학원"), ("publication_date", "학위수여 연월")),
        BOOK: (("author", "저자"), ("title", "도서 제목"),
               ("publisher", "출판사"), ("publication_date", "발행 연월")),
        REPORT: (("author", "저자/기관명"), ("title", "보고서 제목"),
                 ("publisher", "발행기관"), ("report_number", "보고서 번호"),
                 ("publication_date", "발행 연월")),
    }
    if kind not in fields:
        return ["자료유형"]
    missing = [label for key, label in fields[kind] if not _text(record.get(key))]
    if kind == REPORT and not (_text(record.get("doi")) or _text(record.get("url"))):
        missing.append("DOI/URL")
    # 발행연도만 제공받았다면 '월 미확인' 역시 제출 전 확인 대상.
    if "월 미확인" in _text(record.get("publication_date")):
        missing.append("발행 월")
    return missing
