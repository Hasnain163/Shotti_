"""Publisher classification and a coarse credibility ranking.

This is a small hand-maintained table, not a judgement about truth. It only decides
which pages are worth spending a scrape on first, and labels the publisher type so
the analysis stage can weigh a government statistic differently from a forum post.
A high score never means a source is correct.
"""

from app.models.source import SourceType

# Score bands: 100 fact-check, 90 official, 80 reference, 70 quality news,
# 60 other news, 20 user-generated, 10 unknown.
FACT_CHECK_DOMAINS = {
    "rumorscanner.com",
    "jachai.org",
    "factwatchbd.com",
    "boomlive.in",
    "bangla.boomlive.in",
    "altnews.in",
    "factcheck.org",
    "politifact.com",
    "snopes.com",
    "fullfact.org",
    "afp.com",
    "factcheck.afp.com",
    "reuters.com/fact-check",
    "leadstories.com",
}

BANGLADESHI_NEWS_DOMAINS = {
    "prothomalo.com",
    "en.prothomalo.com",
    "thedailystar.net",
    "bdnews24.com",
    "dhakatribune.com",
    "newagebd.net",
    "tbsnews.net",
    "banglatribune.com",
    "jugantor.com",
    "kalerkantho.com",
    "ittefaq.com.bd",
    "samakal.com",
    "risingbd.com",
    "bssnews.net",
    "observerbd.com",
    "daily-sun.com",
    "financialexpress.com.bd",
    "bonikbarta.com",
    "somoynews.tv",
    "jamuna.tv",
    "channelionline.com",
    "independent.bd",
}

INTERNATIONAL_NEWS_DOMAINS = {
    "bbc.com",
    "bbc.co.uk",
    "reuters.com",
    "apnews.com",
    "aljazeera.com",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "cnn.com",
    "dw.com",
    "ft.com",
    "economist.com",
    "npr.org",
    "thehindu.com",
    "indianexpress.com",
    "timesofindia.indiatimes.com",
    "scroll.in",
    "anadoluagency.com",
}

ENCYCLOPEDIA_DOMAINS = {
    "wikipedia.org",
    "britannica.com",
    "bn.wikipedia.org",
    "en.wikipedia.org",
}

OFFICIAL_DOMAINS = {
    "who.int",
    "un.org",
    "worldbank.org",
    "imf.org",
    "unicef.org",
    "usgs.gov",
    "nasa.gov",
    "cdc.gov",
    "nih.gov",
    "bbs.gov.bd",
    "bmd.gov.bd",
    "dghs.gov.bd",
    "bb.org.bd",
    "ec.org.bd",
}

ACADEMIC_DOMAINS = {
    "nature.com",
    "science.org",
    "thelancet.com",
    "nejm.org",
    "bmj.com",
    "pubmed.ncbi.nlm.nih.gov",
    "arxiv.org",
    "jstor.org",
}

SOCIAL_DOMAINS = {
    "facebook.com",
    "m.facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "reddit.com",
    "quora.com",
    "pinterest.com",
    "threads.net",
    "telegram.me",
    "t.me",
}

BLOG_DOMAINS = {
    "medium.com",
    "blogspot.com",
    "wordpress.com",
    "substack.com",
    "tumblr.com",
    "wix.com",
}

# Official/academic suffixes catch the long tail that no explicit list can cover.
_OFFICIAL_SUFFIXES = (".gov", ".gov.bd", ".gov.uk", ".mil", ".int")
_ACADEMIC_SUFFIXES = (".edu", ".edu.bd", ".ac.uk", ".ac.bd")


def _matches(domain: str, known: set[str]) -> bool:
    """True when the domain equals, or is a subdomain of, a known entry."""
    return any(domain == entry or domain.endswith("." + entry) for entry in known)


def classify_domain(domain: str) -> SourceType:
    """Categorise a publisher by domain. Unknown domains fall back to OTHER."""
    if not domain:
        return SourceType.OTHER
    domain = domain.lower()

    if _matches(domain, FACT_CHECK_DOMAINS):
        return SourceType.FACT_CHECK
    if _matches(domain, SOCIAL_DOMAINS):
        return SourceType.SOCIAL
    if _matches(domain, BLOG_DOMAINS):
        return SourceType.BLOG
    if _matches(domain, ENCYCLOPEDIA_DOMAINS):
        return SourceType.ENCYCLOPEDIA
    if _matches(domain, ACADEMIC_DOMAINS) or domain.endswith(_ACADEMIC_SUFFIXES):
        return SourceType.ACADEMIC
    if _matches(domain, OFFICIAL_DOMAINS) or domain.endswith(_OFFICIAL_SUFFIXES):
        return SourceType.GOVERNMENT
    if _matches(domain, BANGLADESHI_NEWS_DOMAINS) or _matches(
        domain, INTERNATIONAL_NEWS_DOMAINS
    ):
        return SourceType.NEWS
    return SourceType.OTHER


def credibility_score(domain: str, source_type: SourceType | None = None) -> int:
    """Rank a publisher for scrape ordering. Higher is fetched first."""
    if not domain:
        return 0
    domain = domain.lower()
    kind = source_type or classify_domain(domain)

    if kind is SourceType.FACT_CHECK:
        return 100
    if kind is SourceType.GOVERNMENT:
        return 90
    if kind is SourceType.ACADEMIC:
        return 85
    if kind is SourceType.ENCYCLOPEDIA:
        return 80
    if kind is SourceType.NEWS:
        # Local outlets often carry Bangladesh stories the wires never covered.
        if _matches(domain, BANGLADESHI_NEWS_DOMAINS):
            return 75
        if _matches(domain, INTERNATIONAL_NEWS_DOMAINS):
            return 70
        return 60
    if kind is SourceType.BLOG:
        return 25
    if kind is SourceType.SOCIAL:
        # Where misinformation usually starts; near-useless as verification.
        return 15
    return 40
