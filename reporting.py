"""원우별 연구 결과를 PDF/Excel 파일(메모리)로 작성."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from paperlab import (API_NAME, SOURCE_URL, SUMMARY_FIELDS,
                      calculate_trends, make_reference)


def _excel_safe(value):
    """외부 데이터의 셀 수식 실행 방지 + Excel 셀 길이 제한."""
    if isinstance(value, str):
        value = value[:32000]
        if value.lstrip().startswith(("=", "+", "-", "@")):
            return "'" + value
    return value


def create_excel(df: pd.DataFrame, keyword: str, summary: dict | None = None,
                 chosen_paper: dict | None = None,
                 data_origin: str = "국회도서관 API 검색 서지정보") -> bytes:
    """과제 부록용 다중 시트 Excel 생성(실제 API 결과만 저장)."""
    year_df, type_df = calculate_trends(df)
    references = pd.DataFrame([
        {"번호": i + 1, "참고문헌(임시)": make_reference(row),
         "관리번호": row.get("controlno", ""), "출처": data_origin}
        for i, row in enumerate(df.to_dict("records"))
    ])
    source = pd.DataFrame([
        {"항목": "데이터 출처", "내용": data_origin},
        {"항목": "원천 출처", "내용": SOURCE_URL if "API" in data_origin else "사용자 직접 제공"},
        {"항목": "실행 검색어", "내용": keyword},
        {"항목": "통계 범위", "내용": "수집한 검색 결과만 해당하며 전체 연구 동향이 아님"},
        {"항목": "참고문헌 유의", "내용": "서지정보 기반 임시 표기. 제출 전 원문·서지사항 검증 필요"},
        {"항목": "AI 유의", "내용": "AI 출력은 원문과 대조하여 사실 확인 필요"},
    ])
    summary_rows = []
    if summary:
        summary_rows = [{"항목": key, "AI 요약": summary.get(key, "확인 불가")}
                        for key in SUMMARY_FIELDS]
    if chosen_paper:
        summary_rows.insert(0, {"항목": "선택 논문", "AI 요약": chosen_paper.get("자료명/저자사항", "")})
    sheets = {
        "검색결과": df,
        "연도별통계": year_df,
        "유형별통계": type_df,
        "참고문헌": references,
        "AI요약": pd.DataFrame(summary_rows, columns=["항목", "AI 요약"]),
        "출처_주의사항": source,
    }
    memory = BytesIO()
    with pd.ExcelWriter(memory, engine="openpyxl") as writer:
        for name, data in sheets.items():
            if data.empty and len(data.columns) == 0:
                data = pd.DataFrame({"안내": ["수집 자료가 없습니다."]})
            data = data.map(_excel_safe) if hasattr(data, "map") else data.applymap(_excel_safe)
            data.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            ws.sheet_view.showGridLines = False
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            ws.row_dimensions[1].height = 27
            for cell in ws[1]:
                cell.font = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=11)
                cell.fill = PatternFill("solid", fgColor="17365D")
                cell.alignment = Alignment(vertical="center")
            for col_idx, col_cells in enumerate(ws.columns, 1):
                letter = get_column_letter(col_idx)
                col_name = str(ws.cell(1, col_idx).value or "")
                target_width = 58 if col_name in ["자료명/저자사항", "참고문헌(임시)", "AI 요약", "내용"] else 22
                ws.column_dimensions[letter].width = target_width
                for cell in list(col_cells)[1:]:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    cell.font = Font(name="맑은 고딕", size=10, color="16724F")
                    if cell.row % 2 == 0:
                        cell.fill = PatternFill("solid", fgColor="F3F7FB")
            # 많은 논문에 긴 제목이 있을 수 있으므로 행 높이 과도 확장 방지
            for r in range(2, ws.max_row + 1):
                ws.row_dimensions[r].height = 31 if name != "참고문헌" else 48
    return memory.getvalue()


def _register_korean_font() -> tuple[str, str]:
    """Streamlit Linux packages.txt의 fonts-nanum, Windows 맑은 고딕 지원."""
    for regular, bold in [
        ("/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/malgunbd.ttf"),
        ("/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
         "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf"),
    ]:
        if Path(regular).exists():
            if "PaperKorean" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("PaperKorean", regular))
                pdfmetrics.registerFont(TTFont("PaperKoreanBold", bold if Path(bold).exists() else regular))
            return "PaperKorean", "PaperKoreanBold"
    # 임베디드 한글 폰트를 찾지 못한 경우 CID 폰트로 대체
    if "HYGothic-Medium" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    return "HYGothic-Medium", "HYGothic-Medium"


def _para(text: object, style: ParagraphStyle) -> Paragraph:
    value = escape(str(text if text is not None else ""))
    value = value.replace("\n", "<br/>")
    return Paragraph(value, style)


def create_pdf_report(
    keyword: str,
    metadata: dict,
    selected_paper: dict,
    summary: dict,
    stats_df: pd.DataFrame,
    type_df: pd.DataFrame,
    evidence_source: str,
    data_origin: str = "국회도서관 API 검색 서지정보",
) -> bytes:
    """공식 표지 + 연구 통계 + 6개 항목 요약 보고서(PDF)."""
    regular, bold = _register_korean_font()
    ink = colors.HexColor("#20364E")
    muted = colors.HexColor("#506478")
    accent = colors.HexColor("#1E7186")
    light = colors.HexColor("#ECF5F7")
    doc_buffer = BytesIO()
    doc = SimpleDocTemplate(doc_buffer, pagesize=A4,
                            leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            title="논문 검색 및 AI 분석 과제 보고서")
    styles = {
        "title": ParagraphStyle("report_title", fontName=bold, fontSize=22, leading=34,
                                textColor=ink, alignment=TA_CENTER, spaceAfter=10),
        "subtitle": ParagraphStyle("report_subtitle", fontName=regular, fontSize=11,
                                   leading=18, textColor=muted, alignment=TA_CENTER),
        "section": ParagraphStyle("report_section", fontName=bold, fontSize=13,
                                  leading=20, textColor=accent, spaceBefore=8, spaceAfter=6),
        "body": ParagraphStyle("report_body", fontName=regular, fontSize=9.6,
                               leading=15.5, textColor=ink, spaceAfter=4, wordWrap="CJK"),
        "small": ParagraphStyle("report_small", fontName=regular, fontSize=8.5,
                                leading=14, textColor=muted, wordWrap="CJK"),
        "label": ParagraphStyle("report_label", fontName=bold, fontSize=9.4,
                                leading=16, textColor=ink, wordWrap="CJK"),
    }
    body = []
    body.append(Spacer(1, 38 * mm))
    body.append(_para("연구자료 검색 · 분석 과제", styles["title"]))
    body.append(_para("국회도서관 자료검색 API 활용 및 AI 요약 보고서", styles["subtitle"]))
    body.append(Spacer(1, 14 * mm))
    body.append(HRFlowable(width="100%", thickness=1.5, color=accent))
    body.append(Spacer(1, 18 * mm))
    form_items = [
        ("학교", metadata.get("school", "")),
        ("대학원 / 전공", metadata.get("department", "")),
        ("교과목", metadata.get("course", "")),
        ("담당교수", metadata.get("professor", "")),
        ("제출자", metadata.get("student", "")),
        ("제출일", metadata.get("date", date.today().isoformat())),
        ("검색 주제", keyword),
    ]
    table_data = [[_para(k, styles["label"]), _para(v or "(미입력)", styles["body"])]
                  for k, v in form_items]
    cover_table = Table(table_data, colWidths=[40 * mm, 111 * mm], hAlign="CENTER")
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F4F8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 11),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 0.45, colors.HexColor("#DCE5ED")),
    ]))
    body.append(cover_table)
    body.append(PageBreak())

    body.append(_para("1. 연구 및 검색 개요", styles["section"]))
    body.append(_para(f"검색어: {keyword}", styles["body"]))
    body.append(_para(f"자료 출처: {data_origin}" + (f" ({SOURCE_URL})" if "API" in data_origin else ""), styles["body"]))
    body.append(_para("통계는 이번에 수집한 검색 결과에만 해당합니다. 전체 학술 연구 동향으로 일반화할 수 없습니다.", styles["small"]))
    body.append(_para("2. 선택한 논문 서지정보", styles["section"]))
    for field, label in [("자료명/저자사항", "자료명/저자사항"),
                         ("발행자", "발행자"), ("발행년", "발행연도"),
                         ("DB", "자료유형"), ("controlno", "관리번호")]:
        body.append(_para(f"{label}: {selected_paper.get(field, '확인 불가')}", styles["body"]))

    body.append(_para("3. AI 논문 요약 (6개 항목)", styles["section"]))
    rows = []
    for i, key in enumerate(SUMMARY_FIELDS, 1):
        rows.append([_para(f"{i}. {key}", styles["label"]),
                     _para(summary.get(key, "확인 불가"), styles["body"])])
    sum_table = Table(rows, colWidths=[36 * mm, 121 * mm], repeatRows=0, hAlign="LEFT")
    sum_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), light),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#DBE7ED")),
    ]))
    body.append(sum_table)
    body.append(Spacer(1, 6 * mm))
    body.append(_para("분석 근거: " + evidence_source, styles["small"]))

    body.append(_para("4. 수집 자료 통계", styles["section"]))
    if not stats_df.empty:
        text = ", ".join(f"{r['발행연도']}년 {r['건수']}건" for r in stats_df.to_dict("records"))
        body.append(_para("발행연도별: " + text[:1000], styles["body"]))
    if not type_df.empty:
        text = ", ".join(f"{r['자료유형']} {r['건수']}건" for r in type_df.to_dict("records"))
        body.append(_para("자료유형별: " + text[:1000], styles["body"]))
    body.append(_para("5. 참고문헌 및 검증 유의사항", styles["section"]))
    body.append(_para(make_reference(selected_paper), styles["body"]))
    body.append(_para(
        "이 참고문헌은 API에서 제공하는 서지정보로 자동 생성한 임시 표기입니다. "
        "저자명·논문명·학술지·페이지·DOI와 인용 형식은 제출 전 원문에서 확인하세요.", styles["small"]))
    body.append(Spacer(1, 3 * mm))
    body.append(_para(
        "본 요약은 AI 생성 문장입니다. 제공한 초록/PDF의 발췌 부분에 근거하며, "
        "원문 전체의 정확성·일관성을 보장하지 않습니다. 표절과 저작권 규정을 준수하세요.", styles["small"]))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(muted)
        canvas.drawRightString(A4[0] - 22 * mm, 12 * mm, f"{document.page}")
        canvas.restoreState()

    doc.build(body, onFirstPage=footer, onLaterPages=footer)
    return doc_buffer.getvalue()
