"""PDF 전 페이지 텍스트 수집과 네 구역 근거 선별. 네트워크 호출 없음.

PDF 페이지와 추출 텍스트는 사용자 Streamlit 세션 메모리에서만 취급합니다.
내장 PDF 텍스트만 지원하며, 스캔 PDF OCR / 그림 판독은 수행하지 않습니다.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

import fitz

MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_PAGES = 600
MAX_TEXT_PER_PAGE = 16000


@dataclass(frozen=True)
class PageText:
    page: int  # PDF 페이지(1부터 시작). 인쇄된 페이지 번호가 아님
    text: str


@dataclass(frozen=True)
class PdfDocument:
    total_pages: int
    pages: tuple[PageText, ...]
    clipped_pages: int = 0

    @property
    def char_count(self) -> int:
        return sum(len(p.text) for p in self.pages)

    @property
    def text_pages(self) -> int:
        return sum(bool(p.text.strip()) for p in self.pages)


@dataclass(frozen=True)
class EvidencePacket:
    section: str
    page_numbers: tuple[int, ...]
    text: str


SECTION_PATTERNS = {
    "초록·서론": re.compile(r"^(?:[제 ]*\d+[.\s]*)?(초록|요약|서론|연구 배경|abstract|introduction|background)(?:\s|$|[:：])", re.I),
    "연구 방법": re.compile(r"^(?:[제 ]*\d+[.\s]*)?(연구\s*방법|분석\s*방법|연구\s*설계|실험\s*방법|방법론|methodology|methods?|materials and methods?|experiments?)(?:\s|$|[:：])", re.I),
    "연구 결과": re.compile(r"^(?:[제 ]*\d+[.\s]*)?(연구\s*결과|실험\s*결과|분석\s*결과|평가\s*결과|성능\s*평가|results?|findings?|evaluation)(?:\s|$|[:：])", re.I),
    "토의·결론": re.compile(r"^(?:[제 ]*\d+[.\s]*)?(결론|토의|논의|고찰|요약\s*및\s*결론|향후\s*연구|discussion|conclusions?|future work|limitations?)(?:\s|$|[:：])", re.I),
}


def extract_pdf_pages(data: bytes) -> PdfDocument:
    """전 페이지 추출. 처리 불가능하게 큰 파일은 조용히 일부만 읽지 않고 안내함."""
    if not data or len(data) > MAX_PDF_BYTES:
        raise ValueError("15MB 이하의 PDF를 업로드해 주세요.")
    try:
        with fitz.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass:
                raise ValueError("암호가 설정된 PDF는 지원하지 않습니다.")
            n = len(pdf)
            if n > MAX_PAGES:
                raise ValueError(f"현재 버전은 최대 {MAX_PAGES}페이지 PDF를 지원합니다. 파일을 나눠 업로드해 주세요.")
            pages = []
            clipped = 0
            for i in range(n):
                content = pdf.load_page(i).get_text("text", sort=True).strip()
                if len(content) > MAX_TEXT_PER_PAGE:
                    clipped += 1
                    # 추출·분석 편중을 피하려고 페이지의 앞뒤를 보존.
                    content = content[:10000] + "\n[이 페이지의 중간 일부 생략]\n" + content[-6000:]
                pages.append(PageText(page=i + 1, text=content))
            return PdfDocument(total_pages=n, pages=tuple(pages), clipped_pages=clipped)
    except ValueError:
        raise
    except (RuntimeError, fitz.FileDataError) as exc:
        raise ValueError("PDF를 읽을 수 없습니다. 손상·암호 설정 여부를 확인하세요.") from exc


def _looks_like_heading(line: str, section: str) -> bool:
    clean = " ".join(line.split()).strip("-•▪○ ·\t")
    # 목차에서 긴 제목과 점선/페이지 번호를 보수적으로 배제
    if not clean or len(clean) > 100 or re.search(r"\.{3,}|…{2,}", clean):
        return False
    return bool(SECTION_PATTERNS[section].search(clean))


def _section_headings(pages: tuple[PageText, ...], section: str) -> list[int]:
    found = []
    for page in pages:
        if not page.text.strip():
            continue
        lines = page.text.splitlines()
        # 첫 3페이지는 목차 등 제목 오인 위험이 높음. 초록·서론에는 허용.
        if section != "초록·서론" and page.page <= 3 and len(pages) > 8:
            continue
        if any(_looks_like_heading(line, section) for line in lines):
            found.append(page.page)
    return found


def build_evidence_packets(doc: PdfDocument, per_page_chars: int = 2600,
                           max_pages_per_section: int = 3) -> list[EvidencePacket]:
    """초록/방법/결과/결론을 전체 페이지 범위에서 탐색하여 대표 페이지 선별.

    장 제목을 찾지 못하면 해당 구간의 위치 기반 대표 페이지를 사용합니다.
    완전성 보장 대신 선별 범위를 UI로 투명하게 공개합니다.
    """
    pages = [p for p in doc.pages if p.text.strip()]
    if not pages:
        return []
    total = doc.total_pages
    fallbacks = {
        "초록·서론": [1, min(total, 2), max(1, round(total * .12))],
        "연구 방법": [max(1, round(total * .30)), max(1, round(total * .40))],
        "연구 결과": [max(1, round(total * .65)), max(1, round(total * .75))],
        "토의·결론": [max(1, round(total * .88)), max(1, round(total * .95)), total],
    }
    available = {p.page: p for p in pages}
    packets = []
    for section in SECTION_PATTERNS:
        headings = _section_headings(doc.pages, section)
        # 결과·결론은 본문 뒤쪽에 있는 제목을 우선 (목차에서 언급되는 경우 방지)
        if section == "연구 결과":
            headings.sort(key=lambda p: (p < total * .38, p))
        elif section == "토의·결론":
            headings.sort(key=lambda p: (p < total * .55, -p))
        else:
            headings.sort()
        candidates = []
        if section == "초록·서론":
            candidates.extend([1, 2])
        candidates.extend(headings[:2])
        # 본문 장 제목 직후 페이지까지 읽기(제목만 페이지 끝에 있으면 대비)
        for page in headings[:1]:
            if page + 1 <= total:
                candidates.append(page + 1)
        candidates.extend(fallbacks[section])
        selected = []
        for number in candidates:
            if number in available and number not in selected:
                selected.append(number)
            if len(selected) >= max_pages_per_section:
                break
        if not selected:
            continue
        blocks = []
        for page_number in selected:
            page_text = available[page_number].text
            if len(page_text) > per_page_chars:
                # 잘린 부분이 있음을 AI와 사용자 모두에게 명시.
                head = int(per_page_chars * .72)
                tail = per_page_chars - head
                page_text = page_text[:head] + "\n[페이지 중간 일부 생략]\n" + page_text[-tail:]
            blocks.append(f"[PDF 페이지 {page_number}]\n{page_text}")
        packets.append(EvidencePacket(section, tuple(selected), "\n\n".join(blocks)))
    return packets


def coverage(doc: PdfDocument, packets: list[EvidencePacket]) -> dict:
    included = sorted({p for packet in packets for p in packet.page_numbers})
    return {
        "total_pages": doc.total_pages,
        "text_pages": doc.text_pages,
        "chars_extracted": doc.char_count,
        "selected_pages": included,
        "selected_page_count": len(included),
        "clipped_pages": doc.clipped_pages,
        "sections": {packet.section: list(packet.page_numbers) for packet in packets},
    }


def verify_quote(doc: PdfDocument | None, page: int | None, quote: str,
                 abstract: str = "") -> tuple[bool, str]:
    """PDF 페이지 텍스트/사용자 초록에 인용한 *문구*가 포함되는지만 검증.

    인용의 문구 일치가 AI의 의미 해석까지 입증하지는 않습니다.
    """
    text = re.sub(r"\s+", " ", str(quote or "")).strip()
    if len(text) < 10:
        return False, "인용 문구가 너무 짧음"
    if page is None:
        source = re.sub(r"\s+", " ", abstract or "")
        return (text in source, "입력 초록 문구 일치" if text in source else "초록 문구 불일치")
    if doc is None or not isinstance(page, int) or isinstance(page, bool):
        return False, "PDF 페이지 확인 불가"
    if not 1 <= page <= doc.total_pages:
        return False, "PDF 페이지 범위 밖"
    original = re.sub(r"\s+", " ", doc.pages[page - 1].text)
    match = text in original
    return match, "PDF 텍스트 문구 일치" if match else "PDF 원문 문구 불일치"
