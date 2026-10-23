"""사용자 PC에서만 실행하는 선택형 실서비스 점검. 인증키와 요청 URL은 출력하지 않습니다.
실행: python check_live.py --keyword "데이터베이스 포렌식" --pages 1
실제 승인 키가 .env 또는 환경변수에 있어야 하며 API 요청 한도를 사용합니다.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from paperlab import PaperAPIError
from nanet_search_flow import search_literature_basic
from nanet_metadata import CATEGORY_ORDER

def main() -> int:
    parser=argparse.ArgumentParser(description='P0 실서비스 검색 진단 (키 비출력)')
    parser.add_argument('--keyword', default='데이터베이스 포렌식')
    parser.add_argument('--pages', type=int, choices=range(1,6), default=1)
    parser.add_argument('--per-page', type=int, choices=(5,10,15,20), default=20)
    parser.add_argument('--field', choices=('전체','기본검색','자료명','키워드'), default='전체')
    parser.add_argument('--output', default='live_check.json')
    args=parser.parse_args()
    load_dotenv(Path(__file__).resolve().parent/'.env')
    key=os.getenv('DATA_GO_KR_API_KEY','').strip()
    if not key:
        print('DATA_GO_KR_API_KEY가 없습니다. .env를 설정하세요. 키를 채팅이나 저장소에 올리지 마세요.')
        return 2
    diagnostics=[]
    try:
        result=search_literature_basic(key,args.keyword,pages=args.pages,per_page=args.per_page,
            search_field=args.field,automatic_retry=False,diagnostics=diagnostics)
        counts={k:int(result.catalog.get('자료분류', []).eq(k).sum()) if not result.catalog.empty else 0 for k in CATEGORY_ORDER}
        title_count=int(result.catalog['자료명/저자사항'].fillna('').eq('').sum()) if not result.catalog.empty else 0
        report={'version':'2.3.4-P0','query':result.used_keyword,'search_field':args.field,
                'api_total':result.total,'collected':len(result.catalog),'by_type':counts,
                'missing_title':title_count,'next_page':result.next_page,'errors':result.errors,
                'diagnostics':diagnostics,
                'website_match':'미검증: 실제 공식 웹 목록과 별도 대조 필요'}
        assert sum(counts.values())==len(result.catalog)
        assert result.catalog.empty or result.catalog.loc[result.catalog['controlno'].ne(''),'controlno'].is_unique
        Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'API 전체 {result.total:,}건 / 수집 {len(result.catalog):,}건 / 제목 누락 {title_count:,}건')
        print(counts)
        print(f'인증키를 제외한 진단 저장: {args.output}')
        if result.errors:
            print('API 또는 목록 문제를 진단 파일에서 확인하세요. 전체 검색 성공으로 간주하지 않습니다.')
            return 1
        return 0
    except (PaperAPIError, ValueError) as exc:
        message=str(exc).replace(key,'[인증키 제외]')
        print('검색 점검 실패:',message)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
