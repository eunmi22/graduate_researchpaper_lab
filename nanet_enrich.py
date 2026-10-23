"""Bounded public-metadata enrichment, separate from authenticated API searching.

Never fetch PDFs. Never bypass robots, login, redirects, CAPTCHA or rate limits.
The caller passes a per-session cache; no research PDFs or API keys are cached.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import time
from urllib.robotparser import RobotFileParser
import requests
import pandas as pd
from nanet_detail import fetch_nanet_detail_metadata, MetadataLookupError
from nanet_metadata import clean_text, normalize_frame, normalize_record, control_number, UNKNOWN

USER_AGENT = "AcademicMetadataHelper"

@dataclass
class EnrichmentResult:
    data: pd.DataFrame
    attempted: int = 0
    changed: int = 0
    remaining: int = 0
    errors: list[str] = field(default_factory=list)


def _robots_allows_detail(cache: dict) -> bool:
    saved = cache.get("__robots__", {})
    now = time.monotonic()
    if saved.get("expires", 0) > now:
        return bool(saved.get("allowed"))
    allowed = False
    try:
        response = requests.get("https://dl.nanet.go.kr/robots.txt", timeout=(3, 5),
                                allow_redirects=False, headers={"User-Agent": USER_AGENT})
        if response.status_code == 404:
            allowed = True
        elif response.status_code == 200 and len(response.content) < 200_000:
            parser = RobotFileParser()
            parser.parse(response.text.splitlines())
            allowed = parser.can_fetch(USER_AGENT, "https://dl.nanet.go.kr/search/searchInnerDetail.do")
    except requests.RequestException:
        # Access-policy check failed: do not replace it with aggressive retries.
        allowed = False
    cache["__robots__"] = {"expires": now + (3600 if allowed else 300), "allowed": allowed}
    return allowed


def needs_enrichment(row: dict) -> bool:
    return (not clean_text(row.get("자료명/저자사항"))
            or row.get("자료분류") == UNKNOWN)


def enrich_catalog(frame: pd.DataFrame, *, cache: dict | None = None, limit: int = 5,
                   lookup=None, check_access: bool = True, delay: float = 0.2) -> EnrichmentResult:
    data = normalize_frame(frame)
    result = EnrichmentResult(data)
    if data.empty:
        return result
    cache = cache if cache is not None else {}
    lookup = lookup or fetch_nanet_detail_metadata
    if limit < 1:
        result.remaining = sum(needs_enrichment(r) for r in data.to_dict("records"))
        return result
    candidates = [r for r in data.to_dict("records") if needs_enrichment(r) and control_number(r)]
    if candidates and check_access and not _robots_allows_detail(cache):
        result.errors.append("상세페이지 접근 정책을 확인하지 못했거나 자동 접근이 제한되어 API 자료만 표시합니다.")
        result.remaining = len(candidates)
        return result
    records = data.to_dict("records")
    for index, row in enumerate(records):
        if not needs_enrichment(row):
            continue
        ident = control_number(row)
        if not ident:
            continue
        old = cache.get(ident, {})
        now = time.monotonic()
        if old.get("expires", 0) > now:
            metadata = old.get("metadata", {})
            if old.get("error"):
                continue
        else:
            if result.attempted >= min(limit, 10):
                continue
            if result.attempted and delay:
                time.sleep(delay)
            result.attempted += 1
            try:
                metadata = lookup(ident)
                returned = control_number(metadata)
                if returned and returned != ident:
                    raise MetadataLookupError("요청 자료와 다른 관리번호입니다.")
                cache[ident] = {"expires": now + 3600, "metadata": metadata}
            except (MetadataLookupError, requests.RequestException, ValueError):
                cache[ident] = {"expires": now + 600, "error": True}
                result.errors.append(f"{ident}: 공개 상세정보 확인 실패 (원본 유지)")
                continue
        changed = False
        # Only fill blanks. A stronger source does not silently overwrite conflicts.
        for name, value in metadata.items():
            value = clean_text(value)
            if not value or name in ("controlno", "API순번", "API페이지", "검색어", "검색항목"):
                continue
            if name == "DB":
                name = "상세자료유형"
            if name in ("상세자료유형", "보완출처") or not clean_text(row.get(name)):
                if row.get(name) != value:
                    row[name] = value
                    changed = True
        records[index] = normalize_record(row)
        result.changed += int(changed)
    result.data = normalize_frame(pd.DataFrame(records))
    result.data.attrs = frame.attrs.copy()
    result.remaining = sum(needs_enrichment(r) for r in records)
    return result
