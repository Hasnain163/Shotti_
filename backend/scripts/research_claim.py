"""Manually inspect the Firecrawl research agent against the real API.

Chains the two agents built so far: Gemini generates the search queries, Firecrawl
gathers the evidence. Still produces no verdict.

    cd backend
    ./.venv/Scripts/python.exe scripts/research_claim.py "বাংলাদেশে ডেঙ্গু বেড়েছে"
    ./.venv/Scripts/python.exe scripts/research_claim.py --queries "Dhaka earthquake 2026"
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.services.firecrawl import FirecrawlService  # noqa: E402
from app.services.gemini import GeminiService  # noqa: E402
from app.utils.errors import ShottiError  # noqa: E402

DEFAULT_CLAIM = "Bangladesh won the ICC Champions Trophy in 2017."


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = get_settings()
    if not settings.firecrawl_api_key:
        print("FIRECRAWL_API_KEY is not set. Add it to the repo-root .env file.")
        return 1

    args = sys.argv[1:]
    direct_queries = "--queries" in args
    if direct_queries:
        args.remove("--queries")
    inputs = args or [DEFAULT_CLAIM]

    gemini = GeminiService(settings)
    firecrawl = FirecrawlService(settings)

    try:
        if direct_queries:
            queries = inputs
            print(f"QUERIES: {queries}")
        else:
            claim = inputs[0]
            print(f"CLAIM: {claim}")
            if not settings.gemini_api_key:
                print("GEMINI_API_KEY is not set; pass --queries to skip claim analysis.")
                return 1
            analysis = await gemini.analyze_claim(claim)
            queries = analysis.search_queries
            print(f"  normalized: {analysis.normalized_claim}")
            print(f"  queries   : {queries}")

        bundle = await firecrawl.research(queries)
    except ShottiError as exc:
        print(f"FAILED [{exc.error_code}] {exc.message}")
        return 1
    finally:
        await gemini.aclose()
        await firecrawl.aclose()

    print()
    print(f"candidates found : {bundle.candidates_found}")
    print(f"queries used     : {len(bundle.queries_used)}")
    print(f"queries failed   : {bundle.queries_failed or '-'}")
    print(f"sources kept     : {len(bundle.sources)}")
    print(f"total chars      : {bundle.total_content_chars}")
    print(f"degraded         : {bundle.degraded}")

    for index, source in enumerate(bundle.sources):
        print("-" * 70)
        print(f"[{index}] {source.title}")
        print(f"     {source.url}")
        print(
            f"     domain={source.domain}  type={source.source_type.value}  "
            f"date={source.published_date or 'unknown'}  score={source.credibility}"
        )
        print(f"     chars={len(source.content)}  via={source.found_by_query!r}")
        preview = source.content[:220].replace("\n", " ")
        print(f"     {preview}…")

    if bundle.failures:
        print("-" * 70)
        print("FAILURES:")
        for failure in bundle.failures:
            print(f"  {failure.domain or failure.url}: {failure.reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
