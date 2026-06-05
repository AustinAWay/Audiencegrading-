"""
NicheFit — score how well an X (Twitter) account's audience fits a niche.

Each follower is rated 0–100 individually by a Claude Haiku sub-agent against an
editable five-criterion rubric, then averaged into a single audience score.

Package layout:
    config            settings + the scoring rubric (the tunable core)
    app               FastAPI application: API routes + serves the web UI
    data/             the data layer — Apify scraping, SQLite cache, mock data
    scoring/          the scoring engine — prompts, Haiku scorer, orchestration, cost
    web/              the single-page React + Tailwind UI
"""

__version__ = "1.0.0"
