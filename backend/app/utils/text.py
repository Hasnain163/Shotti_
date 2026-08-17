"""Text cleaning and length control for scraped web content.

Scraped markdown is mostly usable but carries navigation, cookie banners, and
share widgets that waste prompt budget and can mislead the analysis stage. These
helpers trim that down without touching the substance of the page.
"""

import re
import unicodedata
from urllib.parse import urlparse, urlunparse

# The target part of a markdown link. One level of nested parentheses is allowed
# because real URLs contain them — "/wiki/Champions_Trophy_(real_tennis)" would
# otherwise terminate the match early and leave the tail behind as junk.
_LINK_TARGET = r"\((?:[^()]|\([^()]*\))*\)"
# Markdown images carry no evidential value once the alt text is gone.
_IMAGE_RE = re.compile(r"!\[[^\]]*\]" + _LINK_TARGET)
# Keep link text, drop the URL: "[Dhaka floods](http://…)" -> "Dhaka floods".
# The text may be empty ("[](url)" is a bare icon link), in which case nothing is kept.
_LINK_RE = re.compile(r"\[([^\]]*)\]" + _LINK_TARGET)
# Table cell separators left over once the cells are unwrapped.
_PIPE_RE = re.compile(r"[ \t]*\|[ \t]*")
_HEADING_MARKS_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
# Scraped markdown keeps some inline HTML ("ইংল্যান্ড<br>ওয়েলস"). Only a known tag
# list is stripped, so ordinary text like "x < 5 and y > 2" is left alone.
_HTML_TAG_RE = re.compile(
    r"</?(?:br|p|div|span|a|img|b|i|u|strong|em|small|sup|sub|ul|ol|li"
    r"|table|thead|tbody|tr|td|th|h[1-6])\b[^>]{0,200}?/?>",
    re.IGNORECASE,
)
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SPACES_RE = re.compile(r"[ \t ]{2,}")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?[\s:|-]{6,}\|?\s*$", re.MULTILINE)

# Lines that are page furniture rather than content. Matched case-insensitively
# against the whole (stripped) line, so real sentences containing these words survive.
_BOILERPLATE_PATTERNS = (
    r"accept (all )?cookies?",
    r"we use cookies.*",
    r"cookie (policy|settings|preferences)",
    r"subscribe( now| to.*)?",
    r"sign (up|in)( now)?",
    r"log ?in",
    r"share (this|on).*",
    r"follow us( on.*)?",
    r"advertisement",
    r"read more",
    r"related (news|articles?|stories)",
    r"most (read|popular)",
    r"back to top",
    r"skip to (main )?content",
    r"all rights reserved.*",
    r"privacy policy",
    r"terms (of|and) (use|service|conditions)",
    r"comments? \(\d+\)",
    r"©.*",
    # Wiki chrome, seen on every Wikipedia scrape.
    r"jump to content",
    r"from wikipedia, the free encyclopedia",
    r"বিষয়বস্তুতে চলুন",
    r"উইকিপিডিয়া, মুক্ত বিশ্বকোষ থেকে",
    r"toggle .*",
    r"\d+ languages?",
    r"edit",
    r"contents",
    r"references",
    r"external links",
    r"see also",
    # Consent banners and share widgets that carry inline text.
    r"by using this site.*",
    r"ok",
    r"print news",
    r"soc[ai]+l share.*",
)
_BOILERPLATE_RE = re.compile(
    r"^(?:" + "|".join(_BOILERPLATE_PATTERNS) + r")$", re.IGNORECASE
)

_SENTENCE_END_RE = re.compile(r"[.!?।]\s")


def domain_of(url: str) -> str:
    """Host of a URL without the www prefix. Empty string when unparseable."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def canonical_url(url: str) -> str:
    """Normalise a URL for de-duplication.

    Two links to the same article differing only by scheme, www, tracking
    parameters, a fragment, or a trailing slash must collapse to one key.
    """
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return url.strip().lower()

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    path = parts.path.rstrip("/") or "/"

    # Drop tracking parameters; keep the rest so paginated/queried pages stay distinct.
    kept = []
    for pair in parts.query.split("&"):
        if not pair:
            continue
        key = pair.split("=", 1)[0].lower()
        if key.startswith("utm_") or key in {"fbclid", "gclid", "igshid", "ref", "amp"}:
            continue
        kept.append(pair)

    return urlunparse(("https", host, path, "", "&".join(sorted(kept)), ""))


def clean_scraped_text(markdown: str) -> str:
    """Strip markdown noise and page furniture from scraped content."""
    if not markdown:
        return ""

    text = _IMAGE_RE.sub("", markdown)
    text = _LINK_RE.sub(r"\1", text)
    text = _TABLE_DIVIDER_RE.sub("", text)
    text = _HEADING_MARKS_RE.sub("", text)
    text = _PIPE_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)

    kept_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if _BOILERPLATE_RE.match(line):
            continue
        # Drop lines that are only punctuation or list bullets left behind by the
        # substitutions above.
        if line and not re.search(r"[\wঀ-৿]", line):
            continue
        # Two characters cannot carry evidence, but they are exactly what consent
        # buttons and unwrapped icon links leave behind.
        if 0 < len(line) <= 2:
            continue
        kept_lines.append(line)

    text = "\n".join(kept_lines)
    text = _SPACES_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


_QUOTE_NOISE_RE = re.compile(r"[\s​-‍]+")
_ELLIPSIS_RE = re.compile(r"\s*(?:\.{3}|…|\[\.\.\.\])\s*")
# Fragments shorter than this match almost anything, so they prove nothing.
_MIN_FRAGMENT_CHARS = 12


def normalize_for_match(text: str) -> str:
    """Fold text for tolerant comparison.

    Unicode-normalises (so identically-rendered Bangla compares equal), collapses
    whitespace and zero-width joiners, and casefolds. Meaning is untouched — this
    is only used to compare, never to store or display.
    """
    folded = unicodedata.normalize("NFC", text)
    folded = _QUOTE_NOISE_RE.sub(" ", folded)
    return folded.strip().casefold()


def quote_is_grounded(quote: str, source_content: str) -> bool:
    """True when ``quote`` genuinely appears in ``source_content``.

    This is the check that stops a model from attributing invented words to a real
    source. It is deliberately tolerant about presentation but strict about
    substance:

    * whitespace, case, and unicode form may differ
    * a quote may elide with "..." — every fragment must still appear, in order
    * very short fragments are ignored, since they match by coincidence

    A quote that survives this is text the page actually contains.
    """
    needle = normalize_for_match(quote)
    haystack = normalize_for_match(source_content)
    if not needle or not haystack:
        return False

    fragments = [
        fragment
        for fragment in (part.strip() for part in _ELLIPSIS_RE.split(needle))
        if len(fragment) >= _MIN_FRAGMENT_CHARS
    ]
    if not fragments:
        # Too short to elide meaningfully; require the whole thing verbatim.
        return needle in haystack

    position = 0
    for fragment in fragments:
        found = haystack.find(fragment, position)
        if found == -1:
            return False
        position = found + len(fragment)
    return True


def truncate_text(text: str, limit: int) -> str:
    """Cut text to ``limit`` characters, preferring a clean break.

    Tries a paragraph break, then a sentence end (including the Bangla danda),
    then falls back to a hard cut. Cutting mid-sentence invites the analysis stage
    to misread a fragment as a complete statement.
    """
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text

    window = text[:limit]

    paragraph_break = window.rfind("\n\n")
    if paragraph_break >= limit * 0.6:
        return window[:paragraph_break].rstrip()

    sentence_ends = [match.end() for match in _SENTENCE_END_RE.finditer(window)]
    if sentence_ends and sentence_ends[-1] >= limit * 0.5:
        return window[: sentence_ends[-1]].rstrip()

    space = window.rfind(" ")
    if space >= limit * 0.5:
        return window[:space].rstrip() + "…"
    return window.rstrip() + "…"
