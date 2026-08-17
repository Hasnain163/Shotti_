"""Manually inspect all three agents end to end against the real APIs.

Chains claim analysis -> web research -> evidence analysis. This is a development
inspection tool, not the pipeline: /api/verify is still the placeholder until the
pipeline step wires these together.

    cd backend
    ./.venv/Scripts/python.exe scripts/verify_claim.py "Bangladesh won the 2017 Champions Trophy"

Costs 2 Gemini calls and up to 2 searches + 6 scrapes per claim.
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
    missing = [
        name
        for name, present in (
            ("GEMINI_API_KEY", settings.gemini_api_key),
            ("FIRECRAWL_API_KEY", settings.firecrawl_api_key),
        )
        if not present
    ]
    if missing:
        print(f"Missing in the repo-root .env: {', '.join(missing)}")
        return 1

    claim = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CLAIM
    gemini = GeminiService(settings)
    firecrawl = FirecrawlService(settings)

    try:
        print("=" * 70)
        print(f"CLAIM: {claim}")

        print("\n[1/3] analysing claim…")
        claim_analysis = await gemini.analyze_claim(claim)
        print(f"  normalized : {claim_analysis.normalized_claim}")
        print(f"  language   : {claim_analysis.language.value}")
        print(f"  checkable  : {claim_analysis.is_checkable}")
        print(f"  queries    : {claim_analysis.search_queries}")

        if not claim_analysis.is_checkable:
            print(f"\n  not checkable: {claim_analysis.uncheckable_reason}")
            return 0

        print("\n[2/3] researching…")
        bundle = await firecrawl.research(claim_analysis.search_queries)
        print(f"  sources    : {len(bundle.sources)} (from {bundle.candidates_found} candidates)")
        for index, source in enumerate(bundle.sources):
            print(
                f"    [{index}] {source.domain} ({source.source_type.value}, "
                f"{source.published_date or 'no date'}, {len(source.content)} chars)"
            )

        print("\n[3/3] analysing evidence…")
        result = await gemini.analyze_evidence(claim_analysis, bundle.sources)
    except ShottiError as exc:
        print(f"\nFAILED [{exc.error_code}] {exc.message}")
        return 1
    finally:
        await gemini.aclose()
        await firecrawl.aclose()

    print()
    print("=" * 70)
    print(f"VERDICT    : {result.verdict.value}")
    print(f"CONFIDENCE : {result.confidence_score:.2f}")
    print(f"CONFLICTS  : {result.has_conflicting_evidence}")
    print(f"SPECULATION: {result.relies_on_speculation}")
    print(f"DROPPED    : {result.dropped_evidence_count} ungrounded quote(s)")
    print(f"\nEXPLANATION: {result.short_explanation}")

    for label, items in (
        ("SUPPORTING", result.supporting_evidence),
        ("CONTRADICTING", result.contradicting_evidence),
    ):
        print(f"\n{label} EVIDENCE:")
        if not items:
            print("  (none)")
        for item in items:
            source = bundle.sources[item.source_index]
            print(f"  [{item.source_index}] {source.domain}")
            print(f"      “{item.quote[:200]}”")

    if result.important_context:
        print("\nIMPORTANT CONTEXT:")
        for note in result.important_context:
            print(f"  - {note}")

    print("\nSOURCE ASSESSMENTS:")
    for assessment in result.source_assessments:
        outdated = " OUTDATED" if assessment.is_outdated else ""
        print(
            f"  [{assessment.source_index}] {assessment.domain}: "
            f"{assessment.stance.value}, {assessment.reliability.value} reliability{outdated}"
        )
        print(f"      {assessment.note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
