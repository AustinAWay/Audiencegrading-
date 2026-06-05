# Configuration

All defaults live in [`nichefit/config.py`](../nichefit/config.py). The numeric
ones can be overridden with environment variables (typically via `.env`).

## Keys

| Variable | Purpose |
|----------|---------|
| `APIFY_API_TOKEN` | Apify token — the follower data layer. Blank → Apify mock mode. |
| `ANTHROPIC_API_KEY` | Anthropic key — the Haiku scoring brain. Blank → Haiku mock mode. |

Keys are read **server-side only** and are never sent to the browser. The app's
own `.env` takes precedence over shell environment variables (so an empty
exported var can't accidentally force mock mode).

## Mock mode

A layer runs offline when its key is missing, or for everything when
`NICHEFIT_FORCE_MOCK=1`:

- **Apify mock** → bundled sample followers (`data/mock.py`), no scrape spend.
- **Haiku mock** → a deterministic heuristic scorer, no token spend.

The console prints which layers are mocked at startup, and the UI shows a banner.
The test suite relies on `NICHEFIT_FORCE_MOCK=1` so it always runs free and
offline.

## Server

| Variable | Default | Meaning |
|----------|---------|---------|
| `HOST` | `127.0.0.1` | Bind address (`python -m nichefit`). |
| `PORT` | `8000` | Port. |
| `RELOAD` | off | `1`/`true` enables uvicorn auto-reload (dev). |
| `NICHEFIT_DB` | `<repo>/nichefit.db` | SQLite cache file path. |

## Model

| Variable | Default |
|----------|---------|
| `HAIKU_MODEL` | `claude-haiku-4-5` |
| `SCORER_TEMPERATURE` | `0.1` |

## Sampling & concurrency

| Variable | Default | Meaning |
|----------|---------|---------|
| `DEFAULT_SAMPLE_SIZE` | `2000` | Followers sampled/scored per run. |
| `HARD_CAP_SAMPLE_SIZE` | `50000` | Ceiling enforced by the API. |
| `DEFAULT_CONCURRENCY` | `8` | Parallel Haiku calls (async semaphore). |

`MAX_RETRIES_PER_FOLLOWER` (3) and `APIFY_MIN_FOLLOWERS` (200, the actor's
enforced minimum) are constants in `config.py`.

## Cost model

Used for the pre-run estimate and the live spend counter.

| Variable | Default | Meaning |
|----------|---------|---------|
| `APIFY_COST_PER_1000_FOLLOWERS` | `0.13` | Apify price assumption (USD). |
| `HAIKU_INPUT_PRICE_PER_MTOK` | `1.0` | Haiku input price (USD / million tokens). |
| `HAIKU_OUTPUT_PRICE_PER_MTOK` | `5.0` | Haiku output price (USD / million tokens). |

`EST_INPUT_TOKENS_PER_FOLLOWER` (1800) and `EST_OUTPUT_TOKENS_PER_FOLLOWER`
(130) estimate one scoring call's token footprint.

## Web lookup (optional, default OFF)

| Constant | Default | Meaning |
|----------|---------|---------|
| `WEB_LOOKUP_ENABLED_DEFAULT` | `False` | Off unless the request opts in. |
| `WEB_LOOKUP_TOP_PERCENTILE` | `0.05` | Only the top 5% by follower count are eligible. |
| `WEB_LOOKUP_MAX_PER_RUN` | `20` | Hard cap on lookups per run. |
| `WEB_LOOKUP_MIN_FOLLOWERS` | `25000` | Minimum follower count to qualify. |

## The rubric

Weights, point bands, and tier thresholds are **not** environment variables —
they're the `RUBRIC` object in `config.py`. See [scoring.md](scoring.md).
