"""Readable catalogue identities; selection keys never depend on display labels.

No API calls, AI inference or fabricated bibliographic values are used here.
Missing/duplicate control numbers get internal-only keys for inspection, not links.
"""
from __future__ import annotations
import hashlib
import json
import re
from collections import Counter
import pandas as pd
from nanet_metadata import normalize_frame, clean_text, control_number, UNKNOWN
from citation_styles import suggested_citation, format_reference
from paperlab import nanet_detail_url

CONTROL = "자료 관리번호"
TITLE = "자료명/저자사항"
AUTHOR = "저자"
YEAR = "발행연도"
PUBLISHER = "발행처·대학"
KIND = "자료유형"
REASON = "분류 근거·미확인 이유"
LINK = "공식 상세정보"
REFERENCE = "정식 참고문헌"
ROWKEY = "_record_key"
MISSING_CONTROL = "관리번호 미확인"
MISSING_TITLE = "제목 미확인"


def _short(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit-1] + "..."


def identity_rows(frame: pd.DataFrame) -> list[dict]:
    """Build human-readable rows with a stable internal key and full title."""
    normalized = normalize_frame(frame)
    result = []
    seen = Counter()
    for row in normalized.to_dict('records'):
        ident = control_number(row)
        citation = suggested_citation(row)
        title = clean_text(citation.get('title')) or clean_text(row.get(TITLE))
        if title in ('⚠ 제목 미제공', '제목 미제공', MISSING_TITLE):
            title = ''
        author = clean_text(citation.get('authors')) or clean_text(citation.get('author')) or clean_text(row.get(AUTHOR))
        # Only extract a year actually present in a publication date; do not use ID digits.
        raw_year = clean_text(row.get('발행년')) or clean_text(row.get('발행연월'))
        year_match = re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)', raw_year)
        year = year_match.group() if year_match else ''
        publisher = clean_text(row.get('발행자')) or clean_text(row.get('학위수여기관'))
        if ident:
            base_key = 'control:' + ident
        else:
            # This is NOT a library control number. Never use it for a detail link.
            payload = {k: row.get(k, '') for k in (TITLE, AUTHOR, '발행자', '발행년', 'DB', '관리번호 원문', 'API순번')}
            base_key = 'local:' + hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:16]
        seen[base_key] += 1
        row_key = base_key if seen[base_key] == 1 else f'{base_key}#{seen[base_key]}'
        raw_ident = clean_text(row.get('관리번호 원문'))
        display_id = ident or (raw_ident + ' (형식 확인 필요)' if raw_ident else MISSING_CONTROL)
        label = ' | '.join((display_id, _short(title or MISSING_TITLE, 90),
                            _short(author or '저자 미확인', 45), year or '연도 미확인'))
        if not ident or seen[base_key] > 1:
            label += f' | 목록 식별 {row_key[-10:]}'
        result.append({
            ROWKEY: row_key, CONTROL: display_id, TITLE: title or MISSING_TITLE,
            AUTHOR: author or '저자 미확인', YEAR: year or '연도 미확인',
            PUBLISHER: publisher or '발행처 미확인',
            KIND: clean_text(row.get('자료분류')) or UNKNOWN,
            REASON: clean_text(row.get('분류근거')),
            LINK: nanet_detail_url(ident) if ident else '',
            REFERENCE: format_reference(citation),
            '분류출처': clean_text(row.get('분류출처')),
            'API순번': row.get('API순번', ''),
            'label': label, 'record': row,
        })
    return result


def identity_table(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [CONTROL, TITLE, AUTHOR, YEAR, PUBLISHER, KIND, REASON, LINK, REFERENCE, '분류출처', 'API순번']
    return pd.DataFrame([{key: entry[key] for key in columns} for entry in identity_rows(frame)], columns=columns)


def filter_identities(rows: list[dict], query: str) -> list[dict]:
    words = clean_text(query).casefold().split()
    if not words:
        return rows
    keys = (CONTROL, TITLE, AUTHOR, YEAR, PUBLISHER)
    return [row for row in rows if all(word in ' '.join(str(row.get(k, '')) for k in keys).casefold() for word in words)]
