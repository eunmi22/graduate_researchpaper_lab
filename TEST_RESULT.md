# v2.3.6-P0-UI 검증 결과

## 실행한 검사
| 항목 | 결과 |
|---|---|
| pytest 단위·회귀 테스트 | 245개 통과 |
| Streamlit AppTest 모듈 | 1개 건너뜀(런타임 설치 불가) |
| 신규 선택 상태·화면 컨트롤러 테스트 | 기존 203개에 42개 추가, 모두 통과 |
| Jupyter verify_ui.ipynb | 코드 셀 10개 실행, 별도 assert 셀 5개 통과 |
| Python 구문 검사 | 통과 |
| ZIP CRC·경로 검사 | 통과, app.py가 최상위에 위치 |
| 압축 해제본 check_install.py | 배포 소스 일치 검사 통과 |

## 이번 변경의 실제 검증 범위
합성 서지정보를 사용하여 다음을 검사했습니다.
- 대분류별 건수 합계가 수집 자료 수와 일치함.
- 학위논문·학술기사·도서자료·미확인 자료만 각각 선택창에 표시함.
- 세부자료를 고르기 전에는 논문 읽기 버튼을 활성화하지 않음.
- 대분류 변경 시 다른 유형의 이전 선택이 남지 않음.
- 같은 유형으로 돌아올 때 해당 유형의 선택을 복원함.
- 제목 보완·순서 변경·추가 페이지에도 동일 관리번호 선택을 유지함.
- 제목이 같은 다른 자료를 식별자로 구분함.
- 책·미확인 자료는 공식 상세정보를 열 수 있으나 논문으로 자동 전달하지 않음.
- 선택 및 대분류 변경 자체에서는 API를 재호출하지 않음.
- 긴 제목은 전체 카드에 보존하며 동적 HTML 문자를 이스케이프함.
- 02 화면으로 이동할 때 정확한 관리번호를 전달함.
- 새 검색의 선택값 초기화 시 사용자 연구노트를 건드리지 않음.

## 보존 검사
직전 id_release/paper.zip(v2.3.5-P0-ID)과 비교하여 기존 Python 모듈 20개가 바이트 단위로 동일합니다.
특히 paperlab.py, nanet_metadata.py, nanet_search_flow.py, nanet_enrich.py, nanet_detail.py와 AI·PDF·보고서 모듈, requirements.txt는 바꾸지 않았습니다.
세부 목록은 preservation_audit.json에 있습니다.

## 실행하지 못한 검사
- 실제 국회도서관 API 인증 검색과 실데이터 263건 대조.
- 실제 OpenAI API 호출.
- 실제 Streamlit 브라우저 렌더링·모바일 화면 확인.
- 사용자 GitHub/Streamlit Cloud 운영 배포.

Streamlit 설치를 시도했으나 실행 환경의 DNS/네트워크 제약으로 패키지를 받을 수 없었습니다. 따라서 UI 컨트롤러 모의 테스트는 통과했지만 실제 Streamlit AppTest 및 브라우저 테스트는 완료했다고 주장하지 않습니다.
실행 환경에서는 `python -m pip install -r requirements-dev.txt` 후 `python -m pytest -q`로 AppTest도 실행할 수 있습니다.