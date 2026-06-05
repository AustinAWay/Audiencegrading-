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

Two knobs keep cost flat regardless of account size: a cheap **pool** that gets
bot-filtered for free, and a capped **sample** of real accounts that get the
expensive deep analysis.

| Variable | Default | Meaning |
|----------|---------|---------|
| `DEFAULT_POOL_SIZE` | `1000` | Followers scraped + bot-filtered per run (cheap). |
| `DEFAULT_SAMPLE_SIZE` | `150` | Max **real** followers deeply analyzed (research + Haiku). |
| `HARD_CAP_SAMPLE_SIZE` | `50000` | Ceiling enforced by the API. |
| `DEFAULT_CONCURRENCY` | `8` | Parallel Haiku calls (async semaphore). |

`MAX_RETRIES_PER_FOLLOWER` (3) and `APIFY_MIN_FOLLOWERS` (200, the actor's
enforced minimum) are constants in `config.py`.

## Bot / junk filter (default ON)

Flags obvious bots/empty/spam accounts from raw data alone — no LLM, no research
— and counts them as fake (tier D), so you never pay to "analyze" junk. Verified
accounts are never flagged, and the filter is conservative (empty bio **and**
near-zero activity, or a spam signature).

| Variable | Default | Meaning |
|----------|---------|---------|
| `BOT_FILTER_ENABLED_DEFAULT` | `True` | Flag + free-score bots by default. |
| `BOT_MIN_STATUSES` | `3` | Empty bio + fewer tweets than this → junk. |
| `BOT_SPAM_PHRASES` | list | Bio/name/tweet phrases that mark spam. |
| `EST_ANALYZABLE_FRACTION` | `0.5` | Estimate-only: assumed non-bot share of the pool. |

## Run modes

One-click presets (the UI buttons), defined in `MODE_PRESETS` in `config.py`.
`custom` uses the form's own settings.

| Mode | sample | pool | research | selection |
|------|--------|------|----------|-----------|
| `full` | `FULL_MODE_SAMPLE` (120) | `FULL_MODE_POOL` (1500) | off (cheap) | random |
| `top` | `TOP_MODE_SAMPLE` (100) | `TOP_MODE_POOL` (2000) | on | top by reach |

`full` projects the bot rate + tier mix across the whole account; `top` analyzes
the followers with the most followers of their own.

## Cost model

Used for the pre-run estimate and the live spend counter.

| Variable | Default | Meaning |
|----------|---------|---------|
| `APIFY_COST_PER_1000_FOLLOWERS` | `0.13` | Apify price assumption (USD). |
| `HAIKU_INPUT_PRICE_PER_MTOK` | `1.0` | Haiku input price (USD / million tokens). |
| `HAIKU_OUTPUT_PRICE_PER_MTOK` | `5.0` | Haiku output price (USD / million tokens). |

`EST_INPUT_TOKENS_PER_FOLLOWER` (1800) and `EST_OUTPUT_TOKENS_PER_FOLLOWER`
(130) estimate one scoring call's token footprint.

## Web research (default ON)

Researches every follower being scored so the model can judge real-world
influence from who they are (see [scoring.md](scoring.md)). Adds a web search +
tokens per follower; toggle off per-run with the "Research each follower"
checkbox.

| Constant | Default | Meaning |
|----------|---------|---------|
| `WEB_LOOKUP_ENABLED_DEFAULT` | `True` | Research each follower by default. |
| `WEB_LOOKUP_EST_TOKENS` | `2500` | Estimated extra tokens per researched follower. |
| `WEB_SEARCH_COST_PER_CALL` | `0.01` | Web-search price assumption (USD/search). |

## The rubric

Weights, point bands, and tier thresholds are **not** environment variables —
they're the `RUBRIC` object in `config.py`. See [scoring.md](scoring.md).
