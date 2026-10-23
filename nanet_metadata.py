"""P0: public catalogue metadata normalization and evidence-based classification.

No AI inference is used. Raw API DB labels are retained. Prefix rules below are
case-verified catalogue conventions, not a claimed exhaustive official code list.
"""
from __future__ import annotations
import html
import json
import math
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from collections.abc import Mapping
import pandas as pd

THESIS = "학위논문"
ARTICLE = "학술기사"
BOOK = "도서자료"
UNKNOWN = "자료유형 미확인"
CATEGORY_ORDER = (THESIS, ARTICLE, BOOK, UNKNOWN)
PREFIX_RULES = {"KDMT": THESIS, "KINX": ARTICLE, "MONO": BOOK}
# FINX and other codes are intentionally not guessed: add only after verification.
PLACEHOLDERS = {"", "nan", "none", "nat", "null", "<na>", "미분류", "미확인", "자료유형 미확인"}

class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in ("br", "p", "div", "li") and not self.skip:
            self.parts.append(" ")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        if tag in ("p", "div", "li") and not self.skip:
            self.parts.append(" ")
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)

def clean_text(value) -> str:
    """Decode escaped highlighting, remove real markup, retain ordinary comparisons."""
    if value is None:
        return ""
    if not isinstance(value, (str, int, float, bool)):
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() in PLACEHOLDERS:
        return ""
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    if re.search(r"</?[A-Za-z][^>]*>", text):
        parser = _PlainText()
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
    return " ".join(text.replace("\x00", "").split()).strip()

def canonical_field(name: str) -> str:
    raw = clean_text(name)
    simple = re.sub(r"[\s_\-./／:()（）·]", "", raw).lower()
    groups = {
        "controlno": ("controlno", "controlnumber", "제어번호", "관리번호"),
        "DB": ("db", "dbname", "database", "자료유형", "자료구분", "자료종류", "materialtype", "documenttype"),
        "자료명/저자사항": (
            "자료명저자사항", "자료명저자", "자료명저자명", "자료명및저자사항", "제목저자사항", "제목저자",
            "자료명저자정보", "자료명저자표시", "titleandauthor", "titleauthors", "자료명", "서명", "논문명",
            "논문제목", "title", "titleauthor", "titlename", "기사명저자명", "기사명저자사항", "기사명저자",
            "기사명", "기사제목", "학위논문명저자사항", "학위논문명", "도서명", "도서명저자사항", "제목"),
        "저자": ("저자", "저자명", "저자사항", "author", "authors", "creator"),
        "발행자": ("발행자", "발행처", "발행기관", "publisher"),
        "발행사항": ("발행사항", "publicationstatement"),
        "발행년": ("발행년", "발행년도", "발행연도", "year", "pubyear", "publicationyear"),
        "발행연월": ("발행연월", "발행일", "발행일자", "publicationdate", "pubdate"),
        "수록지명": ("수록지명", "학술지명", "journal", "journalname", "수록정보"),
        "학위사항": ("학위사항", "학위논문사항", "학위논문주기", "degreenote"),
        "학위종류": ("학위종류", "학위구분", "degreetype"),
        "학위수여기관": ("학위수여기관", "학위수여대학", "수여대학", "university"),
        "DOI": ("doi",), "ISBN": ("isbn",), "ISSN": ("issn",),
    }
    for canonical, aliases in groups.items():
        if simple in aliases:
            return canonical
    return raw

def canonicalize_record(row: Mapping) -> dict:
    """Fill canonical aliases without concatenating unrelated titles or type codes."""
    result = {}
    conflicts = []
    for key, val in row.items():
        name = canonical_field(str(key))
        value = clean_text(val) if isinstance(val, (str, int, float)) or val is None else val
        if name not in result or not result[name]:
            result[name] = value
        elif value and result[name] != value:
            # Preserve alternatives for audit; never build a fake combined title.
            result[str(key)] = value
            conflicts.append(f"{name}: 복수 값")
    if conflicts:
        result["필드충돌"] = "; ".join(conflicts)
    return result

def control_number(row_or_value) -> str:
    if isinstance(row_or_value, (Mapping, pd.Series)):
        raw = next((clean_text(row_or_value.get(k)) for k in ("controlno", "controlNo", "제어번호", "관리번호")
                    if clean_text(row_or_value.get(k))), "")
    else:
        raw = clean_text(row_or_value)
    # Empty or ambiguous identifiers must not be merged or used to fetch a different record.
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", raw):
        return ""
    return raw.upper()

def _explicit_type(value: str) -> str:
    text = clean_text(value).replace(" ", "").lower()
    if not text:
        return ""
    if any(word in text for word in ("학위논문", "석사학위", "박사학위", "dissertation", "thesis")):
        return THESIS
    if any(word in text for word in ("일반도서", "도서자료", "아동도서", "어린이도서", "단행본", "전자책", "ebook")) or text == "도서":
        return BOOK
    if any(word in text for word in ("국내학술기사", "국외학술기사", "학술기사", "학술논문", "학술지논문", "저널논문", "journalarticle")):
        return ARTICLE
    if any(word in text for word in ("신문", "잡지", "멀티미디어", "정기간행물", "표그림", "표·그림", "영상", "학술행사", "웹db")):
        return "기타"
    return ""

@dataclass(frozen=True)
class TypeDecision:
    category: str
    source: str
    reason: str
    status: str = "자동분류"

def classify_record(row: Mapping) -> TypeDecision:
    """Conflicting source types stay unknown; no title/publisher keyword guessing."""
    signals = []
    for key in ("DB", "자료유형", "자료구분", "자료종류", "document_type", "상세자료유형"):
        cat = _explicit_type(row.get(key, ""))
        if cat:
            signals.append((cat, key))
    ident = control_number(row)
    prefix = re.match(r"^(KDMT|KINX|MONO)\d{8,20}$", ident)
    prefix_kind = PREFIX_RULES[prefix.group(1)] if prefix else ""
    official = {cat for cat, _ in signals}
    # No silent override, even if one of the inputs looks more authoritative.
    if len(official) > 1 or (official and prefix_kind and prefix_kind not in official):
        return TypeDecision(UNKNOWN, "공식정보·관리번호", "자료유형 근거가 충돌하여 자동 확정하지 않음", "충돌")
    if official:
        chosen = next(iter(official))
        if chosen == "기타":
            return TypeDecision(UNKNOWN, signals[0][1], "도서·논문 3분류 밖의 자료", "기타자료")
        return TypeDecision(chosen, signals[0][1], "원문 서지정보의 명시적 자료유형")
    if prefix_kind:
        return TypeDecision(prefix_kind, "관리번호", f"검증 사례 기반 접두어 {prefix.group(1)} (세부 학위·심사 여부는 별도)")
    degree = " ".join(clean_text(row.get(k)) for k in ("학위사항", "학위종류", "학위구분"))
    if any(w in degree for w in ("석사", "박사", "학위논문")):
        return TypeDecision(THESIS, "학위사항", "명시된 학위정보")
    # Domestic 'article' can also mean a magazine article. Require journal metadata.
    journal = clean_text(row.get("수록지명") or row.get("학술지명"))
    if journal and any(w in journal.lower() for w in ("학회논문지", "학술", "journal", "논문집", "논문지")):
        return TypeDecision(ARTICLE, "수록지명", "학술지 수록정보 (동료심사 여부 미판정)")
    return TypeDecision(UNKNOWN, "자료부족", "공식 유형·검증된 관리번호·서지정보가 부족함", "미확인")

def normalize_record(row: Mapping) -> dict:
    result = canonicalize_record(row)
    for key in ("자료명/저자사항", "저자", "발행자", "발행년", "DB", "controlno"):
        result.setdefault(key, "")
    result["controlno"] = control_number(result)
    # Keep DB unmodified: inferred category must not become fake API metadata.
    decision = classify_record(result)
    result.update({"자료분류": decision.category, "분류출처": decision.source,
                   "분류근거": decision.reason, "분류상태": decision.status})
    if not result["DB"]:
        result["DB"] = "미분류"
    return result

def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    attrs = frame.attrs.copy()
    if frame.empty:
        result = frame.copy()
        for col in ("자료명/저자사항", "DB", "controlno", "자료분류", "분류출처", "분류근거", "분류상태"):
            if col not in result:
                result[col] = pd.Series(dtype=str)
    else:
        result = pd.DataFrame(normalize_record(r) for r in frame.to_dict("records")).fillna("")
    result.attrs = attrs
    return result

def merge_records(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate only valid control numbers; fill missing fields and preserve first rank."""
    frames = [f for f in (existing, incoming) if isinstance(f, pd.DataFrame) and not f.empty]
    if not frames:
        return normalize_frame(pd.DataFrame())
    rows = []
    seen = {}
    for frame in frames:
        for source_row in frame.to_dict("records"):
            row = normalize_record(source_row)
            ident = control_number(row)
            if not ident or ident not in seen:
                if ident:
                    seen[ident] = len(rows)
                rows.append(row)
                continue
            old = rows[seen[ident]]
            for key, value in row.items():
                if key in ("자료분류", "분류출처", "분류근거", "분류상태"):
                    continue
                if clean_text(old.get(key)) in ("", "미분류") and clean_text(value):
                    old[key] = value
                elif key == "DB" and clean_text(value) and clean_text(value) != clean_text(old.get(key)):
                    old["상세자료유형"] = value
            rows[seen[ident]] = normalize_record(old)
    return pd.DataFrame(rows).fillna("")
