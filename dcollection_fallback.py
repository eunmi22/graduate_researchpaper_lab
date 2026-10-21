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

# This school has an official thesis-research guide, but we did not verify
# a school-specific dCollection repository. Do not invent a repository URL.
UNIVERSITY_OFFICIAL_RESEARCH = {
    "세종사이버대학교": "https://graduate.sjcu.ac.kr/graduate/life/search-for-papers.do",
}


def universities() -> list[str]:
    """Return universities with verified links and a fallback directory."""
    return list(UNIVERSITY_DCOLLECTION) + list(UNIVERSITY_OFFICIAL_RESEARCH) + [ALL_UNIVERSITIES]


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
    site_url = UNIVERSITY_DCOLLECTION.get(
        university, UNIVERSITY_OFFICIAL_RESEARCH.get(university, DCOLLECTION_DIRECTORY)
    )
    domain = urlparse(site_url).hostname or "www.dcollection.net"
    is_official_guide = university in UNIVERSITY_OFFICIAL_RESEARCH
    # University guide is not a dCollection repository or a live paper-search API.
    # In this case provide a broad school+topic web search as the secondary link.
    if is_official_guide:
        search_term = " ".join(part for part in (f'"{university}"', phrase, "\ub17c\ubb38") if part)
        source_type = "university_research_guide"
        button_label = "\uc138\uc885\uc0ac\uc774\ubc84\ub300 \ub17c\ubb38\uac80\uc0c9 \uc548\ub0b4 \uc5f4\uae30"
        source_note = (
            "\uc138\uc885\uc0ac\uc774\ubc84\ub300\ud559\uad50\uc758 \ubcc4\ub3c4 dCollection \uc800\uc7a5\uc18c \uc8fc\uc18c\ub294 \ud655\uc778\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4. "
            "\ub300\uc2e0 \ud559\uad50 \ub300\ud559\uc6d0\uc758 \uacf5\uc2dd \ub17c\ubb38\uac80\uc0c9(KISS \uc774\uc6a9) \uc548\ub0b4 \ud398\uc774\uc9c0\ub85c \uc774\ub3d9\ud569\ub2c8\ub2e4. "
            "\ud574\ub2f9 \ud398\uc774\uc9c0\ub294 \uac1c\ubcc4 \ud559\uc704\ub17c\ubb38\uc744 \uc790\ub3d9\uc73c\ub85c \uac80\uc0c9\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4."
        )
    else:
        # Direct repository query formats differ by institution, so do not guess.
        scope = f"site:{domain}" if university != ALL_UNIVERSITIES else "site:dcollection.net"
        search_term = " ".join(part for part in (scope, phrase) if part)
        source_type = "directory" if university == ALL_UNIVERSITIES else "dcollection"
        button_label = ("\uc804\uad6d dCollection \ucc38\uc5ec\ub300\ud559 \ubaa9\ub85d"
                        if university == ALL_UNIVERSITIES else "\ub300\ud559 dCollection \uc5f4\uae30")
        source_note = ""
    external_search = ("https://www.google.com/search?" + urlencode({"q": search_term}))
    return {
        "source_type": source_type,
        "button_label": button_label,
        "source_note": source_note,
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
