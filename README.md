# NicheFit

> 🧪 **Demo / proof-of-concept.** This project demonstrates *what's possible*, not
> a finished product. The scoring rubric, prompts, bot filter, and especially the
> follower sampling (constrained by the data source, which returns followers
> newest-first) are reasonable starting points that would **need real fine-tuning
> and validation** before the scores could be trusted. Treat all output as
> directional, not authoritative.

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
2. The app shows an **estimated cost + a confirm step**.
3. On confirm it:
   - **scrapes a cheap pool** of followers (default ~1,000),
   - **bot-filters the whole pool for free** (no LLM) and counts bots as fake,
   - **deeply analyzes a random sample of the real accounts** (default 150) with
     web research + Haiku,
   - shows a **0–100 real-audience gauge**, the **bot rate**, a **criterion
     breakdown**, a **tier donut**, the **top-25 followers** with reasoning, and a
     **summary**.

Because only a capped sample is deeply analyzed, **cost stays flat regardless of
account size** — analyzing a 100k-follower account costs about the same as a 5k
one. Results are cached in SQLite (`handle` for followers, `handle + niche` for
scores), so re-runs are instant and free; **Force refresh** ignores the cache.

### Run modes (one-click)

| Button | What it does | Cost |
|--------|--------------|------|
| **Estimate cost →** | Uses the form's own settings (full control). | depends |
| **⚡ Full account (cheap estimate)** | Scrapes a big pool, bot-filters free, scores a random sample of real followers **without web research**, and **projects the bot rate + tier mix across the whole account**. | ~$0.50 |
| **★ Top 100 by reach (deep)** | Deeply analyzes the 100 followers with the most followers of their own, **with web research** — your highest-reach audience. | ~$1.80 |

The results dashboard shows the real-sample tier donut **and** a "projected
across the full account" breakdown (bots + tiers as % of everyone).

---

## The rubric (the tunable core)

Each follower is scored 0–100 across five weighted criteria:

| # | Criterion | Max |
|---|-----------|-----|
| 1 | Niche Relevance | 30 |
| 2 | Real-World Influence | 35 |
| 3 | Authority / Expertise | 20 |
| 4 | Content Quality | 8 |
| 5 | Authenticity / Activity | 7 |

Tiers: **A** 80–100 · **B** 60–79 · **C** 40–59 · **D** 0–39.

Value is driven by **real-world influence — who the person actually is** (founder,
executive, investor, billionaire, public figure), judged from **web research, not
follower count**. A major real-world figure is a valuable audience member even
when they're off-topic for the niche.

**All weights, point bands, and tiers live in one place:**
[`nichefit/config.py`](nichefit/config.py) (the `RUBRIC` object). The rubric text
is rendered straight into the Haiku prompt, so editing it there is all you need
to retune scoring. See [`docs/scoring.md`](docs/scoring.md) for the prompt design
and the strict-JSON output contract.

---

## Cost & safety

- **Flat cost by account size** — a cheap pool scrape + free bot filter + a
  capped deep-analysis sample mean a 100k account costs about the same as a small
  one.
- **Free bot filter** — obvious bots/empty/spam accounts are flagged from raw
  data (no LLM/research) and counted as fake.
- Pre-run **cost estimate** (Apify pool + Haiku + web research) with confirm.
- **Caching everywhere**; force refresh to override.
- **Concurrency limit + backoff**; one bad follower never kills the run.
- Live **"spent this run"** counter, and **mock mode** to preview free.
- All keys are **server-side only** — never sent to the browser.

> Real runs consume **Apify credits** (~$0.10–0.15 / 1,000 pooled followers) and
> **Anthropic tokens + web searches** (~$0.02 / deeply-analyzed real follower).
> The estimate screen shows the total before you confirm. Example: a huge,
> bot-heavy account with a 200 pool + 8 real analyzed ≈ **$0.21**.

> **Sampling caveat:** the Apify actor returns followers newest-first, so the
> sample is drawn from the most recent slice of the audience, not uniformly
> across all followers.

---

## Limitations (this is a demo)

NicheFit is a working proof-of-concept, not a validated product. Known gaps that
would need fine-tuning before relying on scores:

- **Sampling is newest-first.** The data source returns recent followers first
  (mostly bots), so reaching real/high-value followers requires scanning deep
  enough to cover the whole account. There's no "by reach" ordering available.
- **No tweet text.** This follower actor doesn't return tweets, so "Activity" is
  inferred from post counts and Top-mode "looks at tweets" via web search rather
  than a real timeline pull (a dedicated tweet-scraper actor would improve this).
- **Scores are uncalibrated.** The rubric weights, point bands, and prompt are
  reasonable defaults but haven't been validated against ground truth. A "B" vs
  "A" boundary is a judgment call you'd tune to your own taste.
- **Influence research depends on web search** being enabled on the Anthropic
  account, and on the person being findable online.
- **Cost estimates are approximate** (the real bot rate and per-call token usage
  vary); the live spend counter and confirm step are the real safeguards.

---

## Data persistence — push your runs

Every audience run is saved to a local SQLite database, **`nichefit.db`**, which
holds the cached followers/scores, the past-runs history, and the **leaderboard +
bell-curve** data. Unlike most projects, this file **is committed to the repo on
purpose** so that data survives across machines and instances.

**After making runs, commit and push them** so the leaderboard / bell curve stays
consistent everywhere:

```bash
git add nichefit.db && git commit -m "data: new runs" && git push
```

Notes:
- The bell-curve percentile **adapts** as more accounts are graded — it starts
  from an assumed distribution and shifts toward the real mean/std of your data
  (the assumption is a prior worth `BELL_PRIOR_STRENGTH` accounts, in `config.py`).
- It's a **single-writer binary file**: don't have two instances writing and
  pushing at once, or git will conflict on it.
- If it grows large or you want a clean slate, use **History → Clear all data**
  (or `POST /api/clear`), then commit the emptied DB.

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
