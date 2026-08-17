"""Manually inspect the claim analysis agent against the real Gemini API.

    cd backend
    ./.venv/Scripts/python.exe scripts/analyze_claim.py "আজ ঢাকায় ভূমিকম্প হয়েছে"
    ./.venv/Scripts/python.exe scripts/analyze_claim.py            # runs sample claims

Forces UTF-8 output so Bangla prints on a cp1252 Windows console.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.services.gemini import GeminiService  # noqa: E402
from app.utils.errors import ShottiError  # noqa: E402

SAMPLE_CLAIMS = [
    "গতকাল ঢাকায় ভূমিকম্প হয়েছে।",
    "Bangladesh won the ICC Champions Trophy in 2017.",
    "Drinking hot water cures COVID-19.",
    "Biryani is the most delicious food in the world.",
]


async def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = get_settings()
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set. Add it to the repo-root .env file.")
        return 1

    claims = sys.argv[1:] or SAMPLE_CLAIMS
    service = GeminiService(settings)
    exit_code = 0

    try:
        for claim in claims:
            print("=" * 70)
            print(f"CLAIM: {claim}")
            try:
                analysis = await service.analyze_claim(claim)
            except ShottiError as exc:
                print(f"  FAILED [{exc.error_code}] {exc.message}")
                exit_code = 1
                continue

            print(f"  normalized  : {analysis.normalized_claim}")
            print(f"  language    : {analysis.language.value}")
            print(f"  topic       : {analysis.topic.value}")
            print(f"  checkable   : {analysis.is_checkable}")
            if analysis.uncheckable_reason:
                print(f"  why not     : {analysis.uncheckable_reason}")
            print(f"  proposition : {analysis.factual_proposition}")
            print(f"  entities    : {', '.join(analysis.entities) or '-'}")
            print(f"  time refs   : {', '.join(analysis.temporal_references) or '-'}")
            print(f"  timeframe   : {analysis.resolved_timeframe or '-'}")
            print("  questions   :")
            for question in analysis.verification_questions:
                print(f"    - {question}")
            print("  queries     :")
            for query in analysis.search_queries:
                print(f"    - {query}")
    finally:
        await service.aclose()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
