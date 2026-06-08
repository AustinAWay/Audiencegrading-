# Audiencegrading — AI handoff / build prompt

You are taking over development of an existing web app called **Audiencegrading**.
This document is the full spec and the current state. Read it, then continue from
where it's at (or recreate it faithfully if starting fresh).

---

## 1. Where the codebase is

- **Local path:** `/Users/austinway/Desktop/AudinceRating` (note: the folder name
  is misspelled "AudinceRating" — that's expected; don't rename it).
- **GitHub:** `https://github.com/AustinAWay/Audiencegrading-` (branch `main`).
- **User-facing product name:** "Audiencegrading". **Internal Python package name
  stays `nichefit/`** (deliberate — do NOT rename the package; only UI/titles say
  Audiencegrading).
- Status: a working **demo / proof-of-concept**. It runs end-to-end and is on
  GitHub. Scores are illustrative, not production-validated.

## 2. What it does

Grades how well an X (Twitter) account's **audience** fits a chosen **niche**:
scrape the account's followers → filter bots for free → research + score the real
ones individually with Claude → aggregate into a 0–100 audience score with tiers,
a ranked roster, and a summary. Also a **single-person** mode that grades one
person's influence/fit for an area.

## 3. Tech stack (keep this; it's intentional)

- **Backend:** Python 3.9+, **FastAPI** (async), **SQLite** cache, `httpx`,
  `anthropic` SDK. Pinned in `pyproject.toml` + `requirements.txt`.
- **Frontend:** ONE file — `nichefit/web/index.html` — React + Tailwind + Babel
  via **CDN** (no Node, no build step), font **Outfit**. Served by FastAPI.
  (This machine has no Node; do not introduce a build step.)
- **Data layer:** Apify actors. **Scoring brain:** Claude **`claude-haiku-4-5`**
  with the server-side `web_search` tool (`web_search_20250305`).
- All keys are **server-side only**, read from env vars; never sent to the browser.

## 4. Keys & modes

Env vars (via `.env` at repo root, gitignored):
- `APIFY_API_TOKEN`, `ANTHROPIC_API_KEY`.
- Missing a key → that layer runs in **mock mode** automatically.
- `NICHEFIT_FORCE_MOCK=1` forces full mock (used by tests; fully offline/free).
- The app's own `.env` is loaded with `override=True` (an empty shell env var must
  not shadow it).

## 5. Project structure

```
nichefit/
  config.py        # settings + the RUBRIC (the tunable core) + MODE_PRESETS
  app.py           # FastAPI routes; serves the UI; resolves modes/scan-all
  __main__.py      # `python -m nichefit`
  data/
    apify.py       # follower scraper, tweet scraper, handle parsing,
                   #   fetch_profile_and_tweets(), fetch_follower_count() (cached)
    cache.py       # SQLite caches: followers, scores, analyses
    mock.py        # bundled sample followers for mock mode
  scoring/
    prompts.py     # system prompt, embedded rubric, XML rendering, few-shot
    scorer.py      # Scorer: concurrent Haiku calls, retry/backoff, JSON validate,
                   #   is_junk()/junk_score() bot filter, research_person()
    engine.py      # orchestration: scrape→bot-filter→sample→research→grade→
                   #   aggregate; run_analysis(), analyze_person(), resolve_pool()
    cost.py        # pre-run cost estimate
  web/index.html   # the entire UI
docs/              # architecture.md, scoring.md, configuration.md
tests/             # offline pytest suite (forces mock mode)
pyproject.toml, requirements.txt, .env.example, .gitignore, README.md
```

## 6. The scoring rubric (lives in `config.py` `RUBRIC` — single source of truth)

Each follower scored 0–100 across 5 weighted criteria; the rubric text is rendered
verbatim into the Haiku prompt:

| key | label | max |
|-----|-------|-----|
| `niche_relevance` | Niche Relevance | 30 |
| `influence_reach` | Real-World Influence | 35 |
| `authority` | Authority / Expertise | 20 |
| `engagement_quality` | Activity | 8 |
| `authenticity` | Authenticity / Activity | 7 |

Tiers: A 80–100, B 60–79, C 40–59, D 0–39. **Critical philosophy:** influence =
*who the person actually is* (founder/exec/investor/public figure), judged from
**web research**, **NOT follower count**. Follower count is excluded from grading
(not even shown to the model); it's only used for the "Top followers" *selection*
and bot detection. Keys are kept stable so stored scores/UI keep working — change
meaning/weights/bands, not keys.

Prompt design (`prompts.py` / `scorer.py`): system role sets the evaluator for the
niche; rubric embedded verbatim; follower data in labelled XML; 2 few-shot
examples; brief reasoning then **strict JSON**; low temperature; JSON is
validated + clamped + total/tier recomputed server-side; one stricter retry on
malformed output; a follower is skipped after N failures (never kills the run).

## 7. Run modes (the `mode` field; presets in `config.py` MODE_PRESETS)

- **Full account** (`full`): scan all followers, free bot filter, score a *random*
  sample (default 120) **without** web research; headline score is **bot-adjusted**
  (`real_avg × (1 − bot_rate)`). Cheap.
- **Top followers** (`top`): scan all, rank real ones by their own follower count,
  research + grade the **top 100**.
- **Custom** (`custom`): the form's own settings (sample, scan depth, research,
  skip-bots, selection).

**Scan-all:** by default `pool_size = 0` → `engine.resolve_pool()` auto-detects the
account's follower count (via `fetch_follower_count`, cached) and scrapes all of
them, capped at `HARD_CAP_SAMPLE_SIZE` (50,000). This is what makes "Top by reach"
see the whole audience. Advanced lets the user override scan depth.

## 8. Data-source facts (important gotchas)

- **Follower scraper** `kaitoeasyapi/premium-x-follower-scraper-following-data`:
  returns full user objects (bio=`description`, `followers_count`, `statuses_count`,
  `verified`, etc.) but **NO tweet text**; returns followers **newest-first** (recent
  followers are ~85% bots/empty); requires `maxFollowers` AND `maxFollowings` ≥ 200.
- **Tweet scraper** `kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest`:
  input `{from: handle, maxItems, queryType:"Latest"}`; each tweet has an `author`
  object with the full profile. Used for **single-person** grading and for
  **follower-count detection** (scan-all).
- Costs (approx): Apify ~**$0.13/1k followers**, ~**$0.25/1k tweets**; Anthropic
  ~**$0.02 per researched follower** (web search inflates input tokens).
- Single-person mode (`analyze_person`): fetch real profile + recent tweets, then
  research + grade. If no public tweets/profile → returns `status:"not_found"`
  (never fabricate a grade). Do NOT grade a person from the bare handle.

## 9. API endpoints

`GET /api/config` · `POST /api/estimate` · `POST /api/analyze` (returns `{job_id}`)
· `GET /api/progress/{job_id}` (UI polls ~0.9s) · `POST /api/person` · `GET /api/analyses` · `GET /` (UI).

## 10. How to run

```bash
cd /Users/austinway/Desktop/AudinceRating
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # or: pip install -e ".[dev]"
cp .env.example .env   # add the two keys (or leave blank for mock mode)
.venv/bin/python -m uvicorn nichefit.app:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000
```

## 11. Quality bar / conventions

- **Lint:** `ruff check .` must pass (config in `pyproject.toml`, line length 100;
  literal-heavy files have per-file E501 ignores).
- **Tests:** `pytest` — 35 tests, **fully offline** (force mock; never hit live
  APIs in tests). Add coverage for new logic.
- **UI:** no emojis. Palette — cream `#F4F1E8`, ink `#15140F`, purple `#6A4CF0`,
  lime `#C2F23D`, teal `#0E7A62`; font Outfit; bold/clean/decluttered.
- Keep all tunables in `config.py`. Keys server-side only.
- Error handling everywhere: surface a clear message + retry, never a fake result.

## 12. Current state — done & verified

UI redesign; Audiencegrading rename (UI only); scan-all by default; free bot
filter; Full/Top/Custom modes; bot-adjusted full-account score; per-follower web
research; single-person mode with real profile+tweets; full sortable/searchable
roster + "Analyze next 100 by reach" pagination; cost estimate/confirm + live
spend; caching + force refresh; robust error states; grading-process explainer;
demo disclaimers. `ruff` clean, 35/35 tests pass.

## 13. Known limitations / open work

- **Scores are uncalibrated** (no ground-truth validation) — the highest-value
  next step is a small labeled set to tune rubric weights/bands.
- Mega accounts cap scan at 50k (Apify cost). Sampling is still constrained by the
  data source.
- **README/docs still say "NicheFit"** (UI says Audiencegrading) — not yet synced.
- **No CI** — the GitHub token lacked `workflow` scope, so `.github/workflows`
  isn't committed; add a ruff+pytest workflow when possible.
- Audience "Top" mode "looks at tweets" via web research, not a real timeline pull
  (only single-person uses actual tweets). Could fetch tweets for the top N.
- **Security:** the API keys were originally pasted into a chat — rotate them.
