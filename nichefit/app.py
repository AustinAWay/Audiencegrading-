"""
NicheFit API — the FastAPI application. All keys stay server-side.

Endpoints
---------
GET  /api/config             niches, defaults, rubric, mock-mode flags
POST /api/estimate           pre-run cost estimate + resolved handle
POST /api/analyze            start a background run, returns {job_id}
GET  /api/progress/{job_id}  live progress / final result
GET  /api/analyses           recent saved analyses
GET  /api/analyses/{id}      a single saved analysis
GET  /                       the single-page React + Tailwind UI
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .data import apify
from .data import cache as db
from .scoring import cost as cost_mod
from .scoring import engine

WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    if config.APIFY_MOCK:
        print("\033[93m[NicheFit] APIFY_API_TOKEN missing -> Apify MOCK mode "
              "(bundled sample followers, no scrape spend).\033[0m")
    if config.ANTHROPIC_MOCK:
        print("\033[93m[NicheFit] ANTHROPIC_API_KEY missing -> Haiku MOCK mode "
              "(heuristic scoring, no token spend).\033[0m")
    if not config.APIFY_MOCK and not config.ANTHROPIC_MOCK:
        print("\033[92m[NicheFit] Live mode: both keys present.\033[0m")
    yield


app = FastAPI(title="NicheFit", version="1.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #
class EstimateReq(BaseModel):
    handle: str
    niche: str
    sample_size: int = config.DEFAULT_SAMPLE_SIZE
    web_lookup: bool = config.WEB_LOOKUP_ENABLED_DEFAULT
    force_refresh: bool = False


class AnalyzeReq(EstimateReq):
    concurrency: int = config.DEFAULT_CONCURRENCY


def _settings_from(req: AnalyzeReq) -> config.Settings:
    return config.Settings(
        sample_size=max(1, min(req.sample_size, config.HARD_CAP_SAMPLE_SIZE)),
        concurrency=max(1, min(req.concurrency, 32)),
        force_refresh=req.force_refresh,
        web_lookup=req.web_lookup,
    )


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/config")
async def get_config():
    return {
        "niches": config.PRELOADED_NICHES,
        "default_sample_size": config.DEFAULT_SAMPLE_SIZE,
        "hard_cap": config.HARD_CAP_SAMPLE_SIZE,
        "default_concurrency": config.DEFAULT_CONCURRENCY,
        "model": config.HAIKU_MODEL,
        "rubric": [
            {"key": c.key, "label": c.label, "max": c.max_points, "bands": c.bands}
            for c in config.RUBRIC.criteria
        ],
        "tiers": config.RUBRIC.tiers,
        "mock": {"apify": config.APIFY_MOCK, "anthropic": config.ANTHROPIC_MOCK},
    }


@app.post("/api/estimate")
async def post_estimate(req: EstimateReq):
    handle = apify.parse_handle(req.handle)
    if not handle:
        raise HTTPException(400, "Could not parse an X handle from the input.")
    sample = max(1, min(req.sample_size, config.HARD_CAP_SAMPLE_SIZE))

    cached_followers = 0 if req.force_refresh else len(db.get_cached_followers(handle))
    cached_scores = 0 if req.force_refresh else len(db.get_cached_scores(handle, req.niche))
    est = cost_mod.estimate(
        sample, req.web_lookup,
        cached_followers=min(cached_followers, sample),
        cached_scores=min(cached_scores, sample),
    )
    est["handle"] = handle
    est["niche"] = req.niche
    return est


@app.post("/api/analyze")
async def post_analyze(req: AnalyzeReq):
    handle = apify.parse_handle(req.handle)
    if not handle:
        raise HTTPException(400, "Could not parse an X handle from the input.")
    jid = engine.new_job()
    asyncio.create_task(engine.run_analysis(jid, req.handle, req.niche, _settings_from(req)))
    return {"job_id": jid}


@app.get("/api/progress/{job_id}")
async def get_progress(job_id: str):
    job = engine.JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job id.")
    return {
        "status": job["status"],
        "phase": job["phase"],
        "scraped": job["scraped"],
        "scored": job["scored"],
        "total": job["total"],
        "skipped": job["skipped"],
        "spend": job["spend"],
        "logs": job["logs"][-12:],
        "error": job["error"],
        "result": job["result"],
        "handle": job.get("handle"),
        "niche": job.get("niche"),
    }


@app.get("/api/analyses")
async def get_analyses():
    return {"analyses": db.list_analyses()}


@app.get("/api/analyses/{analysis_id}")
async def get_analysis(analysis_id: str):
    res = db.get_analysis(analysis_id)
    if res is None:
        raise HTTPException(404, "Unknown analysis id.")
    return res


# --------------------------------------------------------------------------- #
# Frontend (single-page React via CDN, served from /web)
# --------------------------------------------------------------------------- #
@app.get("/")
async def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
