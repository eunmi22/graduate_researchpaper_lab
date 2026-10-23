# P0 근거와 미검증 범위

## 적용한 자료

1. 사용자 제공 「대학원 AI 논문 연구 도우미 — 통합 개발 요구사항 및 국회도서관 검색 기능 고도화」. 특히 검색/분류/보안/테스트, P0~P2 단계 구분.
2. 사용자 대화에 제공된 국회도서관 자료검색 활용가이드 2023-05-02. `basic` 필수 변수는 serviceKey, pageno, displaylines, search. 검색어는 검색항목,키워드 형식. 이 문서에서 basic 정렬 파라미터는 확인되지 않아 새로 만들지 않음. 기존 패키지의 `_nanet_api_spec.txt` 참고.
3. 공공데이터포털 「국회 국회도서관_자료검색 서비스」 공식 페이지: https://www.data.go.kr/data/15098174/openapi.do
4. 사용자 제공 공식 상세화면의 국내기사/학위논문/도서 서지 예시 및 기존 테스트. 접두어 분류는 확인 사례 기반이며 공식 전체 코드표라고 주장하지 않음.
5. Streamlit AppTest 공식 문서: https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest

## 소스 검토로 확인한 결함

기존 유형 분류는 DB 값이 없으면 미분류로 남겼으며, 제목 별칭이 제한적이었습니다. 학술자료가 수집되지 않았다는 조건으로 검색어를 넓혀 다른 검색어의 결과가 섞일 가능성이 있었습니다. 이 부분은 코드와 모의응답으로 확인하여 수정했습니다.

## 아직 증명하지 않은 사항

사용자의 실제 API 원응답과 승인 키가 없으므로 실제 제목 누락이 어느 XML 변형에서 발생했는지, 공식 웹과 결과 목록이 얼마나 일치하는지 확정하지 않았습니다. 자동 보완은 공개 상세정보 접근과 HTML 구조에 영향을 받습니다. 실제 사이트에서 검색·보완이 반드시 성공한다고 보장하지 않습니다.

본 패키지는 웹사이트와 API가 동일한 관련도 정렬을 제공한다고 가정하지 않습니다. API 순번과 앱 유형 우선 순번을 분리해서 보여줍니다. 261건은 이전 사용자 화면의 관측값이며 현재 API 건수로 고정하지 않습니다.


## Identification update

User screenshot: identifier-only selector and unreadable unknown catalogue.
Streamlit selectbox display labels can differ from returned option values: https://docs.streamlit.io/develop/api-reference/widgets/st.selectbox
The UI displays metadata but selects by a stable internal identifier. This update does not add new library identifier-prefix rules.
