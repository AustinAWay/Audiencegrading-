# Architecture

> 🧪 **Demo / proof-of-concept.** The design below works end-to-end but is meant
> to show what's possible; the scoring and sampling would need fine-tuning before
> production use.

NicheFit is a single FastAPI process that serves both the JSON API and the
single-page UI. There is no separate frontend server and no build step.

## Components

```
┌─────────────────────────────────────────────────────────────────┐
│  nichefit.app  (FastAPI)                                          │
│    /api/config /api/estimate /api/analyze /api/progress  + UI     │
└───────────────┬───────────────────────────────┬─────────────────┘
                │                                 │
        scoring/engine.py                   scoring/cost.py
        (orchestration)                     (pre-run estimate)
                │
   ┌────────────┼─────────────────────────────┐
   │            │                             │
 data/apify   scoring/scorer  ───────────►  scoring/prompts
 (scrape)     (Haiku sub-agents)            (rubric + few-shot)
   │            │
   └──── data/cache (SQLite: followers · scores · analyses) ────┘
```

| Module | Responsibility |
|--------|----------------|
| `config.py` | Settings + the scoring **rubric** (the tunable core). |
| `app.py` | FastAPI routes; serves `web/index.html`. All keys stay server-side. |
| `data/apify.py` | Run the Apify actor, poll, fetch the dataset, normalize + dedupe; parse handles. |
| `data/cache.py` | SQLite caches keyed by `handle` (followers) and `handle+niche` (scores), plus saved analyses. |
| `data/mock.py` | Bundled sample followers for mock mode. |
| `scoring/prompts.py` | System prompt, embedded rubric, XML rendering, two few-shot examples. |
| `scoring/scorer.py` | The `Scorer`: concurrent Haiku calls, retry/backoff, JSON validation, token accounting, summary, web lookup. |
| `scoring/engine.py` | Orchestration: scrape → score → aggregate → summarize; the in-memory job store. |
| `scoring/cost.py` | Pre-run cost estimate. |

## Request lifecycle of an analysis

1. **`POST /api/estimate`** — resolve the handle, check the cache, return an
   itemized cost estimate (Apify + Haiku + optional web lookups).
2. **`POST /api/analyze`** — create a job, kick off `run_analysis` as an
   `asyncio` background task, return a `job_id` immediately.
3. **`run_analysis`** (in `engine.py`):
   - **Scrape a pool** of followers (`pool_size`, cache first; otherwise Apify) —
     cheap, and decoupled from how many we deeply analyze.
   - **Bot-filter the whole pool for free** (`is_junk`): obvious bots/empty/spam
     accounts get a free tier-D "fake" score, no LLM or research.
   - **Deeply analyze a random sample of the real accounts** (capped at
     `sample_size`): per-follower web research → `Scorer.score_one`, bounded by an
     `asyncio.Semaphore`. Cached scores are reused first.
   - **Aggregate** the real sample into the audience score, criterion averages,
     tier distribution, and top-25 — plus the **bot rate** over the pool.
   - **Summarize** with a final Haiku call, and persist the saved analysis.
4. **`GET /api/progress/{job_id}`** — the UI polls this (~1 s) for live phase,
   counts, spend, logs, and the final result.

This keeps cost flat by account size: a 100k-follower account scrapes the same
pool and analyzes the same capped sample as a small one. The trade-off is that
the result is a **sample-based estimate** (and the Apify actor returns
followers newest-first, so the pool is the most recent slice, not a uniform draw).

## Caching

Every paid call is cache-checked first:

- **Followers** are cached per `handle`; a run reuses them if the cache already
  holds at least `pool_size` rows (no Apify spend).
- **Scores** are cached per `(handle, niche, screen_name)` — including free bot
  scores; only uncached real accounts in the sample are sent to research + Haiku.
- **Force refresh** clears both caches for that handle/niche before the run.

The result: re-running the same handle/niche is instant and free.

## Concurrency & resilience

- Scoring runs under `asyncio.Semaphore(concurrency)` (default 8).
- Each follower call retries up to `MAX_RETRIES_PER_FOLLOWER` with exponential
  backoff; a follower that still fails is **skipped**, never failing the run.
- The whole run is wrapped so any exception is captured into the job record —
  the server never crashes on a bad run.

## Mock mode

If a key is missing (or `NICHEFIT_FORCE_MOCK=1`), that layer runs offline:
Apify → bundled sample followers; Haiku → a deterministic heuristic scorer. The
entire UI and flow work with zero spend. See [configuration.md](configuration.md).
