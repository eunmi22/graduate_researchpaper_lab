"""한국교육학술정보원 RISS 종합목록 *기관별 서지 구축 통계* 전용 모듈.

주의: 이 API는 논문 제목/저자/초록 검색 API가 아닙니다.
관리자가 Swagger의 GET 전체 URL을 RISS_API_URL로 설정해야만 호출합니다.
"""

from __future__ import annotations

from io import BytesIO
from urllib.parse import urlsplit, unquote
import re

import pandas as pd
import requests

RISS_SOURCE_URL = "https://www.data.go.kr/data/15071949/fileData.do"
RISS_NAME = "한국교육학술정보원_RISS 종합목록"
CANONICAL_COLUMNS = ["기관코드", "조사년도", "국내 구축건수", "국외 구축건수", "합계 구축건수"]


class RissCatalogError(Exception):
    """외부 응답 본문이나 인증키를 포함하지 않는 간결한 오류."""


def validate_endpoint(endpoint: str) -> str:
    """비밀 키를 외부 도메인으로 보내지 않도록 공식 API 도메인만 허용."""
    address = (endpoint or "").strip()
    parts = urlsplit(address)
    if (parts.scheme != "https" or parts.hostname != "api.odcloud.kr"
            or parts.username or parts.password or parts.port is not None
            or parts.query or parts.fragment
            or not re.fullmatch(r"/api/\d+/v1/[A-Za-z0-9:._~-]+", parts.path)):
        raise ValueError(
            "RISS_API_URL은 승인된 Swagger에서 복사한 "
            "https://api.odcloud.kr/api/숫자/v1/GET경로 전체 주소여야 합니다. "
            "인증키나 ?serviceKey= 쿼리는 포함하지 마세요."
        )
    return address


def clean_key(value: str) -> str:
    if not (value or "").strip():
        raise ValueError("DATA_GO_KR_API_KEY 인증키가 설정되지 않았습니다.")
    return unquote(value.strip())


def _strip_header(value: object) -> str:
    return re.sub(r"[\s_./()（）-]+", "", str(value or "").strip("\ufeff")).lower()


def _normalized_fields(record: dict) -> dict:
    fields = {_strip_header(key): value for key, value in record.items()}

    def pick(*aliases):
        for alias in aliases:
            found = fields.get(_strip_header(alias))
            if found is not None:
                return found
        return ""

    return {
        "기관코드": pick("기관코드", "기관 코드", "기관ID", "기관 아이디"),
        "조사년도": pick("조사년도", "조사연도", "년도", "연도"),
        "국내 구축건수": pick("데이터 국내 구축건수", "MARC 데이터 국내 구축건수", "국내 구축건수"),
        "국외 구축건수": pick("데이터 국외 구축건수", "MARC 데이터 국외 구축건수", "국외 구축건수"),
    }


def normalize_riss_rows(rows: list[dict]) -> tuple[pd.DataFrame, list[str]]:
    """실제 응답 컬럼을 확인해 의미가 명확한 통계 필드로 정규화한다."""
    raw_df = pd.DataFrame(rows)
    if raw_df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS), []
    if not all(isinstance(row, dict) for row in rows):
        raise RissCatalogError("RISS 응답의 data 항목이 객체 목록이 아닙니다.")

    found = {_strip_header(name) for name in raw_df.columns}
    field_aliases = {
        "기관코드": ["기관코드", "기관 코드", "기관ID", "기관 아이디"],
        "조사년도": ["조사년도", "조사연도", "년도", "연도"],
        "국내 구축건수": ["데이터 국내 구축건수", "MARC 데이터 국내 구축건수", "국내 구축건수"],
        "국외 구축건수": ["데이터 국외 구축건수", "MARC 데이터 국외 구축건수", "국외 구축건수"],
    }
    missing = [name for name, aliases in field_aliases.items()
               if not any(_strip_header(a) in found for a in aliases)]
    if missing:
        # 형식이 다른 API를 받았는데 0으로 채워 통계를 만들지 않습니다.
        raise RissCatalogError(
            "RISS 응답 컬럼이 공식 설명과 다릅니다. 확인이 필요한 항목: "
            + ", ".join(missing)
            + " · 응답에 존재하는 컬럼명: "
            + ", ".join(str(c) for c in raw_df.columns[:12])
        )

    normalized = pd.DataFrame([_normalized_fields(row) for row in rows])
    for key in ("기관코드", "조사년도"):
        normalized[key] = normalized[key].fillna("").astype(str).str.strip()
        normalized[key] = normalized[key].replace({"nan": "", "None": ""})
    for key in ("국내 구축건수", "국외 구축건수"):
        series = normalized[key].fillna("").astype(str).str.replace(",", "", regex=False).str.strip()
        normalized[key] = pd.to_numeric(series, errors="coerce")

    normalized["합계 구축건수"] = normalized[["국내 구축건수", "국외 구축건수"]].sum(
        axis=1, min_count=1
    )
    return normalized[CANONICAL_COLUMNS], list(map(str, raw_df.columns))


def _parse_response(payload: object) -> tuple[int, list[dict]]:
    if not isinstance(payload, dict):
        raise RissCatalogError("RISS 응답은 JSON 객체여야 합니다.")
    if "data" not in payload:
        raise RissCatalogError("RISS 응답에 data 배열이 없습니다. 승인된 API 경로를 확인하세요.")
    records = payload["data"]
    if not isinstance(records, list):
        raise RissCatalogError("RISS 응답의 data가 배열이 아닙니다.")
    if not all(isinstance(row, dict) for row in records):
        raise RissCatalogError("RISS 자료는 객체 목록이어야 합니다.")
    try:
        total = int(payload.get("totalCount") or payload.get("matchCount") or len(records))
    except (TypeError, ValueError):
        total = len(records)
    return total, records


def fetch_riss_catalog(api_key: str, endpoint: str, pages: int = 3,
                       per_page: int = 100, session=None) -> tuple[int, pd.DataFrame, list[str]]:
    """승인된 odcloud GET 엔드포인트에서 JSON 페이지를 받아 통계를 생성한다.

    공식 데이터가 기관/연도별 서지 구축 현황이므로 개별 논문으로 취급하지 않는다.
    """
    url = validate_endpoint(endpoint)
    key = clean_key(api_key)
    if not (1 <= pages <= 10 and 1 <= per_page <= 100):
        raise ValueError("페이지 수는 1~10, 페이지당 건수는 1~100으로 제한합니다.")
    client = session if session is not None else requests
    combined = []
    overall_total = 0
    for page in range(1, pages + 1):
        params = {
            "page": page, "perPage": per_page, "returnType": "JSON",
            "serviceKey": key,
        }
        try:
            response = client.get(url, params=params, timeout=(6, 20))
        except requests.RequestException as exc:
            # 요청 URL에 포함된 serviceKey가 예외 문자열에 들어갈 수 있어 출력 금지.
            raise RissCatalogError(f"RISS API 통신 실패 ({type(exc).__name__}).") from None
        if response.status_code != 200:
            raise RissCatalogError(
                f"RISS API HTTP {response.status_code} 오류. "
                "Swagger GET 경로와 서비스키 승인 상태를 확인하세요."
            )
        try:
            payload = response.json()
        except ValueError:
            raise RissCatalogError("RISS가 JSON이 아닌 응답을 보냈습니다. 요청 경로를 확인하세요.") from None
        count, records = _parse_response(payload)
        overall_total = count
        combined.extend(records)
        if not records or len(combined) >= count or len(records) < per_page:
            break
        if len(combined) > 1000:
            raise RissCatalogError("한 번에 수집할 수 있는 최대 1,000건을 초과했습니다.")
    df, fields = normalize_riss_rows(combined)
    return overall_total, df, fields


def summarize_riss(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """조회 *행* 기반 통계. 동일 기관/연도 자료의 중복은 자동 삭제하지 않음."""
    if df.empty:
        year_columns = ["조사년도", "기관기록 수", "국내 구축건수", "국외 구축건수", "합계 구축건수"]
        return pd.DataFrame(columns=year_columns), pd.DataFrame(columns=["기관코드"] + year_columns[2:])
    year_stats = (df.groupby("조사년도", dropna=False, as_index=False)
                  .agg(**{
                      "기관기록 수": ("기관코드", "size"),
                      "국내 구축건수": ("국내 구축건수", lambda s: s.sum(min_count=1)),
                      "국외 구축건수": ("국외 구축건수", lambda s: s.sum(min_count=1)),
                      "합계 구축건수": ("합계 구축건수", lambda s: s.sum(min_count=1)),
                  }).sort_values("조사년도"))
    by_org = (df.groupby("기관코드", dropna=False, as_index=False)
              .agg(**{
                  "국내 구축건수": ("국내 구축건수", lambda s: s.sum(min_count=1)),
                  "국외 구축건수": ("국외 구축건수", lambda s: s.sum(min_count=1)),
                  "합계 구축건수": ("합계 구축건수", lambda s: s.sum(min_count=1)),
              }).sort_values("합계 구축건수", ascending=False, na_position="last"))
    return year_stats, by_org


def make_riss_excel(raw: pd.DataFrame, yearly: pd.DataFrame,
                    by_org: pd.DataFrame) -> bytes:
    """RISS 통계 3개 시트와 출처를 포함한 Excel 파일."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        raw.to_excel(writer, sheet_name="수집원본", index=False)
        yearly.to_excel(writer, sheet_name="연도별통계", index=False)
        by_org.to_excel(writer, sheet_name="기관별통계", index=False)
        pd.DataFrame([
            {"구분": "데이터명", "내용": RISS_NAME},
            {"구분": "출처", "내용": RISS_SOURCE_URL},
            {"구분": "주의", "내용": "기관별 서지 구축 통계이며 개별 논문 검색 결과가 아닙니다."},
            {"구분": "분석범위", "내용": "API에서 이번에 수집한 페이지의 기록에 한정됩니다."},
        ]).to_excel(writer, sheet_name="출처및유의사항", index=False)
        from openpyxl.styles import Alignment, Font, PatternFill
        for worksheet in writer.book.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.sheet_view.showGridLines = False
            worksheet.auto_filter.ref = worksheet.dimensions
            for cell in worksheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="213D62")
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            worksheet.row_dimensions[1].height = 28
            for col in worksheet.columns:
                letter = col[0].column_letter
                max_len = max(min(len(str(c.value or "")), 48) for c in col[:min(60, len(col))])
                worksheet.column_dimensions[letter].width = max(15, min(max_len + 3, 48))
                for cell in col[1:]:
                    cell.alignment = Alignment(vertical="center", wrap_text=True)
    return output.getvalue()
