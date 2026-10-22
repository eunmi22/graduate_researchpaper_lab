"""국회도서관 상세페이지에서 **공개적으로 표시된 서지정보만** 선택적으로 보완.

이 파일은 자동 크롤러가 아닙니다. 사용자가 '제목 보완 시도'를 누른 소수의
관리번호에만 접근합니다. 로그인·CAPTCHA·차단을 우회하지 않으며, 원문 PDF를
다운로드하지 않습니다. 국회도서관의 HTML 구조가 바뀌면 미보완으로 남깁니다.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from paperlab import nanet_detail_url, clean_paper_title


class MetadataLookupError(Exception):
    """사용자에게 알려줄 상세페이지 접근·파싱 오류."""


def _text(node) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())[:900]


def _field_from_document(soup: BeautifulSoup, labels: tuple[str, ...]) -> str:
    """국회도서관의 상세페이지 th/td 및 dt/dd 서지 레이블 읽기."""
    for node in soup.find_all(("th", "dt")):
        name = re.sub(r"[\s:：]+", "", _text(node))
        if any(name == label or name.startswith(label + "(") for label in labels):
            next_cell = node.find_next_sibling("td" if node.name == "th" else "dd")
            if next_cell is not None:
                return _text(next_cell)
    # div 행 형태를 제공하는 일부 화면에서는 레이블 바로 옆 문단에서 검색.
    for node in soup.find_all(("strong", "span")):
        name = re.sub(r"[\s:：]+", "", _text(node))
        if name in labels:
            sibling = node.find_next_sibling()
            if sibling is not None and sibling.name in ("p", "span", "div"):
                value = _text(sibling)
                if value and value not in labels:
                    return value
    return ""


def parse_nanet_detail_html(source: str | bytes) -> dict[str, str]:
    """서지정보로 **직접 표시된 것만** 반환. 임의의 제목·저자를 생성하지 않음."""
    soup = BeautifulSoup(source, "html.parser")
    for unwanted in soup(["script", "style", "noscript", "svg"]):
        unwanted.decompose()
    title_candidates = []
    for key in ('meta[property="og:title"]', 'meta[name="citation_title"]', 'meta[name="DC.title"]'):
        meta = soup.select_one(key)
        if meta and meta.get("content"):
            title_candidates.append(meta.get("content"))
    for selector in ('h1', 'h2', 'h3', 'h4', '[class*="detailTitle"]', '[class*="detail_tit"]'):
        for element in soup.select(selector)[:15]:
            title_candidates.append(_text(element))
    name = ""
    for candidate in title_candidates:
        candidate = clean_paper_title(candidate)
        candidate = re.sub(r"\s*[\-|]\s*(국회도서관|국회전자도서관)\s*$", "", candidate).strip()
        if 6 <= len(candidate) <= 500 and not any(
            bad == candidate or candidate.startswith(bad + " ")
            for bad in ("국회도서관", "국회전자도서관", "자료 검색", "외부기관 자료", "상세보기", "검색 결과", "목록으로")
        ):
            name = candidate
            break
    author = _field_from_document(soup, ("저자명", "저자사항", "저자"))
    published = _field_from_document(soup, ("발행사항", "발행정보", "발행처"))
    journal = _field_from_document(soup, ("수록지명", "게재지", "학술지명"))
    dates = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", published)
    return {
        "자료명/저자사항": (f"{name} / {author}" if name and author else name),
        "저자": author,
        "발행자": published,
        "발행년": dates[-1] if dates else "",
        "수록지명": journal,
    }


def fetch_nanet_detail_metadata(controlno: str, session=None) -> dict[str, str]:
    """공식 관리번호를 검증하고 국회도서관 상세 HTML에서 서지정보를 읽습니다.

    동작 보장 대상이 아닙니다. 로그인 요구/JS 동적 렌더/기관 접속 제한이면 실패로
    반환하고 API 원본 정보를 보존하는 것이 올바른 처리입니다.
    """
    url = nanet_detail_url(controlno)
    if not url:
        raise MetadataLookupError("유효한 국회도서관 관리번호가 없습니다.")
    client = session if session is not None else requests
    try:
        response = client.get(
            url, timeout=(5, 9), allow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AcademicMetadataHelper/1.0)",
                     "Accept": "text/html,application/xhtml+xml"},
        )
        if response.status_code in (301, 302, 303, 307, 308):
            raise MetadataLookupError("상세페이지가 로그인 또는 다른 주소로 이동했습니다.")
        response.raise_for_status()
        content = response.content
    except requests.RequestException as exc:
        raise MetadataLookupError("국회도서관 상세페이지에 접근할 수 없습니다.") from exc
    if len(content) > 2_000_000:
        raise MetadataLookupError("상세페이지 응답이 너무 커서 분석하지 않았습니다.")
    target = urlsplit(response.url)
    if target.scheme != "https" or target.hostname != "dl.nanet.go.kr":
        raise MetadataLookupError("국회도서관 공식 도메인이 아닌 응답은 사용하지 않습니다.")
    metadata = parse_nanet_detail_html(content)
    if not metadata["자료명/저자사항"]:
        raise MetadataLookupError("상세페이지에서 제목을 자동 추출하지 못했습니다. 링크를 열어 직접 확인하세요.")
    return metadata
