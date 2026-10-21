"""Official university repository entry points and honest external keyword search.

Keyword search uses Google site: filtering; no institutional API or PDF download
is implied. The repository search page is a separate link and does not receive
keywords automatically. Sources: https://www.dcollection.net/common/instList.do
"""
from urllib.parse import urlencode, urlparse
import html
import re

DCOLLECTION_DIRECTORY = "https://www.dcollection.net/common/instList.do"
DCOLLECTION_GUIDE = "https://www.dcollection.net/"
ALL_UNIVERSITIES = "기타 대학 (참여대학 목록에서 선택)"

UNIVERSITY_DCOLLECTION = {
    "고려대학교": "https://dc.korea.ac.kr/srch/srchSearch",
    "서울대학교": "https://dcollection.snu.ac.kr",
    "연세대학교": "https://dcollection.yonsei.ac.kr/srch/srchSearch",
    "성균관대학교": "https://dcollection.skku.ac.kr",
    "부산대학교": "https://dcollection.pusan.ac.kr",
    # User-confirmed repository: https://sjcu.dcollection.net
    "세종사이버대학교": "https://sjcu.dcollection.net",
}
UNIVERSITY_SEARCH_PAGES = {
    "세종사이버대학교": "https://sjcu.dcollection.net/srch/srchSearch",
}


def universities() -> list[str]:
    """Available official repository choices plus the national directory."""
    return list(UNIVERSITY_DCOLLECTION) + [ALL_UNIVERSITIES]


def normalize_title_or_topic(value: str) -> str:
    """Normalize user text without HTML markup or uncontrolled long queries."""
    clean = html.unescape(str(value or ""))
    clean = re.sub(r"<[^>]*>", " ", clean)
    return " ".join(clean.split())[:200]


def make_dcollection_destinations(university: str, keyword: str) -> dict:
    """Two distinct destinations: real external keyword search and site entry.

    External Google search includes the entered keyword with a site: scope.
    Visiting the repository entry does NOT itself execute keyword search.
    """
    if university not in universities():
        raise ValueError("선택할 수 없는 대학입니다.")
    phrase = normalize_title_or_topic(keyword)
    home = UNIVERSITY_DCOLLECTION.get(university, DCOLLECTION_DIRECTORY)
    page = UNIVERSITY_SEARCH_PAGES.get(university, home)
    host = urlparse(home).hostname or "www.dcollection.net"
    scope = "site:dcollection.net" if university == ALL_UNIVERSITIES else f"site:{host}"
    query = f'{scope} "{phrase}"' if phrase else scope
    google_url = "https://www.google.com/search?" + urlencode({"q": query})
    return {
        "source_type": "directory" if university == ALL_UNIVERSITIES else "dcollection",
        "button_label": ("전국 dCollection 참여대학 목록 열기" if university == ALL_UNIVERSITIES
                         else f"{university} dCollection 열기"),
        "source_note": (
            "키워드 검색은 Google에서 해당 대학 저장소를 대상으로 실제 웹 검색을 수행합니다. "
            "학교 dCollection 자체 검색은 별도 페이지에서 직접 수행합니다. "
            "검색 엔진에 색인되지 않은 자료는 표시되지 않을 수 있습니다."
        ),
        "university": university,
        "keyword": phrase,
        "repository_url": home,
        "repository_search_url": page,
        "web_search_url": google_url,
        "search_query": query,
        "search_engine": "Google 외부 웹검색",
        "directory_url": DCOLLECTION_DIRECTORY,
        "guide_url": DCOLLECTION_GUIDE,
    }


def no_results_from_nanet(total_count: int, collected_count: int, attempts: list) -> bool:
    """Only actual API zero results cause prominent fallback messaging."""
    return bool(attempts) and int(total_count) == 0 and int(collected_count) == 0
