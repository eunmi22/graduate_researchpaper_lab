"""대학원 AI 논문 연구 도우미 v2.3 신규 화면 (02~06).

과거 버전의 공공데이터 검색/AI 요약/보고서는 legacy_views_v22.py에서 유지.
사용자별 작업공간은 st.session_state에만 존재; JSON 내보내기로 백업.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date

import fitz
import pandas as pd
import streamlit as st

from citation_styles import (
    JOURNAL, THESIS, REPORT, UNKNOWN, REFERENCE_TYPES,
    complete_citation, format_reference, missing_citation_fields, suggested_citation,
)
from legacy_views_v22 import current_paper, edit_citation
from prompt_templates import ASSIGNMENT, READING, DISPLAY_NAMES
from research_ai import analysis_summary
from reading_premap import generate_premap, PREMAP_FIELDS
from research_workspace import (
    DIMENSIONS, INCOMPLETE, build_entry, literature_rows, literature_excel,
    direction_prompt, export_snapshot, import_snapshot, paper_uid,
)


def _library() -> list[dict]:
    return st.session_state.setdefault('research_library', [])


def _workspace() -> dict:
    return st.session_state.setdefault('workspace_data', {})


def _paper_context() -> tuple[dict | None, str, str, str]:
    paper, origin = current_paper()
    if paper is None:
        paper = st.session_state.get('active_current_paper')
        origin = st.session_state.get('active_origin', '')
    paper_id = str(paper.get('controlno') or paper.get('자료명/저자사항')) if paper else ''
    evidence_id = st.session_state.get('active_evidence_id', '')
    return paper, origin, paper_id, evidence_id


def _paper_note(paper_id: str, evidence_id: str) -> tuple[str, str]:
    note_id = hashlib.sha256((paper_id + '|' + evidence_id).encode('utf-8')).hexdigest()[:16]
    note_key = f'v23_note_input_{note_id}'
    if note_key not in st.session_state:
        st.session_state[note_key] = st.session_state.get('research_notes', {}).get(note_id, '')
    note = st.text_area(
        '8. 나의 생각 / 의문 (본인이 직접 작성)', key=note_key, height=145,
        placeholder='예: 감사 로그가 비활성화되었을 때 대체 증거원을 이용할 수 있을까?',
    )
    st.session_state.setdefault('research_notes', {})[note_id] = note
    return note, note_id


def render_reading(user_ai_key: str, model: str) -> None:
    st.subheader('📖 논문 읽기 · 사전 개요 → 원문 확인 → 나의 질문')
    st.caption('부록 1·2를 참고한 학습 메뉴입니다. 논문 PDF의 Figure 이미지를 자동 AI 판독하지 않습니다.')
    paper, origin, paper_id, evidence_id = _paper_context()
    if paper is None:
        st.info('먼저 이 메뉴의 「AI 요약·자료 업로드」에서 논문을 선택하거나 직접 입력해 주세요.')
        return
    pdf_doc = st.session_state.get('pdf_doc')
    pdf_bytes = st.session_state.get('pdf_bytes')
    abstract = st.session_state.get('saved_abstract', '')
    st.markdown(f"**대상 논문:** {paper.get('자료명/저자사항', '')}")
    with st.expander('📚 정식 참고문헌 확인·수정', expanded=False):
        citation = edit_citation(paper)
    if not st.session_state.get('active_citation_record'):
        citation = complete_citation(paper)
    else:
        citation = st.session_state['active_citation_record']
    st.caption('정식 참고문헌')
    st.code(format_reference(citation), language=None)

    steps = st.tabs(['① 사전 개요', '② 본문 읽기', '③ 그림·표 보기', '④ 나의 생각·저장'])
    with steps[0]:
        st.markdown('#### 7문장 사전 개요 (Pre-map)')
        st.caption('부록 1 방식: 배경 1 · 질문 1 · 자료 1 · 결과·의의 4. 기존 v2.2의 일반 7문장 요약과 구분됩니다.')
        ctx = f'{paper_id}|{evidence_id}'
        premap = st.session_state.get('premap_results', {}).get(ctx)
        ready = (pdf_doc is not None and pdf_doc.char_count >= 80) or len(abstract.strip()) >= 40
        if not user_ai_key.strip():
            st.warning('🔑 새로운 AI 사전 개요를 생성하려면 사이드바에서 개인 OpenAI API 키를 입력하세요.')
        if not ready:
            st.info('먼저 「AI 요약·자료 업로드」에서 PDF 또는 초록을 준비하세요.')
        if st.button('✨ 부록 1 방식 7문장 사전 개요 생성 (API 1회)',
                     type='primary', disabled=not (bool(user_ai_key.strip()) and ready),
                     key='v23_generate_premap'):
            try:
                with st.spinner('논문의 대표 구간을 근거로 사전 개요를 만드는 중...'):
                    premap = generate_premap(
                        user_ai_key, str(paper.get('자료명/저자사항', '')),
                        pdf_doc=pdf_doc if ready else None,
                        abstract=abstract, model=model,
                    )
                st.session_state.setdefault('premap_results', {})[ctx] = premap
                st.success('사전 개요 7항목 생성 완료 (별도 OpenAI API 1회 사용).')
            except Exception as exc:
                st.error(f'AI 사전 개요 생성 실패 ({type(exc).__name__}). 키와 모델 및 결제 상태를 확인하세요.')
        if premap:
            for i, item in enumerate(premap['items'], 1):
                st.markdown(f"**{i}. {item['key']}:** {item['text']}")
                for record in item.get('evidence', []):
                    with st.expander(f"{i}번 항목 PDF 근거 · {record['page']}쪽"):
                        st.write(record['quote'])
                        st.caption('직접 인용 문구 일치만 검증했습니다. 해석은 원문과 대조하세요.')
            st.caption('AI 제공 구간: ' + premap.get('source_scope', ''))
        else:
            st.caption('AI 사전 개요를 만들지 않은 경우에도 다음 탭에서 원문을 직접 읽을 수 있습니다.')
        v22_reading = st.session_state.get('analysis_results', {}).get((paper_id, evidence_id, READING))
        if v22_reading:
            with st.expander('v2.2 방식 7문장 요약도 함께 보기'):
                for i, item in enumerate(v22_reading['items'], 1):
                    st.markdown(f"**{i}. {DISPLAY_NAMES.get(item['key'],item['key'])}:** {item['text']}")
    with steps[1]:
        st.markdown('#### 원문을 직접 확인하는 읽기 경로')
        st.info('제목·초록 → 연구 문제·방법 → 중요한 결과/절차 → 결론·한계 순서로 읽어보세요.')
        if pdf_doc is not None:
            st.caption(f"PDF {pdf_doc.total_pages}페이지 중 텍스트 {pdf_doc.text_pages}페이지 추출 완료 (글자만 추출한 자료입니다).")
            page_choices = [i for i, page in enumerate(pdf_doc.pages, 1) if page.text.strip()]
            if page_choices:
                selected_page = st.selectbox('직접 읽을 PDF 페이지', page_choices, key='v23_text_page')
                shown = pdf_doc.pages[selected_page - 1].text
                st.text_area(f'PDF {selected_page}쪽 원문 텍스트', shown[:10000], height=320, disabled=True)
                st.caption('PDF의 표시 페이지와 본문에 인쇄된 쪽수는 다를 수 있습니다. 긴 페이지는 텍스트 일부만 보여줍니다.')
        elif abstract.strip():
            st.text_area('제공한 초록', abstract[:10000], height=200, disabled=True)
        else:
            st.info('본문을 직접 읽으려면 PDF를 업로드하거나 초록을 입력해 주세요.')
        st.markdown('**읽으며 확인할 내용**')
        for question in ('저자가 해결하고자 하는 문제는 무엇인가?', '어떤 기술·자료·방법을 실제 사용했는가?',
                         '새롭게 기여한 부분과 실제 검증 결과는 무엇인가?', '논문에 명시된 한계는 무엇인가?'):
            st.caption('• ' + question)
    with steps[2]:
        st.markdown('#### Figure·Table 확인')
        st.caption('PDF의 해당 페이지 이미지를 직접 열어 확인합니다. 그림의 숫자·축은 AI가 판독했다고 주장하지 않습니다.')
        if pdf_bytes:
            page = st.number_input('그림·표가 있는 PDF 페이지 선택', min_value=1,
                                   max_value=max(1, pdf_doc.total_pages if pdf_doc else 1),
                                   value=1, step=1, key='v23_figure_page')
            if st.button('🖼 원문 페이지 이미지 보기', key='v23_show_figure'):
                try:
                    with fitz.open(stream=pdf_bytes, filetype='pdf') as pdf:
                        rendered = pdf[page - 1].get_pixmap(matrix=fitz.Matrix(1.15, 1.15))
                        st.image(rendered.tobytes('png'), caption=f'PDF {page}쪽 실제 페이지 이미지', use_container_width=True)
                except Exception as exc:
                    st.error(f'페이지 렌더링 오류 ({type(exc).__name__})')
            st.text_area('이 그림·표를 내 말로 설명하기 (학습용)',
                         key='v23_figure_notes', height=100,
                         placeholder='무엇을 보여 주는지, 어떤 비교인지, 해석과 의문을 적어 보세요.')
        else:
            st.info('Figure·Table을 보려면 원본 PDF를 먼저 업로드하세요.')
    with steps[3]:
        st.markdown('#### 나의 생각과 연구 질문')
        note, note_id = _paper_note(paper_id, evidence_id)
        st.caption('AI가 사용자를 대신해 개인적 생각을 작성하지 않습니다. 입력한 질문이 03·04 메뉴로 전달됩니다.')
        st.info('생각의 출발점 예시: 이 접근의 한계는 무엇이고, 다른 자료로 어떻게 검증할 수 있을까요?')
        result = st.session_state.get('analysis_results', {}).get((paper_id, evidence_id, READING))
        if result is None:
            result = st.session_state.get('analysis_results', {}).get((paper_id, evidence_id, ASSIGNMENT))
        uid = paper_uid(paper, evidence_id)
        existing = any(item.get('id') == uid for item in _library())
        if st.button('📚 이 논문을 03. 선행연구 분석에 저장' + (' (기존 기록 갱신)' if existing else ''),
                     type='primary', key='v23_add_literature'):
            entry = build_entry(paper, citation, result, note, evidence_id, origin)
            library = _library()
            for i, item in enumerate(library):
                if item['id'] == uid:
                    library[i] = entry
                    break
            else:
                library.append(entry)
            st.success('선행연구 자료함에 기록했습니다. 왼쪽에서 03. 선행연구 분석으로 이동할 수 있습니다.')
        st.caption('주의: 세션에만 저장된 내용은 종료 후 사라질 수 있으므로 03 메뉴에서 프로젝트 JSON을 다운로드하세요.')
        if result:
            lines = [format_reference(citation), '', '논문 읽기용 AI 요약']
            lines += [f"{i}. {DISPLAY_NAMES.get(item['key'], item['key'])}: {item['text']}" for i,item in enumerate(result['items'],1)]
            lines += ['', '8. 나의 생각 / 의문', note]
            st.download_button('📥 나의 논문 읽기노트 (.txt)', '\n'.join(lines).encode('utf-8-sig'),
                               file_name='논문읽기_연구노트.txt', mime='text/plain', key='v23_note_download')


def render_literature() -> None:
    st.subheader('03. 선행연구 분석')
    st.caption('여러 논문의 주요 내용·활용 기술·방법·결과·기여도·한계를 비교하고 새로운 쟁점을 검증합니다.')
    library = _library()
    if not library:
        st.info('02. 논문 읽기에서 「이 논문을 03에 저장」을 눌러야 비교할 자료가 생깁니다.')
    else:
        c1, c2 = st.columns(2)
        c1.metric('저장된 논문', f'{len(library)}편')
        c2.metric('미검증 질문', f"{sum('미검증' in item.get('dimensions',{}).get('새로운 쟁점','') for item in library)}개")
        rows = literature_rows(library)
        st.markdown('#### 선행연구 종합 비교표')
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=350)
        st.caption('AI 요약을 직접 검증한 사실과 사용자 의문을 구분하세요. 정식 참고문헌만 표시합니다.')
        st.download_button('📊 선행연구 비교표 Excel 다운로드', literature_excel(library),
                           file_name='선행연구_정식참고문헌_비교표.xlsx',
                           mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        labels = [f"{i+1}. {item.get('title','')}" for i,item in enumerate(library)]
        index = st.selectbox('상세 비교·수정할 논문', list(range(len(library))),
                             format_func=lambda i:labels[i], key='v23_literature_idx')
        item = library[index]
        st.markdown('**정식 참고문헌**')
        st.code(item['reference'], language=None)
        with st.expander('분석 항목 수정 및 검증 상태', expanded=False):
            for field in DIMENSIONS:
                wid = f'v23_dim_{item["id"]}_{field}'
                if wid not in st.session_state:
                    st.session_state[wid] = item.get('dimensions',{}).get(field, INCOMPLETE)
                item['dimensions'][field] = st.text_area(field, key=wid, height=90)
            statuses=['개별 논문 요약 / 추가 선행연구 검증 필요', '여러 원문 교차 검토 진행 중',
                      '선행연구 원문 비교 완료 (사용자 검토)', '지도교수 검토 완료 (사용자 기록)']
            s_key = f'v23_lit_status_{item["id"]}'
            if s_key not in st.session_state:
                st.session_state[s_key] = item.get('review_status') if item.get('review_status') in statuses else statuses[0]
            item['review_status'] = st.selectbox('검토 상태', statuses, key=s_key)
            st.caption('상태는 사용자가 기록한 단계이며 실제 독창성·증거 타당성의 자동 인증이 아닙니다.')
        if st.button('🗑 선택한 기록 제거', key='v23_delete_lit'):
            library.pop(index)
            st.rerun()
    st.divider()
    st.markdown('#### 선행연구 기록 저장·복원')
    snapshot = export_snapshot(library, _workspace())
    st.download_button('📥 내 연구 프로젝트 JSON 백업', snapshot,
                       file_name=f'대학원_연구프로젝트_{date.today().isoformat()}.json',
                       mime='application/json')
    uploaded = st.file_uploader('기존 연구 프로젝트 JSON 불러오기 (최대 2MB)', type=['json'], key='v23_json_import')
    if uploaded is not None and st.button('프로젝트 복원', key='v23_import_btn'):
        try:
            records, params = import_snapshot(uploaded.getvalue())
            st.session_state.research_library = records
            st.session_state.workspace_data = params
            st.session_state.research_candidates = params.get('research_candidates', [])
            # 기존 작업공간 입력 위젯 값이 복원 자료를 덮지 않도록 UI 키를 초기화.
            for key in list(st.session_state.keys()):
                if key.startswith(('v23_workspace_ui_', 'v23_dim_', 'v23_lit_status_')):
                    st.session_state.pop(key, None)
            st.success(f'선행연구 {len(records)}편과 연구 메모를 복원했습니다. PDF·API 키는 포함되지 않습니다.')
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def _workspace_text(name: str, label: str, height: int = 90, placeholder: str = '') -> str:
    doc = _workspace()
    wid = f'v23_workspace_ui_{name}'
    if wid not in st.session_state:
        st.session_state[wid] = str(doc.get(name, ''))
    value = st.text_area(label, key=wid, height=height, placeholder=placeholder)
    doc[name] = value
    return value


def render_direction(user_ai_key: str, model: str) -> None:
    st.subheader('04. 연구 방향·계획')
    st.caption('02에서 작성한 나의 의문 + 03의 선행연구 비교를 바탕으로 연구과제 후보를 설계합니다.')
    interest = _workspace_text('research_interest','연구 관심 분야',90,'예: 클라우드 DB의 로그 부재 상황에서 행위 추적 가능성')
    purpose = _workspace_text('purpose','학위·연구 목표',68,'예: 석사학위논문')
    available = _workspace_text('available_data','확보 가능한 데이터·도구·실험 환경',90,'예: 교육용 AWS 계정, 생성한 테스트 로그, Python')
    timeframe = _workspace_text('timeframe','연구 가능한 기간',68,'예: 6개월')
    prompt = direction_prompt(_library(), interest, purpose or '석사학위논문', available, timeframe)
    st.markdown('#### 선행연구 기반 AI 프롬프트')
    with st.expander('AI로 보낼 검토 프롬프트 확인', expanded=True):
        st.code(prompt, language=None)
    st.download_button('📄 연구과제 검토 프롬프트 다운로드', prompt.encode('utf-8-sig'),
                       file_name='연구과제_방향_분석프롬프트.txt', mime='text/plain')
    if not _library():
        st.warning('현재 선행연구 비교표가 없습니다. 생성 결과는 근거 검증 없는 연구 아이디어에 불과합니다.')
    if not user_ai_key.strip():
        st.warning('🔑 AI 주제 후보 생성을 사용하려면 개인 OpenAI API 키를 입력하세요. 프롬프트 다운로드는 키 없이 가능합니다.')
    if st.button('✨ 연구주제 후보 3개 AI 검토 (API 1회)', type='primary',
                 disabled=not bool(user_ai_key.strip()), key='v23_research_ai'):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=user_ai_key.strip(), timeout=75.0, max_retries=1)
            with st.spinner('선행연구 근거를 바탕으로 연구 아이디어를 검토하는 중...'):
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {'role':'system','content':(
                            '당신은 대학원 연구 설계 조언자입니다. 문헌을 실제 검색한 것처럼 말하지 마세요. '
                            '기존 논문에서 확인한 한계와 사용자의 아이디어를 구분하고 실험하지 않은 결과를 만들지 마세요. '
                            'JSON 객체 {"candidates":[{"title":...,"rq":...,"data":...,"method":...,"evaluation":...,"expected_contribution":...,"risks":...,"evidence_to_check":...}]} 형태로 최대 3개 후보를 쓰세요. '
                            '연구 공백은 모두 검증 전 후보로 명시하세요. 이미 알 수 없는 서지정보를 생성하지 마세요.'
                        )},
                        {'role':'user','content':prompt[:26000]},
                    ],
                    response_format={'type':'json_object'},
                    temperature=0, max_tokens=2200,
                )
            obj = json.loads(response.choices[0].message.content or '{}')
            candidates = obj.get('candidates', [])
            if not isinstance(candidates, list):
                raise ValueError('주제 후보 형식이 올바르지 않습니다.')
            st.session_state.research_candidates = [
                {k: str(c.get(k,''))[:1800] for k in (
                    'title','rq','data','method','evaluation','expected_contribution','risks','evidence_to_check')}
                for c in candidates[:3] if isinstance(c,dict)
            ]
            _workspace()['research_candidates'] = st.session_state.research_candidates
            st.success('연구 질문 후보가 생성되었습니다. 기존 연구에 없는 새 주제라는 의미는 아닙니다.')
        except Exception as exc:
            st.error(f'AI 연구 방향 분석 실패 ({type(exc).__name__}). API 키·요청 형식 등을 확인하세요.')
    candidates = st.session_state.get('research_candidates', []) or _workspace().get('research_candidates', [])
    if candidates:
        st.markdown('#### 연구주제 후보 (모두 검증 전)')
        for i,item in enumerate(candidates,1):
            with st.expander(f"후보 {i}. {item.get('title', '[제목 미정]')}", expanded=i==1):
                for col,title in [('rq','연구 질문'),('data','필요 자료'),('method','연구 방법'),
                                  ('evaluation','평가 지표'),('expected_contribution','예상 기여도'),
                                  ('risks','위험·제약'),('evidence_to_check','검증할 문헌')]:
                    st.markdown(f"**{title}:** {item.get(col) or '[확인 필요]'}")
        data = json.dumps({'candidates':candidates},ensure_ascii=False,indent=2).encode('utf-8')
        st.download_button('📥 연구주제 후보 JSON 다운로드', data, file_name='연구주제_후보_검증전.json',mime='application/json')
    st.divider()
    st.markdown('#### 연구계획서 작업 메모')
    _workspace_text('research_plan','연구 목적·RQ·데이터 확보 계획·평가 지표·지도교수 피드백',200)
    st.caption('확정 연구계획서는 선행연구 조사·자료 접근·비용 및 지도교수 검토 이후 작성해야 합니다.')


def render_analysis() -> None:
    st.subheader('05. 연구 수행·분석')
    st.caption('실제 연구 자료에 대한 분석과 실험 기록. 결과가 없을 때 임의 통계·실험값을 생성하지 않습니다.')
    _workspace_text('methods_note','실험 환경·자료 출처·도구 버전·재현 절차 메모',145)
    _workspace_text('results_note','실제로 확인한 결과 또는 다음 실험 계획',145)
    st.markdown('#### 데이터 파일로 기본 품질 검증')
    file = st.file_uploader('CSV 또는 XLSX 업로드 (최대 10MB, 실제 연구데이터만)',
                            type=['csv','xlsx'], key='v23_dataset_file')
    if file is None:
        st.info('CSV·Excel 자료를 올리면 결측·중복·기본 통계를 확인할 수 있습니다. 이 기능은 실험 결과의 학술적 타당성 검증이 아닙니다.')
        return
    if len(file.getvalue()) > 10*1024*1024:
        st.error('10MB 이하의 파일을 올려 주세요.')
        return
    try:
        if file.name.lower().endswith('.xlsx'):
            data = pd.read_excel(io.BytesIO(file.getvalue()), engine='openpyxl')
        else:
            try:
                data = pd.read_csv(io.BytesIO(file.getvalue()), encoding='utf-8-sig')
            except UnicodeDecodeError:
                data = pd.read_csv(io.BytesIO(file.getvalue()), encoding='cp949')
        data = data.head(20000).copy()
        st.caption('첫 20,000행까지만 화면·통계에 사용합니다. 파일 전체를 분석한 것으로 보지 마세요.')
        st.dataframe(data.head(100), use_container_width=True)
        a,b,c=st.columns(3)
        a.metric('분석 행',f'{len(data):,}')
        b.metric('결측 셀',f'{int(data.isna().sum().sum()):,}')
        c.metric('중복 행',f'{int(data.duplicated().sum()):,}')
        st.dataframe(data.isna().sum().rename('결측 건수').reset_index(names='열 이름'),
                     hide_index=True, use_container_width=True)
        numeric = data.select_dtypes(include='number')
        if not numeric.empty:
            st.markdown('**수치 데이터 기초 통계**')
            st.dataframe(numeric.describe().T, use_container_width=True)
            col = st.selectbox('차트로 볼 수치 열', list(numeric.columns), key='v23_chart_field')
            st.line_chart(numeric[col].head(200))
        st.success('이 분석은 로컬 pandas 처리이며 외부 AI API로 업로드하지 않습니다.')
    except Exception as exc:
        st.error(f'자료를 읽을 수 없습니다 ({type(exc).__name__}). CSV/XLSX 형식과 파일 크기를 확인해 주세요.')


def render_writing() -> None:
    st.subheader('06. 내 논문 작성')
    st.caption('연구 스토리라인·장별 실제 메모를 작성하고, 확인되지 않은 결과는 빈칸으로 남깁니다.')
    st.info('논문 작성 순서와 제출 형식은 대학원/지도교수 지침이 우선합니다. 연구 실적이 없으면 Results를 생성하지 않습니다.')
    p1,p2,p3 = st.tabs(['목차·연구 스토리', '장별 실제 작성 메모', '원고 초안·참고문헌'])
    with p1:
        st.markdown('#### 권장 5장 학위논문 목차')
        st.markdown('''1. **서론** — 연구 배경 → 문제 정의 → 연구 목적·질문(RQ)
2. **이론적 배경·선행연구** — 검증된 문헌과 한계
3. **연구 방법** — 데이터·도구·실험·검증·재현성
4. **연구 결과 및 분석** — 실제 데이터, Table/Figure 및 평가
5. **논의 및 결론** — RQ에 대한 답, 기여도, 한계, 후속연구''')
        st.caption('이는 일반적인 구성 예시이며 모든 대학원 학위논문의 필수 순서는 아닙니다.')
        _workspace_text('research_interest','내 연구의 주제·제목',70)
        _workspace_text('research_plan','확정한 연구 질문과 스토리라인',150)
    with p2:
        _workspace_text('methods_note','3장 Methods — 실제 연구자료·방법·실험 설정',160)
        _workspace_text('results_note','4장 Results — 실제로 얻은 결과와 표·그림',160)
        _workspace_text('introduction','1장 Introduction — 연구 배경·연구 공백·목적',140)
        _workspace_text('discussion','5장 Discussion — 실제 결과의 해석·비교·한계',140)
    with p3:
        data = _workspace()
        reference_list = [item['reference'] for item in _library() if item.get('reference')]
        doc = [
            '# 내 학위논문 초안 (사용자 연구 메모)',
            '',
            '## 임시 제목', str(data.get('research_interest') or '[논문 제목 입력 필요]'),
            '',
            '## 연구 질문과 스토리라인', str(data.get('research_plan') or '[연구 질문 입력 필요]'),
            '',
            '## 1장. 서론', str(data.get('introduction') or '[서론 실제 자료 입력 필요]'),
            '',
            '## 2장. 이론적 배경·선행연구', '[검증된 선행연구 비교를 바탕으로 직접 작성]',
            '',
            '## 3장. 연구 방법', str(data.get('methods_note') or '[실제 연구방법 입력 필요]'),
            '',
            '## 4장. 연구 결과', str(data.get('results_note') or '[연구 수행 후 실제 결과 입력 필요]'),
            '',
            '## 5장. 논의·결론', str(data.get('discussion') or '[실제 연구 결과가 확인된 후 작성]'),
            '',
            '## 참고문헌 (정식 표기)',
            *([f'{i}. {ref}' for i,ref in enumerate(reference_list,1)] if reference_list else ['[원문 검증된 참고문헌 추가 필요]']),
            '',
            '> 생성된 텍스트는 사용자가 작성한 메모·인증 전 문헌 기록을 정리한 초안이며, '
            '실제 연구 결과나 독창성을 보증하지 않습니다.',
        ]
        text = '\n'.join(doc)
        st.text_area('Markdown 초안 미리보기', text[:25000], height=380, disabled=True)
        st.download_button('📄 내 논문 초안 (.md) 다운로드', text.encode('utf-8-sig'),
                           file_name='나의_석사학위논문_초안.md', mime='text/markdown')
        st.caption('정식 참고문헌은 03에 저장한 논문만 반영하며, 서지정보 검증은 최종 제출 전에 직접 확인해야 합니다.')
