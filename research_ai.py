"""근거 페이지 검증을 포함한 6/7 모드 분석 엔진 (OpenAI SDK)."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from pdf_analysis import (PdfDocument, build_evidence_packets,
                          coverage as extraction_coverage, verify_quote)
from prompt_templates import (ASSIGNMENT, READING, fields_for,
                              final_system_prompt, STAGE_SYSTEM_PROMPT)

SUPPORTED_MODELS = {"gpt-4.1-mini", "gpt-4o-mini"}
MISSING = "원문에서 확인되지 않음"


def _as_json(result: Any) -> dict:
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError as exc:
            raise ValueError("AI 분석 결과가 올바른 JSON 형식이 아닙니다.") from exc
    if not isinstance(result, dict):
        raise ValueError("AI 분석 결과가 JSON 객체가 아닙니다.")
    return result


def _make_ask_json(api_key: str, model: str) -> Callable:
    # SDK import를 지연하여 오프라인 검증에 키/네트워크가 필요 없도록 함.
    from openai import OpenAI
    client = OpenAI(api_key=api_key, timeout=65.0, max_retries=1)

    def ask(system: str, user: str, max_tokens: int = 1500) -> dict:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=max_tokens,
        )
        return _as_json(response.choices[0].message.content or "")

    return ask


def _source_pages(doc: PdfDocument | None) -> int:
    return doc.total_pages if doc is not None else 0


def _normalized_one_line(value) -> str:
    content = " ".join(str(value or "").split()).strip()
    # 과도한 생성은 잘라 사실 관계가 바뀔 수 있으므로 실패/추가 검토가 필요하다고 표시.
    if len(content) > 260:
        content = content[:256].rstrip(" ,;") + " …"
    return content or MISSING


def _one_sentence(value) -> str:
    """JSON 필드별 1문장만 남겨 7문장 출력 형식을 강제합니다.

    정밀 자연어 문장 판독이 아니라 온점·느낌표·물음표 뒤 공백을 보수적으로 적용.
    """
    cleaned = _normalized_one_line(value)
    if cleaned == MISSING:
        return cleaned
    pieces = re.split(r"(?<=[.!?。])\s+(?=[가-힣A-Za-z\[(])", cleaned, maxsplit=1)
    return pieces[0].strip() or MISSING


def normalize_analysis(raw: dict, mode: str, pdf_doc: PdfDocument | None,
                       abstract: str = "", allowed_pages: set[int] | None = None) -> dict:
    """AI 제공 page/quote가 실제 PDF 텍스트에 존재하는지 검증하고 미확인 정보 분리."""
    raw = _as_json(raw)
    data = raw.get("items", [])
    if isinstance(data, dict):
        entries = [{"key": k, **(v if isinstance(v, dict) else {"text": v})}
                   for k, v in data.items()]
    elif isinstance(data, list):
        entries = [e for e in data if isinstance(e, dict)]
    else:
        entries = []
    keyed = {str(item.get("key", "")).strip(): item for item in entries}
    items = []
    invalid_count = 0
    for key in fields_for(mode):
        item = keyed.get(key, {})
        text = _one_sentence(item.get("text"))
        evidence = []
        for candidate in item.get("evidence", []) if isinstance(item.get("evidence"), list) else []:
            if not isinstance(candidate, dict):
                continue
            page = candidate.get("page")
            # 외부 응답의 타입을 보수적으로 해석. 문자열 형태 숫자는 허용.
            if isinstance(page, str) and page.isdecimal():
                page = int(page)
            quote = str(candidate.get("quote") or "").strip()[:220]
            is_valid, label = verify_quote(pdf_doc, page, quote, abstract)
            if page is not None and allowed_pages is not None and page not in allowed_pages:
                is_valid = False  # 모델이 보지 않은 페이지를 근거로 주장하는 경우 차단
            if is_valid:
                evidence.append({"page": page, "quote": quote, "status": label})
            else:
                invalid_count += 1
            if len(evidence) >= 2:
                break
        items.append({"key": key, "text": text, "evidence": evidence})
    return {"mode": mode, "items": items,
            "unverified_quote_count": invalid_count,
            "evidence_verified_count": sum(len(i["evidence"]) for i in items)}


def analysis_summary(result: dict) -> dict[str, str]:
    return {i["key"]: i["text"] for i in result.get("items", [])}


def analysis_lines(result: dict) -> str:
    fields = fields_for(result.get("mode", ASSIGNMENT))
    summaries = analysis_summary(result)
    return "\n".join(f"{idx}. {key}: {summaries.get(key, MISSING)}"
                     for idx, key in enumerate(fields, 1))


def estimate_ai_calls(pdf_doc: PdfDocument | None) -> int:
    if pdf_doc is None:
        return 1
    packets = build_evidence_packets(pdf_doc)
    return len(packets) + 1 if sum(len(packet.text) for packet in packets) > 23000 else 1


def analyze_paper(api_key: str, title: str, mode: str,
                  pdf_doc: PdfDocument | None = None, abstract: str = "",
                  model: str = "gpt-4.1-mini", ask_json: Callable | None = None) -> dict:
    """짧은 PDF/초록 1회, 긴 PDF 4개 구간 요약+최종 통합(최대 5회).

    비용은 사용자 개인 OpenAI 키에 청구되며 이 함수는 키를 파일에 기록하지 않는다.
    원문 근거 검증은 페이지와 문구 일치만 보증하고 의미적 타당성을 보증하지 않는다.
    """
    if mode not in (ASSIGNMENT, READING):
        raise ValueError("요약 목적을 선택하세요.")
    if not (api_key or "").strip() and ask_json is None:
        raise ValueError("왼쪽 개인 AI 설정에서 OpenAI API 키를 입력하세요.")
    if model not in SUPPORTED_MODELS:
        raise ValueError("허용되지 않은 OpenAI 모델입니다.")
    if len((abstract or "").strip()) < 40 and (pdf_doc is None or pdf_doc.char_count < 40):
        raise ValueError("분석 가능한 40자 이상의 초록 또는 텍스트 PDF가 필요합니다.")

    ask = ask_json or _make_ask_json(api_key.strip(), model)
    packets = build_evidence_packets(pdf_doc) if pdf_doc is not None else []
    selected_texts = [packet.text for packet in packets]
    supplied_abstract = "\n[사용자가 직접 제공한 초록/발췌]\n" + abstract.strip()[:6000] if abstract.strip() else ""
    content_chars = sum(len(s) for s in selected_texts)
    call_count = 0

    if content_chars > 23000:
        # 원문 일부를 나누어 발췌하고, 직접 인용문이 페이지에 실제 존재할 때만 채택.
        verified_facts = []
        for packet in packets:
            raw_stage = _as_json(ask(
                STAGE_SYSTEM_PROMPT,
                f"논문 제목(서지 표식): {title[:250]}\n"
                f"구간 이름: {packet.section}\n원문 (수정하지 말고 그대로 인용):\n{packet.text}",
                max_tokens=900,
            ))
            call_count += 1
            for fact in raw_stage.get("facts", []) if isinstance(raw_stage.get("facts"), list) else []:
                if not isinstance(fact, dict):
                    continue
                page = fact.get("page")
                if isinstance(page, str) and page.isdecimal():
                    page = int(page)
                quote = str(fact.get("quote", ""))[:180]
                matched, _ = verify_quote(pdf_doc, page, quote)
                if matched and page in packet.page_numbers and len(verified_facts) < 32:
                    verified_facts.append({"section": packet.section,
                                           "page": page, "quote": quote,
                                           "claim": _normalized_one_line(fact.get("claim", ""))})
        facts_json = json.dumps(verified_facts, ensure_ascii=False)
        # 단순 텍스트 유사 인용 검증 후에도 사용자가 의미를 다시 확인해야 함.
        # 검증 근거가 한 건도 없으면 첫 단계에서 정보를 못 얻었음을 숨기지 않음.
        if verified_facts:
            evidence = ("[4개 구간의 PDF 원문 일치 구절만 채택]\n" + facts_json
                        + supplied_abstract)
        else:
            # 원문이 섞인 구간별 추출 결과를 신중하게 제공, 허위 근거 없이 처리.
            evidence = ("[PDF 구간별 발췌, 중간 단계 인용 검증 0건]\n"
                        + "\n\n".join(t[:4800] for t in selected_texts) + supplied_abstract)
        strategy = "긴 PDF · 구간별 AI 발췌 후 종합"
    else:
        evidence = ("\n\n".join(selected_texts) + supplied_abstract)[:36000]
        strategy = "핵심 구간 선별 · 단일 AI 분석" if pdf_doc else "입력 초록 · 단일 AI 분석"

    raw_final = _as_json(ask(
        final_system_prompt(mode),
        f"논문 제목(서지 표식): {title[:350]}\n"
        "아래의 학술 내용에만 근거하여 요약하라. 없는 내용은 채우지 말라.\n\n" + evidence,
        max_tokens=2400 if mode == READING else 1900,
    ))
    call_count += 1
    allowed_pages = {p for packet in packets for p in packet.page_numbers}
    result = normalize_analysis(raw_final, mode, pdf_doc, abstract,
                                allowed_pages=allowed_pages if pdf_doc else None)
    result.update({
        "model": model, "ai_calls": call_count, "strategy": strategy,
        "coverage": extraction_coverage(pdf_doc, packets) if pdf_doc else {
            "total_pages": 0, "text_pages": 0, "chars_extracted": len(abstract.strip()),
            "selected_pages": [], "selected_page_count": 0,
            "clipped_pages": 0, "sections": {}},
    })
    return result
