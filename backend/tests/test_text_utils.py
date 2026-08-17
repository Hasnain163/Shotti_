"""Tests for URL normalisation, content cleaning, truncation, and quote grounding."""

from app.utils.text import (
    canonical_url,
    clean_scraped_text,
    domain_of,
    quote_is_grounded,
    truncate_text,
)


class TestDomainOf:
    def test_strips_www_and_lowercases(self) -> None:
        assert domain_of("https://WWW.Prothomalo.COM/news/123") == "prothomalo.com"

    def test_keeps_meaningful_subdomain(self) -> None:
        assert domain_of("https://en.prothomalo.com/x") == "en.prothomalo.com"

    def test_garbage_returns_empty_string(self) -> None:
        assert domain_of("not a url") == ""
        assert domain_of("") == ""


class TestCanonicalUrl:
    def test_collapses_scheme_www_slash_and_fragment(self) -> None:
        variants = [
            "http://www.example.com/article/",
            "https://example.com/article",
            "https://www.example.com/article#comments",
        ]
        keys = {canonical_url(url) for url in variants}
        assert len(keys) == 1

    def test_drops_tracking_parameters(self) -> None:
        clean = canonical_url("https://example.com/a")
        tracked = canonical_url("https://example.com/a?utm_source=fb&fbclid=xyz")
        assert clean == tracked

    def test_keeps_meaningful_query_parameters(self) -> None:
        assert canonical_url("https://example.com/a?id=1") != canonical_url(
            "https://example.com/a?id=2"
        )

    def test_query_parameter_order_does_not_matter(self) -> None:
        assert canonical_url("https://e.com/a?b=1&a=2") == canonical_url(
            "https://e.com/a?a=2&b=1"
        )


class TestCleanScrapedText:
    def test_removes_images_and_unwraps_links(self) -> None:
        cleaned = clean_scraped_text("![logo](http://x/l.png)\n[Dhaka floods](http://x/a)")
        assert "l.png" not in cleaned
        assert "http://x/a" not in cleaned
        assert "Dhaka floods" in cleaned

    def test_removes_icon_links_with_empty_text(self) -> None:
        """Bare icon links are everywhere on real pages and leave URL junk behind."""
        cleaned = clean_scraped_text("[](https://bn.wikipedia.org/wiki/File:X.JPG)\nReal text here.")
        assert "wikipedia.org" not in cleaned
        assert "Real text here." in cleaned

    def test_handles_urls_containing_parentheses(self) -> None:
        raw = '[2017 Champions Trophy](/wiki/2017_CT_(real_tennis) "2017 CT (real tennis)")'
        cleaned = clean_scraped_text(raw)
        assert cleaned == "2017 Champions Trophy"

    def test_strips_inline_html_tags(self) -> None:
        cleaned = clean_scraped_text("ইংল্যান্ড<br>ওয়েলস <strong>বিজয়ী</strong> পাকিস্তান")
        assert "<br>" not in cleaned and "strong" not in cleaned
        assert "বিজয়ী" in cleaned and "পাকিস্তান" in cleaned

    def test_leaves_comparison_operators_alone(self) -> None:
        """Only known tags are stripped, so arithmetic in prose survives."""
        text = "Inflation was < 5 percent while growth was > 2 percent."
        assert clean_scraped_text(text) == text

    def test_removes_table_pipes(self) -> None:
        assert "|" not in clean_scraped_text("| Team | Score |\n| --- | --- |\n| BD | 200 |")

    def test_removes_wiki_and_consent_chrome(self) -> None:
        raw = "\n".join(
            [
                "Jump to content",
                "From Wikipedia, the free encyclopedia",
                "By using this site, you agree to our Privacy Policy.",
                "OK",
                "socal share facebook icons",
                "Pakistan beat India by 180 runs in the final.",
            ]
        )
        cleaned = clean_scraped_text(raw)
        assert cleaned == "Pakistan beat India by 180 runs in the final."

    def test_removes_page_furniture(self) -> None:
        raw = "\n".join(
            [
                "Accept all cookies",
                "Subscribe now",
                "Share this",
                "Advertisement",
                "The earthquake struck at 3am local time.",
                "All rights reserved",
            ]
        )
        cleaned = clean_scraped_text(raw)
        assert "The earthquake struck at 3am local time." in cleaned
        for junk in ("cookies", "Subscribe", "Share this", "Advertisement"):
            assert junk not in cleaned

    def test_keeps_sentences_that_merely_contain_boilerplate_words(self) -> None:
        """Only whole furniture lines go; real prose using those words must survive."""
        raw = "The minister said users should subscribe to the new service."
        assert "minister" in clean_scraped_text(raw)

    def test_preserves_bangla_content(self) -> None:
        cleaned = clean_scraped_text("ঢাকায় ভূমিকম্প অনুভূত হয়েছে।")
        assert "ঢাকায় ভূমিকম্প অনুভূত হয়েছে।" in cleaned

    def test_collapses_excess_blank_lines(self) -> None:
        assert "\n\n\n" not in clean_scraped_text("a\n\n\n\n\nb")

    def test_empty_input_is_safe(self) -> None:
        assert clean_scraped_text("") == ""


class TestQuoteIsGrounded:
    """The check that stops invented words being attributed to a real source."""

    ARTICLE = (
        "Pakistan defeated India by 180 runs in the final on 18 June 2017. "
        "It was Pakistan's first Champions Trophy title."
    )

    def test_verbatim_quote_passes(self) -> None:
        assert quote_is_grounded("Pakistan defeated India by 180 runs", self.ARTICLE)

    def test_invented_quote_fails(self) -> None:
        assert not quote_is_grounded("India defeated Pakistan by 180 runs", self.ARTICLE)

    def test_presentation_differences_are_tolerated(self) -> None:
        assert quote_is_grounded("pakistan   DEFEATED india\n by 180 runs", self.ARTICLE)

    def test_elision_passes_when_all_fragments_are_real(self) -> None:
        quote = "Pakistan defeated India ... first Champions Trophy title"
        assert quote_is_grounded(quote, self.ARTICLE)

    def test_elision_fails_when_a_fragment_is_invented(self) -> None:
        quote = "Pakistan defeated India ... after a match-fixing inquiry"
        assert not quote_is_grounded(quote, self.ARTICLE)

    def test_fragments_must_appear_in_order(self) -> None:
        """Reordered fragments change the meaning, so they are not a real quote."""
        quote = "first Champions Trophy title ... Pakistan defeated India by 180"
        assert not quote_is_grounded(quote, self.ARTICLE)

    def test_bangla_quote_matches(self) -> None:
        article = "গতকাল ঢাকায় ৫.২ মাত্রার ভূমিকম্প অনুভূত হয়েছে। কোনো হতাহতের খবর নেই।"
        assert quote_is_grounded("ঢাকায় ৫.২ মাত্রার ভূমিকম্প অনুভূত হয়েছে", article)
        assert not quote_is_grounded("ঢাকায় ৭.৮ মাত্রার ভূমিকম্প অনুভূত হয়েছে", article)

    def test_empty_inputs_fail_closed(self) -> None:
        assert not quote_is_grounded("", self.ARTICLE)
        assert not quote_is_grounded("anything", "")


class TestTruncateText:
    def test_short_text_is_untouched(self) -> None:
        assert truncate_text("short", 100) == "short"

    def test_respects_the_limit(self) -> None:
        assert len(truncate_text("x " * 500, 100)) <= 101  # allows the ellipsis

    def test_prefers_a_paragraph_break(self) -> None:
        first = "The earthquake struck Dhaka before dawn and lasted eight seconds."
        text = first + "\n\n" + "Later coverage added little. " * 20
        # The break sits late enough in the window to be worth keeping.
        assert truncate_text(text, 80) == first

    def test_ignores_a_paragraph_break_that_would_discard_most_of_the_window(self) -> None:
        text = "Short intro.\n\n" + "The substance of the article follows here. " * 10
        result = truncate_text(text, 200)
        assert len(result) > 100

    def test_breaks_on_bangla_danda(self) -> None:
        text = "ঢাকায় ভূমিকম্প হয়েছে। " + "আরও তথ্য " * 30
        assert truncate_text(text, 40).endswith("।")

    def test_zero_limit_returns_empty(self) -> None:
        assert truncate_text("anything", 0) == ""
