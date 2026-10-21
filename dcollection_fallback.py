"""University dCollection links for manual full-text discovery.

These are official university repository home/search pages, not PDF download links.
Google site-search is an external convenience query, NOT a dCollection API call.
Sources: https://www.dcollection.net/common/instList.do
University source websites are documented in README.md.
"""

from urllib.parse import urlencode, urlparse
import html
import re

DCOLLECTION_DIRECTORY = "https://www.dcollection.net/common/instList.do"
DCOLLECTION_GUIDE = "https://www.dcollection.net/common/guideView.do?guideId=000000000001"
ALL_UNIVERSITIES = "\uae30\ud0c0 \ub300\ud559 (\ucc38\uc5ec\ub300\ud559 \ubaa9\ub85d\uc5d0\uc11c \uc120\ud0dd)"

# The source URLs were verified against university sites and official notices.
UNIVERSITY_DCOLLECTION = {
    "\uace0\ub824\ub300\ud559\uad50": "https://dc.korea.ac.kr/srch/srchSearch",
    "\uc11c\uc6b8\ub300\ud559\uad50": "https://dcollection.snu.ac.kr",
    "\uc5f0\uc138\ub300\ud559\uad50": "https://dcollection.yonsei.ac.kr/srch/srchSearch",
    "\uc131\uade0\uad00\ub300\ud559\uad50": "https://dcollection.skku.ac.kr",
    "\ubd80\uc0b0\ub300\ud559\uad50": "https://dcollection.pusan.ac.kr",
}


def universities() -> list[str]:
    """Return a short verified subset plus the official directory for others."""
    return list(UNIVERSITY_DCOLLECTION) + [ALL_UNIVERSITIES]


def normalize_title_or_topic(value: str) -> str:
    """Keep a useful search phrase, not HTML markups or unbounded input."""
    clean = html.unescape(str(value or ""))
    clean = re.sub(r"<[^>]*>", " ", clean)
    return " ".join(clean.split())[:200]


def make_dcollection_destinations(university: str, keyword: str) -> dict:
    """Provide a repository page, site-limited web search, and directory.

    Search engines may omit or lag records; links do not establish availability.
    """
    if university not in universities():
        raise ValueError("Unsupported university")
    phrase = normalize_title_or_topic(keyword)
    site_url = UNIVERSITY_DCOLLECTION.get(university, DCOLLECTION_DIRECTORY)
    domain = urlparse(site_url).hostname or "www.dcollection.net"
    # Direct repository search query formats differ by university; do not guess.
    # Google site-restricted query is a fallback helper, not an official API.
    scope = f"site:{domain}" if university != ALL_UNIVERSITIES else "site:dcollection.net"
    search_term = " ".join(part for part in (scope, phrase) if part)
    external_search = ("https://www.google.com/search?" + urlencode({"q": search_term}))
    return {
        "university": university,
        "keyword": phrase,
        "repository_url": site_url,
        "web_search_url": external_search,
        "directory_url": DCOLLECTION_DIRECTORY,
        "guide_url": DCOLLECTION_GUIDE,
    }


def no_results_from_nanet(total_count: int, collected_count: int, attempts: list) -> bool:
    """Only genuinely zero returned counts trigger the prominent fallback.

    If API says total>0 but parser extracts 0, it is not proof of non-holding.
    """
    return bool(attempts) and int(total_count) == 0 and int(collected_count) == 0
