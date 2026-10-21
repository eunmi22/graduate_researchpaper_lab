# 대학원 AI 논문 연구 도우미

> 국회도서관 자료검색 API + Streamlit + pandas + 개인 OpenAI API 키 기반 연구/과제 도우미

## 먼저 알아두기

- **공개 링크**로 대학원 원우들이 함께 이용할 수 있는 Streamlit 웹서비스입니다. 별도의 회원가입·로그인은 구현하지 않았습니다.
- 국회도서관 공공데이터 API 키(`DATA_GO_KR_API_KEY`)는 **운영자가 한 번만 설정**합니다.
- 각 원우는 자신의 **OpenAI API 키를 화면의 암호형 입력창**에 입력합니다. 검색·통계는 개인 OpenAI 키가 없어도 가능합니다.
- 업로드 PDF/초록은 메모리에서 처리되며 별도 DB나 서버 파일에 저장하지 않습니다. 다만 브라우저/Streamlit 서버 세션 내에는 일시적으로 존재하고, AI 요약 시 해당 텍스트는 OpenAI API로 전송됩니다. **저작권·개인정보·소속 대학원의 연구윤리 기준을 확인**해야 합니다.
- 별도의 결제 설정이 필요할 수 있으며, **OpenAI API는 ChatGPT 구독과 별도로 과금**될 수 있습니다.

## 기능

| 기능 | 제공 내용 |
|---|---|
| 1. 논문 검색 | 국회도서관 `/searchservice/basic` 통합검색, 최대 5페이지, 자료유형별 필터 |
| 2. AI 요약 | 초록/PDF 발췌 근거, 주제·목적·다룬기술·활용분야·주요한계·발전방향 총 6줄 |
| 3. 연구 동향 | 검색해 **수집한** 자료의 발행연도별, 자료유형별 빈도 그래프 |
| 4. 보고서 | 표지 포함 PDF + 6개 시트 Excel + 텍스트 요약 |
| 5. 참고문헌 | 검색 결과의 서지정보를 이용한 **임시** 참고문헌 목록 |
| 6. 표지 | 학교, 대학원/전공, 교과목, 교수, 성명, 제출일 |
| 7. 파일 업로드 | 텍스트 기반 PDF(15MB 이하, 최대 30페이지) 및 초록 붙여넣기, 직접 업로드 분석 |

> API 문서가 보장하는 것은 도서·학위논문·국내외 기사 **목록 서지정보**입니다. 초록·본문을 자동으로 반환하는 API가 아닙니다. 제목만 입력하면 AI가 요약을 만들지 않도록 막았습니다. 스캔 PDF의 OCR은 지원하지 않습니다.

## 폴더 구성

```text
graduate_paper_lab/
├─ app.py                         # Streamlit 메인 화면
├─ paperlab.py                    # 국회도서관 XML·데이터 분석·OpenAI 처리
├─ reporting.py                   # PDF·Excel 보고서
├─ requirements.txt               # pip 설치 대상
├─ packages.txt                   # Cloud에서 PDF 한글 글꼴 설치
├─ .streamlit/
│  ├─ config.toml                 # 테마·업로드 최대 15MB
│  └─ secrets.example.toml        # 배포용 비밀 값 형식(실제 키 없음)
├─ .env.example                   # 로컬 환경변수 예시(실제 키 없음)
├─ .gitignore                     # 실제 비밀 키 추적 금지
├─ API_실습_검증.ipynb             # 수업 제출용 Jupyter 실습 노트북
└─ tests/test_paperlab.py         # API 없이 검사 가능한 단위 테스트
```

## 화면 구성 (좌측 입력 / 우측 결과) - 개편판

| 왼쪽 사이드바: 입력/설정 | 오른쪽 메인화면: 검색 결과/다운로드 |
|---|---|
| 논문 주제 검색어, 검색 대상, 자동 재검색, 검색 페이지 수/건수, 검색 실행 버튼 | **검색 결과** 탭: 논문 목록, 원 검색어·재검색어, API 건수, 오류 진단 |
| 검색된 자료 유형 필터 | **논문 AI 요약** 탭: 논문 선택, 초록/PDF 첨부, 6개 항목 요약 |
| 원우 개인 OpenAI API 키, AI 모델 | **연구 동향** 탭: 발행연도/자료유형 차트와 결측·중복 |
| 접이식 **과제 표지 정보**: 학교, 전공, 과목, 제출자, 교수, 날짜 | **과제 보고서** 탭: 표지 미리보기, PDF/Excel 다운로드 |
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
