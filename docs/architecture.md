# Architecture

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
   - **Scrape** followers (cache first; otherwise Apify), trim to `sample_size`.
   - **Score** each uncached follower concurrently via `Scorer.score_one`,
     bounded by an `asyncio.Semaphore`. Cached scores are reused.
   - **Aggregate** into the audience score, influence-weighted score, criterion
     averages, tier distribution, and top-25 list.
   - **Summarize** with a final Haiku call.
   - Persist the result as a saved analysis.
4. **`GET /api/progress/{job_id}`** — the UI polls this (~1 s) for live phase,
   counts, spend, logs, and the final result.

## Caching

Every paid call is cache-checked first:

- **Followers** are cached per `handle`; a run reuses them if the cache already
  holds at least `sample_size` rows (no Apify spend).
- **Scores** are cached per `(handle, niche, screen_name)`; only uncached
  followers are sent to Haiku.
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
