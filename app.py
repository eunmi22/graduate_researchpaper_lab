"""대학원 AI 논문 연구 도우미 v2.3.5-P0-ID — 6단계 통합 Streamlit 앱.

실행: python -m streamlit run app.py
관리자: DATA_GO_KR_API_KEY / 선택 RISS_API_URL·RISS_API_KEY → .env 또는 Cloud Secrets.
원우: OpenAI 키는 직접 입력하며 서버파일/다운로드/연구 프로젝트에 저장하지 않음.

기능:
01 자료 찾기: v2.2 국회도서관 검색, 연구동향, RISS, dCollection·학회 외부검색.
02 논문 읽기: v2.2 AI 6/7요약, PDF·Excel 보고서, v2.3 부록 7문장 사전개요,
                페이지·그림 확인, 나의 생각, 선행연구 보관함 전달.
03 선행연구 분석: 논문 비교표, 검증 기록, 정식 서지정보 Excel, 세션 백업 JSON.
04 연구 방향: 연구 질문 프롬프트와 AI 주제 후보(검증 전).
05 연구 수행: 실험 메모, 사용자 CSV/XLSX 기초 품질 확인.
06 내 논문 작성: 결과·방법·서론·논의 메모와 Markdown 초안.
"""
from __future__ import annotations

from datetime import date

import streamlit as st
from dotenv import load_dotenv

from legacy_views_v22 import (
    admin_api_key, render_university_theses,
    render_riss_controls, render_external_controls,
    render_ai_summary, render_trends, render_riss, render_sources,
    render_submission,
)
from p0_search_ui import UI_BUILD, render_search_controls, render_search_results
from research_workspace import export_snapshot
from v23_screens import (
    render_reading, render_literature, render_direction,
    render_analysis, render_writing,
)

load_dotenv()
st.set_page_config(
    page_title='대학원 AI 논문 연구 도우미 v2.3.5-P0-ID', page_icon='🎓',
    layout='wide', initial_sidebar_state='expanded',
)
if UI_BUILD != "2.3.5-P0-ID":
    st.error("실행 파일과 검색 화면의 버전이 다릅니다. 새 폴더에 전체 ZIP을 풀고 다시 실행하세요.")
    st.stop()

st.markdown('''
<style>
.block-container{padding-top:1.4rem;max-width:1560px}
h1,h2,h3{color:#17365d}
[data-testid="stMetric"]{background:#f3f7fb;padding:14px;border-radius:12px}
[data-testid="stSidebar"]{background:#f7f9fc}
</style>
''', unsafe_allow_html=True)

MENUS = [
    '01. 자료 찾기',
    '02. 논문 읽기',
    '03. 선행연구 분석',
    '04. 연구 방향·계획',
    '05. 연구 수행·분석',
    '06. 내 논문 작성',
]

with st.sidebar:
    st.title('🎓 논문 연구 도우미')
    st.caption('v2.3.5-P0-ID · 논문 검색부터 나의 학위논문까지')
    selected_menu = st.radio('연구 진행 단계', MENUS, key='v23_main_menu')
    st.divider()
    st.subheader('🤖 개인 AI 설정')
    user_ai_key = st.text_input(
        '본인의 OpenAI API 키', type='password', key='v23_user_api_key',
        help='AI 요청에만 사용합니다. 원문·키를 프로젝트 JSON/Excel이나 로그에 저장하지 않습니다.',
        placeholder='sk-...',
    )
    model = st.selectbox('AI 요약 모델', ['gpt-4.1-mini','gpt-4o-mini'],
                         key='v23_user_model')
    if user_ai_key.strip():
        st.caption('개인 AI 키 입력됨 (실제 유효성은 호출 시 확인)')
    else:
        st.info('API 키가 없어도 검색·논문 원문 읽기·노트 저장은 가능합니다.')
    st.divider()
    with st.expander('📝 과제 보고서 표지', expanded=False):
        school = st.text_input('학교명', key='cover_school')
        department = st.text_input('대학원/전공', key='cover_department')
        course = st.text_input('교과목', key='cover_course')
        student = st.text_input('제출자', key='cover_student')
        professor = st.text_input('담당 교수 (선택)', key='cover_professor')
        submission_date = st.date_input('제출일', value=date.today(), key='cover_date')
    with st.expander('💾 프로젝트 자료 백업', expanded=False):
        st.caption('현재 세션의 선행연구·연구 메모를 내려받습니다. PDF 원문과 API 키는 포함하지 않습니다.')
        try:
            project = export_snapshot(st.session_state.get('research_library', []),
                                      st.session_state.get('workspace_data', {}))
            st.download_button('연구 프로젝트 JSON 백업', project,
                               file_name='대학원_연구프로젝트_백업.json',mime='application/json',
                               key='v23_project_download_sidebar', use_container_width=True)
        except ValueError as exc:
            st.warning(str(exc))
    with st.expander('ℹ️ 이용 안내', expanded=False):
        st.caption('01 검색·원문 확보 → 02 읽기·나의 생각 → 03 논문 비교 → 04 연구 계획 → 05 실제 자료 분석 → 06 원고 작성')
        st.caption('연구 공백·독창성은 AI가 확정할 수 없습니다. 지도교수와 문헌을 직접 확인하세요.')
        st.caption('공개 링크 · 사용자별 로그인/영구 저장 없음. PDF 및 세션은 앱이 재시작되면 사라질 수 있습니다.')
        st.caption('국회도서관과 RISS 서비스는 관리자가 API 인증·엔드포인트를 설정한 경우에만 이용할 수 있습니다.')

st.title('🎓 대학원 AI 논문 연구 도우미')
st.caption('자료 찾기 → 논문 읽기 → 선행연구 분석 → 연구 방향·계획 → 연구 수행·분석 → 내 논문 작성')
st.caption('v2.3.5-P0-ID · 모든 참고문헌은 자료유형별 정식 표기 · AI 분석과 사용자의 생각·검증 결과를 구분')

if selected_menu == MENUS[0]:
    st.header('01. 자료 찾기')
    # 국회도서관/대학별 검색은 서로 다른 탭으로 표시합니다. 기존 RISS·동향 등은 보조 탭에 보존.
    tabs = st.tabs(['국회도서관 논문 검색', '대학 학위논문 검색', '기타 자료·통계'])
    with tabs[0]:
        render_search_controls(admin_api_key())
        render_search_results(admin_api_key())
    with tabs[1]:
        render_university_theses()
    with tabs[2]:
        st.caption('기존 연구 동향·RISS 통계·학회 자료 기능은 유지하되, 논문 검색과 분리했습니다.')
        misc = st.tabs(['연구 동향', 'RISS 서지통계', '학회·연구보고서'])
        with misc[0]:
            render_trends()
        with misc[1]:
            render_riss_controls()
            render_riss()
        with misc[2]:
            render_external_controls()
            render_sources()
    st.caption('국회도서관 자료검색은 서지정보 중심이며 원문 PDF 자동 확보를 보장하지 않습니다. PDF 분석은 02에서 진행하세요.')

elif selected_menu == MENUS[1]:
    st.header('02. 논문 읽기')
    st.caption('부록 1·2의 「요약하고 읽기」와 기존 v2.2 요약·보고서를 함께 제공합니다.')
    tabs = st.tabs(['AI 요약·논문/PDF 준비', '논문 읽기·나의 생각', '과제 보고서·정식 참고문헌'])
    with tabs[0]:
        render_ai_summary(user_ai_key, model)
    with tabs[1]:
        render_reading(user_ai_key, model)
    with tabs[2]:
        render_submission(school,department,course,student,professor,submission_date)

elif selected_menu == MENUS[2]:
    render_literature()

elif selected_menu == MENUS[3]:
    render_direction(user_ai_key, model)

elif selected_menu == MENUS[4]:
    render_analysis()

elif selected_menu == MENUS[5]:
    render_writing()

st.divider()
st.caption('개인정보·PDF 저작권·연구윤리 및 대학원의 AI 사용 기준을 확인하세요. AI의 서술은 원문·실제 데이터로 재검증해야 합니다.')
