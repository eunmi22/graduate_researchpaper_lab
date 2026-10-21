# 대학원 AI 논문 연구 도우미

> 국회도서관 자료검색 API + RISS 종합목록 통계 API + Streamlit + pandas + 개인 OpenAI API 키 기반 연구/과제 도우미

## 먼저 알아두기

**최신 버전 v2.2**: 과제용 6항목과 논문 읽기용 7문장 요약, PDF 최대 600페이지 전 페이지 텍스트 추출 및 구간별 증거 검증 기능이 추가되었습니다. 긴 PDF는 최대 5회(선택 구간 수에 따라 변동) OpenAI 호출이 발생할 수 있습니다. 실제 연구 결론/원문 페이지의 의미는 사람이 대조해야 합니다.


- **공개 링크**로 대학원 원우들이 함께 이용할 수 있는 Streamlit 웹서비스입니다. 별도의 회원가입·로그인은 구현하지 않았습니다.
- 국회도서관 공공데이터 API 키(`DATA_GO_KR_API_KEY`)는 **운영자가 한 번만 설정**합니다.
- 각 원우는 자신의 **OpenAI API 키를 화면의 암호형 입력창**에 입력합니다. 검색·통계는 개인 OpenAI 키가 없어도 가능합니다.
- 업로드 PDF/초록은 메모리에서 처리되며 별도 DB나 서버 파일에 저장하지 않습니다. 다만 브라우저/Streamlit 서버 세션 내에는 일시적으로 존재하고, AI 요약 시 해당 텍스트는 OpenAI API로 전송됩니다. **저작권·개인정보·소속 대학원의 연구윤리 기준을 확인**해야 합니다.
- 별도의 결제 설정이 필요할 수 있으며, **OpenAI API는 ChatGPT 구독과 별도로 과금**될 수 있습니다.

## 기능

| 기능 | 제공 내용 |
|---|---|
| 1. 논문 검색 | 국회도서관 `/searchservice/basic` 통합검색, 최대 5페이지, 자료유형별 필터 |
| 2. AI 요약 | **6항목 과제용 / 7문장 읽기용 선택**, 원문 인용·PDF 페이지 문구 대조 |
| 3. 연구 동향 | 검색해 **수집한** 자료의 발행연도별, 자료유형별 빈도 그래프 |
| 4. 보고서 | 모드별 PDF·Excel·텍스트, 근거 검증 시트 및 연구노트(읽기용) |
| 5. 참고문헌 | 학술지 논문/학위논문/기관 연구보고서 **3종 형식과 서지정보 수동 교정, 누락항목 표시** |
| 6. 표지 | 학교, 대학원/전공, 교과목, 교수, 성명, 제출일 |
| 8. RISS 서지 구축 통계 | 기관·조사년도별 국내/국외 MARC 구축 건수, 차트, Excel (개별 논문 검색 아님) |
| 7. 파일 업로드 | 텍스트 기반 PDF(15MB 이하, 최대 600페이지 전 페이지 추출), 구간 선별 및 초록 보조 입력 |

> API 문서가 보장하는 것은 도서·학위논문·국내외 기사 **목록 서지정보**입니다. 초록·본문을 자동으로 반환하는 API가 아닙니다. 제목만 입력하면 AI가 요약을 만들지 않도록 막았습니다. 스캔 PDF의 OCR은 지원하지 않습니다.

## 폴더 구성

```text
graduate_paper_lab/
├─ app.py                         # Streamlit 메인 화면
├─ ui_helpers.py                  # AI 버튼 비활성화 원인 분리 안내
├─ pdf_analysis.py                 # PDF 전체 텍스트 추출·장별 대표 페이지 선별
├─ prompt_templates.py             # 6항목/7문장 프롬프트
├─ research_ai.py                  # 단계별 AI 분석·PDF 인용 문구 대조
├─ paperlab.py                    # 국회도서관 XML·데이터 분석·OpenAI 처리
├─ riss_catalog.py                # RISS 종합목록 기관별 구축통계 JSON 처리
├─ reporting.py                   # PDF·Excel 보고서
├─ citation_styles.py              # 자료유형별 참고문헌 형식·필수 필드 검증
├─ requirements.txt               # pip 설치 대상
├─ packages.txt                   # Cloud에서 PDF 한글 글꼴 설치
├─ .streamlit/
│  ├─ config.toml                 # 테마·업로드 최대 15MB
│  └─ secrets.example.toml        # 배포용 비밀 값 형식(실제 키 없음)
├─ .env.example                   # 로컬 환경변수 예시(실제 키 없음)
├─ .gitignore                     # 실제 비밀 키 추적 금지
├─ API_실습_검증.ipynb             # 수업 제출용 국회도서관 노트북
├─ RISS_API_실습_검증.ipynb        # RISS 검증용 주피터 노트북
├─ RISS_추가기능_안내.md           # RISS 추가 설정 및 이용 안내
└─ tests/test_paperlab.py         # API 없이 검사 가능한 단위 테스트
```

## 화면 구성 (좌측 입력 / 우측 결과) - 개편판

| 왼쪽 사이드바: 입력/설정 | 오른쪽 메인화면: 검색 결과/다운로드 |
|---|---|
| 논문 주제 검색어, 검색 대상, 자동 재검색, 검색 페이지 수/건수, 검색 실행 버튼 | **검색 결과** 탭: 논문 목록, 원 검색어·재검색어, API 건수, 오류 진단 |
| RISS 통계 페이지 수 및 불러오기(별도 접이식) | **RISS 서지통계** 탭: 기관별·조사년도별 국내/국외 MARC 구축 건수, 통계·Excel |
| 검색된 자료 유형 필터 | **논문 AI 요약** 탭: 6항목/7문장 선택, PDF 전체 추출·범위 안내, 키 안내, 원문 근거 확인 |
| 원우 개인 OpenAI API 키, AI 모델 | **연구 동향** 탭: 발행연도/자료유형 차트와 결측·중복 |
| 접이식 **과제 표지 정보**: 학교, 전공, 과목, 제출자, 교수, 날짜 | **과제 보고서** 탭: 표지, 참고문헌 유형·서지정보 수정, PDF/Excel 다운로드 |
| 이용 순서 간단 안내 | **이용 안내** 탭: 주의사항과 출처 |

검색/과제표지 정보는 별도 페이지로 이동하지 않아도 좌측에서 설정할 수 있습니다. 모바일에서는 Streamlit 사이드바를 열어 입력한 뒤 오른쪽 결과를 확인합니다.

## 1. Windows Anaconda Prompt에서 로컬 실행

1. `graduate_paper_lab` 폴더를 예를 들어 `C:\Users\ASUS\Python\graduate_paper_lab`로 복사합니다.
2. Anaconda Prompt를 실행하고 폴더로 이동합니다.

```bat
cd /d "C:\Users\ASUS\Python\graduate_paper_lab"
```

3. 패키지를 설치합니다.

```bat
python -m pip install -r requirements.txt
```

4. `.env.example`을 복사해 `.env` 파일을 만들고, 발급받은 **공공데이터포털 키**를 설정합니다.

```ini
DATA_GO_KR_API_KEY=본인의_공공데이터포털_인증키
```

5. 앱을 실행합니다.

```bat
python -m streamlit run app.py
```

브라우저에 로컬 주소가 나타납니다(보통 `http://localhost:8501`). `http://localhost:8501`은 로컬 실행주소이지 배포 주소가 아닙니다.

### Jupyter로 과제 제출 실습

- `API_실습_검증.ipynb`를 같은 폴더에서 Jupyter Notebook으로 열어 순서대로 실행합니다.
- `assert` 검증 셀을 별도로 넣었습니다.
- API로 실제 검색을 성공적으로 수행한 경우에만 `논문_API_실습_분석.xlsx` 파일이 생성됩니다.

## 2. GitHub에 업로드

1. GitHub에 새 저장소를 만들고 이 프로젝트 폴더의 파일들을 업로드합니다.
2. **실제 `.env`와 `.streamlit/secrets.toml`은 절대 업로드하지 마세요.** `.gitignore`에 제외되어 있습니다.
3. `README.md`, `app.py`, `requirements.txt`, `packages.txt`, `.streamlit/config.toml` 등이 루트 기준으로 있어야 합니다.
4. GitHub에 프로젝트를 업로드한 후 URL을 확인합니다.

## 3. Streamlit Community Cloud에 공개 배포

1. [https://share.streamlit.io](https://share.streamlit.io)에 로그인한 후 **Create app**을 선택합니다.
2. GitHub의 Repository, Branch(예: `main`), Main file path(`app.py`)를 지정합니다.
3. **Advanced settings → Secrets**에 다음을 입력합니다. 개인 OpenAI API 키는 이곳에 넣지 않습니다.

```toml
DATA_GO_KR_API_KEY = "발급받은_공공데이터포털_인증키"
```

4. Python 버전은 **3.12**로 선택하는 것을 권장합니다.
5. **Deploy**를 클릭합니다. 성공하면 `https://...streamlit.app` 형태의 주소가 생기며 원우에게 공유하면 됩니다.
6. `requirements.txt`로 Python 패키지를 설치하고, `packages.txt`의 `fonts-nanum`으로 PDF 한글 폰트를 설치합니다.

- [Streamlit 공식 배포 안내](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Streamlit 공식 Secrets 설정](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management)
- [Streamlit 공식 패키지 설치](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)

## 4. 실제 공공데이터 API 오류 점검

| 메시지 | 조치 |
|---|---|
| `NO_OPENAPI_SERVICE_ERROR` / 12 | `/searchservice`가 아닌 **`/searchservice/basic`**으로 호출하는지 확인 |
| 인증되지 않은 키 / 30 | 서비스 신청이 승인되었는지, 인코딩/디코딩 키가 올바른지 확인 |
| HTTP 400/500 | API 주소·필수 파라미터 `serviceKey,pageno,displaylines,search` 확인 |
| API 응답 정상, 검색 0건 | 다른 검색어 입력 또는 **검색 결과가 0건이면 핵심 단어로 재검색** 체크. 예: `데이터베이스 포렌식` → `포렌식` |
| API 전체 건수 양수, 수집자료 0건 | 오른쪽 **API 검색 진단** 펼쳐 건수 확인. 데이터 제공 XML 구조 변경 여부 점검 |
| SSL/HTTPS 오류 | 제공기관에 HTTPS 지원 여부 문의. **인증키를 평문 HTTP로 보내도록 자동 폴백하지 않음** |
| AI 401/429 | 원우 개인 OpenAI 키, 결제/사용 한도 확인 |
| PDF 글자 추출 실패 | 스캔 PDF일 수 있음. 초록을 직접 복사해 붙여넣기 |

**API 출처**
- 이름: 국회 국회도서관_자료검색 서비스
- 제공처: [공공데이터포털](https://www.data.go.kr/)
- 문서: 사용자가 제공한 `국회도서관_참고기술문서양식 -자료검색서비스_20230502.pdf`, 3~9쪽
- 통합검색 엔드포인트: `https://apis.data.go.kr/9720000/searchservice/basic`
- 호출 변수: `serviceKey`, `pageno`, `displaylines`, `search=전체,키워드`
- 문서에 기록된 원래 URL은 `http://.../basic`; 본 앱은 키 보호를 위해 **HTTPS를 우선 사용하며 HTTPS 지원 여부는 실제 서버에서 검증해야 합니다**.


### 검색 결과가 0건일 때 (2026-10-20 수정)

- 오른쪽 검색결과 탭의 메시지에서 **실제 검색된 단어**와 건수를 확인합니다.
- 왼쪽 **검색 대상**: 전체/자료명/키워드 중 선택할 수 있습니다(공식 API 검색항목).
- **검색 결과가 0건이면 핵심 단어로 재검색**이 기본 선택됩니다. 예: `데이터베이스 포렌식` → `포렌식`. 재검색 결과는 원래 구문과 동일한 검색이 아님을 화면에 표시합니다.
- 검색 결과 아래 **API 검색 진단**에 시도한 검색어별 API 전체 건수, 수집 건수가 표시됩니다. **인증키는 표시하지 않습니다.**
- 인증키 로드 메시지 자체는 실제 HTTP 요청 성공을 의미하지 않습니다. 사용자가 검색 버튼을 눌러 결과를 확인해야 합니다.
- API가 정상 결과 0건을 반환한다면 소스코드 수정만으로 논문을 만들어낼 수는 없습니다. `포렌식`, `디지털 포렌식` 등 실제 검색어를 다양하게 시도하거나, 논문 PDF 업로드 분석을 이용하세요.

## 5. 현실적 운영 한계 및 확장 방향

- **운영자 API 호출량:** 공개 사용자 모두가 공공데이터포털 키 한 개를 사용하기 때문에 쿼터 소진 위험이 있습니다. 세션별 시간당 12회 제한을 두었지만 로그인/공유 스토리지 없이 사용자가 새 세션을 열면 우회할 수 있습니다. 수강생이 많아지면 인증과 중앙 rate limiting 도입을 권장합니다.
- **데이터 정확성:** 기초자료 검색은 책/학위논문/학술기사를 함께 반환할 수 있으며, 그 결과만으로 국내외 논문 전체 연구동향을 추정할 수 없습니다.
- **출처 정리:** API의 `자료명/저자사항` 결합 필드는 자동으로 APA 서지사항으로 분해하기 어렵습니다. 그래서 관리번호와 불완전한 서지 필드를 보존해 원문 확인 후 완성하도록 했습니다.
- **파일 개인정보:** 서버 파일/DB에 별도 저장하지 않지만, Streamlit 앱 서버가 요청을 처리하므로 높은 기밀성의 PDF는 업로드하지 마세요. 공개 링크는 서비스 접근만 공개하는 것이며 회원 인증이나 비밀성 보장이 아닙니다.
- **AI 비용:** 개인별 키는 입력된 요청에만 쓰이고 키가 보고서에 포함되지 않습니다. 사용자는 OpenAI 계정의 이용 한도와 결제를 직접 관리해야 합니다.
- **배포 상태:** 제공 코드는 배포용 프로젝트이며 **실제 GitHub push/Community Cloud 배포는 아직 수행되지 않았습니다.** 발급받은 키와 원우 개인 OpenAI 키를 여기서 대신 이용할 수는 없습니다.

## 6. 로컬 검증

```bat
python -m pip install pytest
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python -m compileall app.py paperlab.py reporting.py
```

단위 테스트는 XML 응답 파싱, HTTP 오류 코드 해석, 참조 텍스트, 통계, 엑셀, 한글 PDF 생성을 검사합니다. 실제 국회도서관/OpenAI 외부 호출은 사용자 환경에서 별도로 확인해야 합니다.

## XML 파싱 보완 및 진단 (2026-10-20)

- 실제 화면에서 `API 전체 263건`이 반환되었으나 자료 목록이 0건으로 표시되는 문제를 보고받았습니다. **인증키가 틀렸다는 근거는 없습니다.**
- `paperlab.py`는 기존 문서 표준 `<record><item><name>/<value>`뿐 아니라 **네임스페이스/대문자 태그, record 내부 직접 필드, 일부 item 컨테이너 변형**을 처리하도록 개선했습니다.
- 다시 검색해도 수집 자료 수가 0건이면, 오른쪽 **API 검색 진단**을 펼쳐 `XML 태그 빈도`와 `XML 요소 경로`를 캡처해 주세요. 해당 진단에는 인증키·요청 URL·논문 본문이 표시되지 않습니다.
- 원문 목록 자체가 제공되지 않은 경우에는 검색 건수만으로 논문 제목을 임의 생성하지 않습니다. 이는 제공기관 응답을 추가로 확인해야 하는 상태입니다.
- 로컬 모의 XML 및 예외처리 테스트를 통과했습니다. 실제 운영 API 응답을 확인한 결과는 아닙니다.
- 이미 배포했다면 **`app.py`와 `paperlab.py` 두 파일을 함께 교체**해야 화면 진단 및 파서가 모두 동작합니다.

## 2026-10-21 업데이트: 검색 결과 20건인데 화면에 0건 표시되는 문제

`DB`(자료유형) 필드가 API 응답에 없거나 비어 있으면 이전 버전은
`No options to select`가 나오고 자료 20건을 모두 숨기는 문제가 있었습니다.

수정 사항:
- 자료유형이 제공되지 않으면 `미분류`로 표시하고 목록은 계속 보여줍니다.
- 자료유형 필터 선택을 모두 해제하면 전체 검색 결과를 보여줍니다.
- `DB` / `db` / `dbname`, `자료명/저자사항` / `논문제목` 등 변형된 필드명을 통일합니다.
- 결과 화면에 제목이 실제 제공된 자료 수를 표시합니다.
- 제목이 여전히 비어 있으면 **API 검색 진단 → 수집된 자료 필드 확인**에서 필드명과 값이 있는 건수를 확인합니다.
- 오른쪽에 `버전 1.4 · 자료유형이 없어도 검색 결과 표시`가 보이면 수정된 `app.py`가 실행 중입니다.

**로컬 환경:** `app.py`, `paperlab.py` 두 파일을 함께 교체한 뒤 Streamlit을 종료하고 재실행합니다.

**Streamlit Cloud:** GitHub에 같은 두 파일을 함께 반영한 후 앱을 새로고침합니다.

> 주의: 데이터 263건은 API 전체 검색 건수이고, 20건은 현재 요청으로 수집한 자료 건수입니다.
> 국회도서관 자료검색 서비스는 도서와 기사도 검색합니다. 모든 결과가 학술 논문이라는 뜻은 아닙니다.
> 실시간 API 응답은 이 오프라인 테스트에서 검증되지 않았습니다.


## 5. 신규 RISS 종합목록 API 연결 (v1.5)

**중요:** RISS 종합목록은 기관별 MARC 서지 구축현황 통계이므로 **논문명·초록 검색 API가 아닙니다.** 기존 국회도서관 논문 검색과 별도의 탭으로 제공됩니다.

공공데이터포털의 Swagger에서 RISS 종합목록 `GET /...` 전체 경로를 확인하고, `.env` 또는 Cloud Secrets에 **`RISS_API_URL`**을 추가해야 합니다.

```toml
DATA_GO_KR_API_KEY = "발급받은_공공데이터포털_인증키"
RISS_API_URL = "https://api.odcloud.kr/api/<실제서비스번호>/v1/uddi:<실제UUID>"
```

경로는 **설명용 형식**입니다. Swagger에 표시된 값으로 교체하세요. 인증키가 서로 다르면 `RISS_API_KEY`도 설정할 수 있습니다. 자세한 과정과 주의사항은 `RISS_추가기능_안내.md`를 참고하세요.

- 오프라인 검증: `python -m pytest -q tests/test_riss_catalog.py`
- 별도 실습: `RISS_API_실습_검증.ipynb`
- 새 화면: 왼쪽 `RISS 서지 구축 통계` 설정 → 오른쪽 `RISS 서지통계` 결과·Excel


## v1.6 - 국회도서관 상세정보 및 원문 확인 기능 (2026-10-21)

- **논문 검색 탭:** 논문 제목 옆 **「📖 상세·원문 확인」** 링크를 누르면 국회도서관의 개별 자료 상세페이지로 이동합니다.
- **논문 AI 요약 탭:** 선택 논문에 대해 `📖 국회도서관 상세·원문 확인` 버튼과 `🔎 Google Scholar에서 공개본 검색` 버튼을 제공합니다.
- 구버전에서 `controlno`가 비고 별도 `제어번호` 필드에 코드가 들어가는 문제를 수정했습니다. `제어번호`를 `controlno`로 통일합니다.
- 검색 API의 응답에 PDF URL이 없으므로 직접 PDF를 다운로드하거나 이용 제한을 우회하는 기능은 없습니다.
- 국회도서관 검색결과에서 「원문보기」가 비활성화된 자료는 현장/협정기관 열람이 필요할 수 있습니다. 열람 가능한 PDF를 이용자가 합법적으로 확보하면 AI 요약 탭에 업로드합니다.
- 국회도서관 공식 이용 안내: https://www.nanet.go.kr/usermadang/etc/infoUseReqView.do
- 국회도서관 FAQ: https://nanet.go.kr/libaryuseinfo/faqServiceList.do
- Streamlit `LinkColumn` 개발 문서: https://docs.streamlit.io/develop/api-reference/data/st.column_config/st.column_config.linkcolumn

### 이 버전에서 교체해야 할 파일

`app.py`, `paperlab.py`를 **같이 교체**하십시오. 기존 `riss_catalog.py`, `reporting.py` 및 RISS 통계 탭 기능은 변경하지 않았습니다.
GitHub에서 배포한 앱의 코드를 변경한 경우 연결된 Streamlit Community Cloud 앱을 새로고침하세요.

### 검증

`python -m pytest tests -q` (오프라인 단위 테스트). 실제 국회도서관 원문 열람 권한은 이용자의 계정/저작권 상태에 따라 달라지므로 자동 검증되지 않습니다.

## v1.7: University dCollection fallback for theses not found in NAL search

- National Assembly Library graduate theses: mandatory deposit under National Assembly Library Act article 7(4), generally within 30 days from publication. The library states universities bulk-submit degree theses. An API result of zero is **not** evidence that a thesis was never deposited or is not held.
- When the public API returns **zero total hits**, the search-results tab expands a university dCollection alternative search panel. If an API parser returns zero rows but total > 0, the fallback does **not** incorrectly assert that the thesis is absent.
- The left sidebar provides a university choice and a title/keyword for fallback. Users can select Korea University, Seoul National University, Yonsei University, Sungkyunkwan University, Pusan National University, or the full official list of dCollection institutions.
- The university button opens a verified institutional dCollection page. The Google button performs a **site-limited web search** (not the institution's search API). Users must confirm the thesis and whether full text is accessible. Other institutions are available through the official institution directory. No PDF scraping or automatic downloading.
- No new API key is needed for external link buttons. Existing NAL API and RISS statistics API remain separate.

Official references:
- National Assembly Library Act article 7: https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0007&lsiSeq=279757&urlMode=lsScJoRltInfoR
- NAL deposit procedure: https://www.nanet.go.kr/usermadang/etc/clView.do
- dCollection: https://www.dcollection.net/common/guideView.do?guideId=000000000001
- Participating universities: https://www.dcollection.net/common/instList.do
- Korea University: https://dc.korea.ac.kr/srch/srchSearch
- Seoul National University: https://dcollection.snu.ac.kr (official SNU library announcements)
- Yonsei University: https://dcollection.yonsei.ac.kr/srch/srchSearch
- Sungkyunkwan University: https://dcollection.skku.ac.kr
- Pusan National University: https://dcollection.pusan.ac.kr (official PNU thesis submission notice)


## v1.8 기록 (v1.9에서 교체)

세종사이버대학교 논문검색 안내 페이지 연결은 기존 임시 설정입니다. v1.9에서는 학교 dCollection의 실제 주소 `https://sjcu.dcollection.net`으로 교체했습니다. 아래의 v1.9 안내가 최신입니다.


## v1.9 - 실사용 키워드 검색과 학회·협회·연구보고서 찾기 (2026-10-21)

### 화면 변경

- **왼쪽 `🏛 대학별 논문·원문 찾기`**: 대학 선택 + 논문 제목/키워드 입력 후 **`🔎 입력 키워드로 검색 결과 열기 ↗`**를 클릭하면 `site:학교dCollection도메인 "키워드"`를 포함한 **Google 외부 검색 결과**가 열립니다.
- 같은 메뉴의 `🏫 학교 dCollection 자료검색 화면 열기 ↗`는 학교 **자체 검색 페이지**만 열며 **키워드를 전달하지 않습니다**. 두 버튼을 혼동하지 않게 명확히 분리했습니다.
- **세종사이버대학교**: 실제 저장소 `https://sjcu.dcollection.net` / 자체 자료검색 화면 `https://sjcu.dcollection.net/srch/srchSearch`로 수정했습니다.
- **왼쪽 `📑 학회·협회·연구보고서 검색`**: 기관/서비스와 키워드를 선택하고 **외부 검색 결과 열기**를 누릅니다.
- **오른쪽 `📑 학회·보고서 검색` 탭**: 선택한 출처 검색 결과 링크, 공식 사이트 링크 및 다른 기관의 검색 결과 링크 표를 제공합니다.

### 검색 지원 기관(기본 제공)

| 출처 | 취급하는 자료 예시 | 검색 방식 |
|---|---|---|
| KCI 한국학술지인용색인 | 학회·학술논문 | Google `site:kci.go.kr` |
| 한국정보보호학회 | 정보보호·포렌식 학술논문 | Google `site:kiisc.or.kr` |
| 한국중견기업연합회 | 협회 정책자료·간행물 | Google `site:fomek.or.kr` |
| KISA 한국인터넷진흥원 | 정보보안 보고서 | Google `site:kisa.or.kr` |
| NIA 한국지능정보사회진흥원 | AI·ICT 정책연구보고서 | Google `site:nia.or.kr` |
| KISTI ScienceON | 논문·국가 R&D 보고서 | Google `site:scienceon.kisti.re.kr` |
| 국회입법조사처 | 입법·정책보고서 | Google `site:nars.go.kr` |
| Google Scholar | 학술자료 통합검색 | Scholar 공식 검색 URL |

### 기술적 범위와 주의사항

- **진짜 외부 웹 검색**: 링크 주소에 키워드와 대상 기관 도메인을 포함하므로, 버튼을 누르면 검색엔진에서 검색이 실행됩니다. 원래 버전처럼 입력만 되고 검색이 실행되지 않는 오해를 바로잡았습니다.
- **앱 내부 API 검색과 다름**: 국회도서관만 승인된 자료검색 API로 Streamlit 내부에 목록을 수집합니다. 대학 저장소/학회·협회 사이트는 검색엔진 결과를 **외부 브라우저 탭**에서 확인합니다. 검색 결과를 pandas에 자동 수집하거나 다운로드하지 않습니다.
- **Google 색인·사이트 운영 제한**: 사이트에 실제 문서가 있어도 구글 색인이 안 되어 검색되지 않을 수 있습니다. 이 경우 해당 기관의 공식 페이지에서 직접 검색하세요. 원문 PDF 공개·무료 제공은 보장되지 않습니다.
- **비밀키 불필요**: 외부 검색 링크에는 DATA_GO_KR_API_KEY 및 개인 OpenAI API 키가 포함되지 않습니다.

### 배포 방법

기존 v1.8 사용자는 `app.py`와 `dcollection_fallback.py`를 교체하고, `external_research.py` **파일을 새로 추가**하세요. 다른 기존 파일은 그대로 유지됩니다. 전체 ZIP으로 배포하는 경우 프로젝트 구조를 유지한 채 GitHub에 업로드하세요.

```bat
cd /d "C:\Users\ASUS\Python\graduate_paper_lab"
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### 검증

```bat
python -m pip install pytest
python -m pytest -q
```

오프라인 단위 테스트는 네트워크와 실제 인증키를 사용하지 않습니다. 실제 검색엔진 결과 개수, 학교 사이트 UI 및 Streamlit Community Cloud 배포 동작은 배포 후 사용자가 확인해야 합니다.

### 참고 사이트

- 세종사이버대학교 dCollection: https://sjcu.dcollection.net
- 세종사이버대학교 자료검색: https://sjcu.dcollection.net/srch/srchSearch
- dCollection 참여기관: https://www.dcollection.net/common/instList.do
- KCI: https://www.kci.go.kr/kciportal/po/search/poArtiSear.kci
- 한국정보보호학회: https://kiisc.or.kr
- 한국중견기업연합회: https://fomek.or.kr
- KISA: https://www.kisa.or.kr
- NIA: https://www.nia.or.kr
- ScienceON: https://scienceon.kisti.re.kr
- 국회입법조사처: https://www.nars.go.kr

## v2.0 자료 종류별 참고문헌 표기 기능

- **학술지 논문:** 저자, 논문 제목, 학술지명, 권·호, 페이지, 발행 연월, DOI
- **석사·박사 학위논문:** 저자, 논문 제목, 학위종류, 학위수여 대학·대학원, 학위수여 연월
- **기관 연구보고서:** 저자 또는 기관명, 보고서 제목, 발행기관, 보고서 번호, 발행 연월, DOI/URL

선택 자료의 실제 자료 종류가 `미분류`이면 임의로 학위논문 등으로 단정하지 않습니다. 누락 필드는 `[항목 미확인]`으로 표시하므로 **원문과 대조하여 수정**해야 합니다. `📄 과제 보고서` 탭에서 각 필드를 편집하고 참고문헌 미리보기를 확인하세요. PDF의 5절에 선택 자료 참고문헌, 별도 부록에 3가지 표기 형식이 포함됩니다. Excel `참고문헌_표기기준` 시트에서도 확인할 수 있습니다.

세부 설명: [`참고문헌_표기기준_v2_0_안내.md`](참고문헌_표기기준_v2_0_안내.md)

## v2.1: AI 요약·참고문헌 화면 간소화 (2026-10-21)

- 오른쪽 `논문 AI 요약` 탭의 버튼이 비활성화된 이유를 버튼 위에 표시합니다. **개인 OpenAI API 키가 없을 때에는 왼쪽 사이드바의 `개인 AI 설정` 위치를 안내**합니다.
- PDF 파일 업로드를 먼저 표시하고 `초록 또는 본문 붙여넣기`는 **접이식 보조 입력**으로 변경했습니다. PDF 텍스트 추출에 성공했다면 추가 입력하지 않아도 됩니다. 스캔 PDF는 여전히 OCR 미지원입니다.
- 이전에 `논문 AI 요약` 탭에 있던 `API 서지정보 임시 참고문헌` 영역은 제거했습니다. 인용문 수정은 `과제 보고서 → 참고문헌 확인·수정 (과제 제출 전)`에서만 진행합니다.
- `자료 종류별 참고문헌 표기 기준`과 `참고문헌 확인·수정`은 기본 접힘 상태입니다. **그 안의 정보는 PDF·Excel 보고서 생성 시 그대로 사용**합니다. 제출 전에는 펼쳐서 출처와 일치하는지 확인하세요.
- AI API 키는 OpenAI API 서비스에서 발급받는 개인 키이며 공공데이터포털 키와 다릅니다. 개인 키의 유효성은 **실제 AI 요청 시에만** 확인할 수 있습니다.
- `ui_helpers.py`를 `app.py`와 같은 폴더에 추가해야 합니다. **교체/추가 파일: `app.py`, `ui_helpers.py`** (기타 파일은 기존 v2.0 유지 가능).
- 단위·회귀 테스트는 `python -m pytest -q`로 실행합니다. `AI요약_사용성_검증.ipynb`에 초보자용 별도 `assert` 셀이 있습니다.

실제 Streamlit UI 브라우저 및 OpenAI 실계정 API 호출은 배포 후 별도 확인해야 합니다.


## v2.2 — 6항목 과제용 / 7문장 논문 읽기용 병행 (2026-10-21)

### 사용자 이용 방법

1. 왼쪽 사이드바에서 본인 OpenAI API 키를 입력합니다(논문 검색은 키 없이 가능).
2. `🤖 논문 AI 요약` 탭에서 **과제 제출용(6항목)** 또는 **논문 읽기용(7문장)**을 선택합니다.
3. 논문 목록에서 제목을 고르거나 직접 논문 제목을 입력하고, 합법적으로 확보한 PDF를 업로드합니다.
4. PDF **전체 페이지**에서 텍스트를 추출하며, 배경·방법·결과·결론 위치를 찾아 **대표 페이지 최대 12페이지**를 AI 근거로 선별합니다. 전 페이지의 내용을 모두 AI가 읽는 것은 아닙니다.
5. 개인 OpenAI API 키, 텍스트 근거, 논문 일치 확인이 준비되면 `AI 요약 생성`을 누릅니다.
6. 7문장 읽기용 결과 아래에서 **나의 생각 / 추가 연구 질문**을 직접 작성할 수 있습니다.
7. `📄 과제 보고서` 탭에서 출력할 요약 모드를 선택하고 PDF/Excel 보고서를 다운로드합니다. 두 모드의 요약은 각각 생성해야 합니다.

### 분석 범위·비용·검증의 한계

- 15MB 이하, **600페이지 이하**의 텍스트 PDF를 지원합니다. 그 이상은 조용히 일부만 처리하는 대신 업로드 제한을 안내합니다.
- 페이지별 글자가 매우 많은 경우 그 페이지의 앞부분·뒷부분 일부만 보존하고 화면에 알립니다.
- 초록·서론, 방법, 결과, 토의·결론 4개 범주의 대표 페이지를 선별합니다. 장 제목을 찾지 못하면 위치 기반 대표 페이지를 사용하며, 섹션 분류가 완벽하지 않을 수 있습니다.
- **짧은 발췌는 OpenAI 1회, 긴 PDF는 구간별 호출 + 통합 최대 5회**입니다. 비용은 사용자 개인 API 키에 부과되며 실행 전 예상 횟수를 표시합니다. 중간 호출 실패 시 재실행하면 추가 비용이 발생할 수 있습니다.
- AI가 반환한 직접 인용문은 PDF 페이지 원문에 실제로 존재하는지 문자·공백 기준으로 검사합니다. 불일치한 인용은 삭제하며, 문구 일치는 **주장 의미의 사실성 검증과 다릅니다.**
- 스캔 PDF OCR, Figure/Table 이미지 자체 해석, 논문 전체 완독, AI 결론의 진위 자동 검증, 검색 및 연구노트 영구 저장은 미지원입니다.
- 개인 OpenAI API 키와 업로드 문서는 글로벌 캐시나 파일/DB에 기록하지 않지만, 활성 Streamlit 사용자 세션 메모리에는 PDF 텍스트·AI 결과·연구노트가 존재합니다.
- 과제용 6항목은 기존 요약·참고문헌·표지 기능을 유지합니다. 읽기용 7문장에는 **사용자가 직접 작성하는 8번째 항목(나의 생각)**을 별도로 제공합니다.

### 신규 파일

`pdf_analysis.py`, `prompt_templates.py`, `research_ai.py` 를 `app.py`와 같은 디렉터리에 추가해야 합니다. `app.py`, `reporting.py`, `requirements.txt`도 함께 최신 버전으로 교체하세요. Python 3.12와 `python -m pip install -r requirements.txt`를 권장합니다.

### 오프라인 검증

```bash
python -m pytest tests -q
```

`v2_2_논문요약_검증.ipynb`에는 초보자용 설명과 **별도의 assert 검증 셀**을 제공합니다. 인터넷 연결이나 API 키 없이 모의 데이터로 실습할 수 있습니다.

**참고 아이디어 출처:** https://github.com/chaek-union/how-to-write-paper (논문 읽기 전 7문장 요약·개인 연구노트 아이디어를 학제 공통형으로 재구성; 원본 코드 복제 아님)
