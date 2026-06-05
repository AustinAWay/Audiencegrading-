# NicheFit

**Score how good an X (Twitter) account's audience is for a chosen niche** — by
analyzing and rating *each follower individually* with Claude Haiku, then
averaging into a single **0–100 audience score**.

- **Data layer:** Apify actor `kaitoeasyapi/premium-x-follower-scraper-following-data`
- **Scoring brain:** Claude Haiku (`claude-haiku-4-5`) — one sub-agent call per follower
- **Backend:** Python + FastAPI (async)
- **Frontend:** React + Tailwind, served as a single page by the backend (no build step)
- **Storage:** SQLite (follower cache, score cache, saved analyses)

You give it a handle and a niche; it returns a big audience score, a
per-criterion breakdown, an A/B/C/D tier distribution, the 25 highest-value
followers (with the model's reasoning), and a short written summary.

---

## Quickstart

Requires **Python 3.9+**. No Node.js needed.

```bash
# 1. install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # or: pip install -e ".[dev]"

# 2. add your keys (or skip to run in mock mode)
cp .env.example .env                      # then fill in APIFY_API_TOKEN + ANTHROPIC_API_KEY

# 3. run
python -m nichefit                        # or, if installed: nichefit
```

Open **http://127.0.0.1:8000** — the API **and** the UI are served from the same
port.

> **Mock mode:** leave a key blank (or set `NICHEFIT_FORCE_MOCK=1`) and that
> layer runs offline — bundled sample followers and/or heuristic scoring — so you
> can click through the whole flow with zero spend. A startup log and a UI banner
> tell you what's mocked.

---

## How a run works

1. Paste an X link or `@handle`, pick a niche (or type a custom one).
2. The app shows an **estimated cost + follower/score counts + a confirm step**.
3. On confirm it scrapes followers, scores each concurrently, and shows:
   a **0–100 gauge** (plus an influence-weighted score), a **criterion
   breakdown**, a **tier donut**, the **top-25 followers** with per-criterion
   scores + reasoning, and a **summary**.

Results are cached in SQLite keyed by `handle` (followers) and `handle + niche`
(scores), so re-runs are instant and free. A **Force refresh** toggle ignores the
cache.

---

## The rubric (the tunable core)

Each follower is scored 0–100 across five weighted criteria:

| # | Criterion | Max |
|---|-----------|-----|
| 1 | Niche Relevance | 35 |
| 2 | Influence & Reach | 25 |
| 3 | Authority / Expertise | 20 |
| 4 | Engagement Quality | 10 |
| 5 | Account Authenticity / Activity | 10 |

Tiers: **A** 80–100 · **B** 60–79 · **C** 40–59 · **D** 0–39.

**All weights, point bands, and tiers live in one place:**
[`nichefit/config.py`](nichefit/config.py) (the `RUBRIC` object). The rubric text
is rendered straight into the Haiku prompt, so editing it there is all you need
to retune scoring. See [`docs/scoring.md`](docs/scoring.md) for the prompt design
and the strict-JSON output contract.

---

## Cost & safety

- Pre-run **cost estimate** (Apify + Haiku + optional web lookups) with confirm.
- **Caching everywhere**; force refresh to override.
- **Concurrency limit + backoff**; one bad follower never kills the run.
- Live **"spent this run"** counter.
- **Mock mode** so you can see everything before spending.
- All keys are **server-side only** — never sent to the browser.

> Real runs consume **Apify credits** (~$0.10–0.15 / 1,000 followers) and
> **Anthropic tokens** (~$0.002–0.003 / follower). The estimate screen shows both
> before you confirm. For a first run, keep the sample at ~200.

---

## Project layout

```
nichefit/
├── config.py            # rubric + all tunables (edit scoring here)
├── app.py               # FastAPI app: routes + serves the UI
├── __main__.py          # `python -m nichefit` entry point
├── data/
│   ├── apify.py         # Apify actor run/poll/fetch + handle parsing
│   ├── cache.py         # SQLite caches (followers · scores · analyses)
│   └── mock.py          # bundled sample followers for mock mode
├── scoring/
│   ├── prompts.py       # system prompt, embedded rubric, few-shot examples
│   ├── scorer.py        # Haiku sub-agents: concurrency, retry, validation
│   ├── engine.py        # orchestration: scrape → score → aggregate → summarize
│   └── cost.py          # pre-run cost estimate
└── web/index.html       # the single-page React + Tailwind UI
docs/                    # architecture / scoring / configuration deep-dives
tests/                   # offline test suite (mock mode, no credits)
```

---

## Development

```bash
pip install -e ".[dev]"
ruff check .             # lint
pytest                   # tests — forced into mock mode, fully offline
```

The test suite never hits Apify or Anthropic (it sets `NICHEFIT_FORCE_MOCK=1`).

## Docs

- [docs/architecture.md](docs/architecture.md) — components, data flow, caching, concurrency
- [docs/scoring.md](docs/scoring.md) — the rubric, prompt design, output contract
- [docs/configuration.md](docs/configuration.md) — every environment variable and tunable

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/config` | niches, defaults, rubric, mock flags |
| POST | `/api/estimate` | pre-run cost estimate + resolved handle |
| POST | `/api/analyze` | start a run, returns `{job_id}` |
| GET | `/api/progress/{job_id}` | live progress / final result |
| GET | `/api/analyses` | recent saved analyses |
| GET | `/api/analyses/{id}` | a single saved analysis |

## Notes

The UI is React via CDN + Tailwind served directly by FastAPI (no Node.js / build
step) — one process, one command. The component source lives in
[`nichefit/web/index.html`](nichefit/web/index.html).
