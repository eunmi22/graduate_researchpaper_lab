"""Keyword search-link generator for society, association and report sources.

All targets are verified public domains. Most use a Google site: query (actual
external search); Google Scholar uses its public search URL. There is NO
unapproved third-party API or automatic indexing/scraping in this module.
"""
from urllib.parse import urlencode
from dcollection_fallback import normalize_title_or_topic

# display_name: official homepage/search landing page, Google site domain, content category
RESEARCH_SOURCES = {
    "KCI 한국학술지인용색인": (
        "https://www.kci.go.kr/kciportal/po/search/poArtiSear.kci", "kci.go.kr", "학회·학술논문"
    ),
    "한국정보보호학회": (
        "https://kiisc.or.kr", "kiisc.or.kr", "학회·학술논문"
    ),
    "한국중견기업연합회": (
        "https://fomek.or.kr", "fomek.or.kr", "협회·정책자료"
    ),
    "KISA 한국인터넷진흥원": (
        "https://www.kisa.or.kr", "kisa.or.kr", "보안·산업보고서"
    ),
    "NIA 한국지능정보사회진흥원": (
        "https://www.nia.or.kr", "nia.or.kr", "정책·연구보고서"
    ),
    "KISTI ScienceON": (
        "https://scienceon.kisti.re.kr", "scienceon.kisti.re.kr", "논문·국가R&D보고서"
    ),
    "국회입법조사처": (
        "https://www.nars.go.kr", "nars.go.kr", "입법·정책보고서"
    ),
    "Google Scholar": (
        "https://scholar.google.com", "scholar.google.com", "학술자료 통합검색"
    ),
}
ALL_RESEARCH_SOURCES = "모든 기관 (웹검색)"


def research_source_names() -> list[str]:
    return [ALL_RESEARCH_SOURCES] + list(RESEARCH_SOURCES)


def research_search_destination(source: str, keyword: str) -> dict:
    """Return verified source page and keyword-bearing search results URL."""
    if source not in research_source_names():
        raise ValueError("지원하지 않는 자료 출처입니다.")
    term = normalize_title_or_topic(keyword)
    if source == ALL_RESEARCH_SOURCES:
        sites = ["kci.go.kr", "kiisc.or.kr", "fomek.or.kr", "kisa.or.kr",
                 "nia.or.kr", "scienceon.kisti.re.kr", "nars.go.kr"]
        scope = "(" + " OR ".join(f"site:{s}" for s in sites) + ")"
        query = f'"{term}" {scope}' if term else scope
        return {
            "name": source, "category": "학회·협회·연구보고서 통합",
            "homepage_url": "https://www.kci.go.kr/kciportal/po/search/poArtiSear.kci",
            "search_url": "https://www.google.com/search?" + urlencode({"q": query}),
            "search_engine": "Google 기관 한정 웹검색", "search_query": query,
            "keyword": term,
        }
    homepage, domain, category = RESEARCH_SOURCES[source]
    if source == "Google Scholar":
        query = term
        search_url = "https://scholar.google.com/scholar?" + urlencode({"q": term})
        engine = "Google Scholar 공식 검색"
    else:
        query = f'site:{domain} "{term}"' if term else f"site:{domain}"
        search_url = "https://www.google.com/search?" + urlencode({"q": query})
        engine = "Google 기관 한정 웹검색"
    return {
        "name": source, "category": category, "homepage_url": homepage,
        "search_url": search_url, "search_engine": engine,
        "search_query": query, "keyword": term,
    }


def research_search_table(keyword: str) -> list[dict]:
    """Provide independently clickable links for the overview table."""
    return [
        {
            "기관/검색처": source,
            "자료 유형": RESEARCH_SOURCES[source][2],
            "키워드 검색 결과": research_search_destination(source, keyword)["search_url"],
            "공식 홈페이지": RESEARCH_SOURCES[source][0],
        }
        for source in RESEARCH_SOURCES
    ]
