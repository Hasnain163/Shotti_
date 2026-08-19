# Shotti? AI

**Bangla/English misinformation verification.** Paste a claim or drop a screenshot, and Shotti? AI searches the web, reads the most credible pages it finds, weighs what they actually say, and returns a verdict with the sources attached.

*Shotti?* (সত্যি?) is Bangla for *"really?"* — the whole product in one word.

---

## What it does

You give it a claim. It gives you one of four verdicts, a confidence score, a short explanation in the language you asked in, the quotes it relied on, and every source it read.

| Verdict | Meaning |
| --- | --- |
| `LIKELY_TRUE` | Credible sources support the claim. |
| `LIKELY_FALSE` | Credible sources contradict the claim. |
| `MISLEADING` | Technically defensible, but framed to mislead — missing context, wrong timeframe, stripped qualifier. |
| `UNVERIFIED` | The evidence was not good enough to say. Reported honestly, with the reason. |

`UNVERIFIED` is a first-class outcome, not a failure mode. A confident answer to a question the evidence cannot settle is worse than no answer.

### Two design rules

Everything in the pipeline follows from these:

1. **No stage may invent evidence.** Sources come from the search API. The model that weighs evidence never sees a URL it could hallucinate — it refers to sources by index only. Every quote is checked character-by-character against the page text actually retrieved, and quotes that cannot be found are discarded. The number discarded is reported with each result.
2. **Insufficient evidence is reported, never dressed up.** Degraded runs are flagged as degraded. Cached results are flagged as cached. The reported timing is always truthful about which run it came from.

---

## How it works

```
claim (text or screenshot)
  │
  ├─ [screenshots only] Gemini vision  ─── read text, find the central claim, note visible date/source
  │
  ├─ Gemini claim analysis  ──────────── restate as an atomic, checkable proposition
  │                                      generate search queries in Bangla and English
  │
  ├─ Firecrawl research  ─────────────── search all queries concurrently
  │                                      de-duplicate URLs, rank by publisher reputation,
  │                                      cap per domain for viewpoint diversity,
  │                                      scrape the top N, clean and length-cap the text
  │
  ├─ Gemini evidence analysis  ───────── per-source stance, reliability, outdatedness
  │                                      → verdict + confidence + explanation
  │
  ├─ verdict validation  ─────────────── quote grounding, verdict/evidence coherence
  │
  └─ VerifyResponse
```

Every research stage **degrades rather than aborts**: a failed query or an unreachable page is recorded and the rest of the research continues. A whole-pipeline timeout (90s default) means a slow upstream can never hang the request forever.

A verification takes roughly **25–40 seconds**, because it genuinely searches and reads pages. The frontend shows the real stage sequence rather than a fake percentage bar.

### Source ranking

[`backend/app/services/domains.py`](backend/app/services/domains.py) holds a small hand-maintained table of publishers — Bangladeshi fact-checkers (Rumor Scanner, Jachai, FactWatch BD), international fact-checkers, government and academic domains, quality news, and user-generated content. It scores which pages are worth spending a scrape on first, and labels publisher type so the analysis stage can weigh a government statistic differently from a forum post.

A high score never means a source is correct. It only decides reading order.

---

## Stack

**Backend** — Python 3.13, FastAPI, Pydantic v2 with `pydantic-settings`, `google-genai` (Gemini), `firecrawl-py`, pytest.

**Frontend** — React 18, TypeScript, Vite 6, Tailwind CSS 3. No component library, no state management library, no data-fetching library.

**Storage** — none. There is no database. Completed verifications live in a bounded in-memory TTL cache ([`services/cache.py`](backend/app/services/cache.py)) that expires on a timer and is gone on restart. Nothing a user submits is persisted anywhere.

---

## Getting started

### Prerequisites

- Python 3.13+
- Node.js 20+
- A [Gemini API key](https://aistudio.google.com/apikey) and a [Firecrawl API key](https://firecrawl.dev) — both have usable free tiers.

### 1. Configure

```bash
cp .env.example .env
```

Fill in `GEMINI_API_KEY` and `FIRECRAWL_API_KEY`. Everything else has a sensible default. `.env` is gitignored — never commit real keys.

> **Note on the Gemini model:** the default is `gemini-3.7-flash`. The `gemini-2.5-*` models are closed to new API keys, so do not "downgrade" this.

### 2. Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/pip install -r requirements.txt      # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS / Linux
```

### 3. Frontend

```bash
cd frontend
npm install
```

### 4. Run

**Development** — two processes, hot reload on both:

```bash
# terminal 1
cd backend && ./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# terminal 2
cd frontend && npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to port 8000, so the API stays same-origin — no CORS to configure and no API base URL to set while working locally.

**Production-style** — one process, one URL:

```bash
cd frontend && npm run build
cd ../backend && ./.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000**. When `frontend/dist` exists, FastAPI mounts it at `/` and serves the whole app itself. The mount happens after the API routers, so `/api` is never shadowed. If `dist` is absent, `/` returns a small JSON pointer instead of 404ing.

---

## API

Interactive docs at **`/docs`** while the server runs.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness, plus which integrations have credentials (booleans only, never keys). |
| `POST` | `/api/verify` | Verify a typed claim. |
| `POST` | `/api/screenshot/extract` | Read a screenshot and return the claim it contains. One Gemini call, no research, no verdict. |
| `POST` | `/api/verify/screenshot` | Read a screenshot, then verify it in one request. |

The extract endpoint exists on purpose: reading an image is one cheap call, verifying is two calls plus web research. Letting the user correct a misread claim before that spend is both kinder and cheaper than confidently verifying the wrong sentence.

### Verify a claim

```bash
curl -X POST http://localhost:8000/api/verify \
  -H 'Content-Type: application/json' \
  -d '{"claim": "Bangladesh won the ICC Champions Trophy in 2017.", "language": "auto"}'
```

`claim` is 3–1000 characters. `language` is `auto` (default), `bn`, or `en`.

```jsonc
{
  "claim": "Bangladesh won the ICC Champions Trophy in 2017.",
  "normalized_claim": "Bangladesh won the 2017 ICC Champions Trophy.",
  "verdict": "LIKELY_FALSE",
  "confidence_score": 0.94,
  "explanation": "Pakistan won the 2017 ICC Champions Trophy...",
  "supporting_evidence": [],
  "contradicting_evidence": [{ "quote": "...", "source_index": 0 }],
  "important_context": ["Bangladesh reached the semi-finals..."],
  "sources": [{ "title": "...", "url": "...", "domain": "...", "source_type": "news", "published_date": "..." }],
  "source_assessments": [{ "source_index": 0, "stance": "contradicts", "reliability": "high", "is_outdated": false, "note": "..." }],
  "claim_id": "a1b2c3d4e5f6a7b8",
  "language": "en",
  "meta": {
    "duration_ms": 28410,
    "sources_found": 14, "sources_used": 6, "queries_used": 3,
    "dropped_evidence_count": 0,
    "has_conflicting_evidence": false, "relies_on_speculation": false,
    "degraded": false, "cached": false
  }
}
```

Evidence references sources **by index**, never by URL — that is the mechanism that makes hallucinated citations structurally impossible.

### Screenshots

```bash
curl -X POST http://localhost:8000/api/verify/screenshot -F 'image=@screenshot.png'
```

PNG, JPEG, WebP, or GIF, up to 5 MB. The MIME type is sniffed from the file's magic bytes and cross-checked against what the client declared, and uploads are read in chunks that stop one byte over the limit — an oversized file is never buffered whole just to be rejected.

### Errors

Every failure — including validation errors, 404s, and unhandled exceptions — returns the same envelope. Stack traces are never exposed.

```json
{ "error": "rate_limited", "message": "Human-readable, safe to display.", "details": {} }
```

| Code | Status |
| --- | --- |
| `validation_error` / `invalid_claim` | 422 |
| `payload_too_large` | 413 |
| `unsupported_media_type` | 415 |
| `rate_limited` | 429 |
| `service_error` | 502 |
| `service_unavailable` | 503 |
| `internal_error` | 500 |

---

## Tests

```bash
cd backend && ./.venv/Scripts/python -m pytest
```

193 tests, fully mocked, no network, no API credits — around 45 seconds.

Live tests that hit the real APIs are marked and deselected by default:

```bash
./.venv/Scripts/python -m pytest -m live      # requires credentials and network
```

Frontend typechecking:

```bash
cd frontend && npm run typecheck
```

### Manual inspection scripts

For poking at one stage at a time against the real APIs:

```bash
cd backend
./.venv/Scripts/python scripts/analyze_claim.py "your claim"    # claim analysis only
./.venv/Scripts/python scripts/research_claim.py "your claim"   # search + scrape only
./.venv/Scripts/python scripts/verify_claim.py "your claim"     # all three agents
```

---

## Configuration

All of these are optional environment variables with defaults in [`backend/app/config.py`](backend/app/config.py). The ones worth knowing:

| Variable | Default | What it controls |
| --- | --- | --- |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Analysis model. |
| `GEMINI_TIMEOUT_MS` | `30000` | Per-call timeout. |
| `FIRECRAWL_MAX_SOURCES` | `6` | Pages scraped per claim. **The main cost and latency dial.** |
| `FIRECRAWL_SEARCH_LIMIT` | `5` | Results per query before de-duplication. |
| `FIRECRAWL_MAX_PER_DOMAIN` | `2` | Viewpoint diversity cap — eight pages from one outlet is still one viewpoint. |
| `FIRECRAWL_MAX_TOTAL_CHARS` | `15000` | Bounds the whole analysis prompt. |
| `PIPELINE_TIMEOUT_SECONDS` | `90` | Whole-request ceiling. |
| `CACHE_TTL_SECONDS` | `900` | Repeat-verification cache. Set to `0` to disable. |
| `SCREENSHOT_MAX_BYTES` | `5242880` | Upload limit (5 MB). |
| `CORS_ORIGINS` | `localhost:5173`, `127.0.0.1:5173` | Comma-separated allowed frontend origins. |
| `LOG_LEVEL` | `INFO` | Standard Python levels. |

Free tiers are tight — Firecrawl allows roughly 10 requests/minute, and one claim fires several searches plus up to `max_sources` scrapes. Concurrency is capped at 3 so an unthrottled burst does not rate-limit itself. Lower `FIRECRAWL_MAX_SOURCES` to cut both latency and credit use.

---

## Deploying

The app is one Python process serving both the API and the built UI, which makes it deployable anywhere that runs a container or a Python web service.

1. `npm run build` in `frontend/` — FastAPI serves `frontend/dist` automatically when it is present.
2. Set the environment variables from `.env.example` in your host's config. **Never bake keys into the image.**
3. Set `CORS_ORIGINS` to your real frontend origin if the UI is served from a different host than the API. If you serve both from the same process, CORS does not come into play at all.
4. Start with `uvicorn app.main:app --host 0.0.0.0 --port $PORT` from the `backend/` directory.
5. Point your platform's health probe at `/api/health`.

Note that the cache is per-process and in memory: with multiple workers or replicas, each has its own, and all of them clear on restart. That is the intended trade — it keeps the promise that nothing users submit is stored.

---

## Project layout

```
backend/
  app/
    main.py            FastAPI app, error handlers, static UI mount
    config.py          env-backed settings, one place for every default
    dependencies.py    service singletons and lifespan cleanup
    routers/           health, verify, screenshot — HTTP concerns only
    services/
      pipeline.py      stage order and degradation decisions
      gemini.py        claim analysis, evidence analysis, image reading
      firecrawl.py     search, rank, scrape, normalise
      domains.py       publisher classification and credibility ranking
      cache.py         bounded in-memory TTL cache
    models/            Pydantic request/response schemas
    prompts/           prompt text, kept out of the service code
    utils/             errors, image validation, text cleaning
  scripts/             manual single-stage inspection tools
  tests/               mocked suite + live suite (deselected by default)

frontend/
  src/
    App.tsx            view state and submission handling
    api/client.ts      the only module that talks to the backend
    hooks/useVerify.ts request lifecycle and stage progression
    components/        landing, composer, dropzone, progress, result, about
    lib/               verdict presentation, formatting
    types/             hand-written mirrors of the backend models
```

Routers hold no business logic. The pipeline owns stage order and nothing else — each service handles its own errors, and the pipeline only decides whether a failure should end the request or continue with less.

---

## Limits

Stated plainly, and also shown to users in the app:

- It only reads public web pages. Private posts, closed groups, and messages are out of reach.
- It cannot detect an edited screenshot. A name or date inside an image is only what the image claims.
- It cannot verify claims that live in video or audio — only text it can read.
- Local Bangladeshi topics sometimes have thin online coverage, which produces `UNVERIFIED` rather than an answer.
- The AI can misread evidence. The sources are listed so you can check the reasoning yourself.
- A verification takes 25–40 seconds, because it really does search and read pages.

Shotti? AI is a research aid, not an arbiter of truth. The sources are the point — read them.
