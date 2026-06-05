"""
Run orchestration: scrape -> score (concurrently) -> aggregate -> summarize.

Progress is published into an in-memory job store that the API polls. Caching is
consulted before any paid call, and "force refresh" clears the relevant cache
rows first. Exceptions are captured into the job record so the server never
crashes on a bad run.
"""
from __future__ import annotations

import asyncio
import math
import time
import uuid

from .. import config
from ..data import apify
from ..data import cache as db
from .scorer import Scorer

# job_id -> live job state (read by the /progress endpoint)
JOBS: dict[str, dict] = {}


def new_job() -> str:
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {
        "status": "queued",
        "phase": "Queued",
        "scraped": 0,
        "scored": 0,
        "total": 0,
        "skipped": 0,
        "spend": {"apify": 0.0, "anthropic": 0.0, "total": 0.0},
        "logs": [],
        "result": None,
        "error": None,
        "started_at": time.time(),
    }
    return jid


def _log(jid: str, msg: str) -> None:
    job = JOBS.get(jid)
    if job is not None:
        job["logs"].append(msg)
        job["logs"] = job["logs"][-40:]


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def aggregate(handle: str, niche: str, scores: list[dict]) -> dict:
    """Roll per-follower scores up into the audience-level result object."""
    n = len(scores)
    if n == 0:
        return {
            "handle": handle, "niche": niche, "scored": 0,
            "audience_score": 0, "weighted_score": 0,
            "criteria_avg": {}, "tiers": {"A": 0, "B": 0, "C": 0, "D": 0},
            "top_followers": [], "avg_confidence": 0,
        }

    totals = [s["total"] for s in scores]
    audience = sum(totals) / n

    # Influence-weighted average: weight = log10(followers + 1).
    weights = [math.log10((s.get("followers_count", 0) or 0) + 1) for s in scores]
    wsum = sum(weights) or 1.0
    weighted = sum(t * w for t, w in zip(totals, weights)) / wsum

    criteria_avg = {}
    for c in config.RUBRIC.criteria:
        criteria_avg[c.key] = {
            "label": c.label,
            "max": c.max_points,
            "avg": round(sum(s.get(c.key, 0) for s in scores) / n, 2),
        }

    tiers = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in scores:
        tiers[s.get("tier", "D")] = tiers.get(s.get("tier", "D"), 0) + 1

    top = sorted(
        scores, key=lambda s: (s["total"], s.get("followers_count", 0)), reverse=True
    )[:25]

    return {
        "handle": handle,
        "niche": niche,
        "scored": n,
        "audience_score": round(audience, 1),
        "weighted_score": round(weighted, 1),
        "criteria_avg": criteria_avg,
        "tiers": tiers,
        "top_followers": top,
        "avg_confidence": round(sum(s.get("confidence", 0) for s in scores) / n, 2),
    }


def _qualifies_for_lookup(f: dict) -> bool:
    return (f.get("followers_count", 0) or 0) >= config.WEB_LOOKUP_MIN_FOLLOWERS


# --------------------------------------------------------------------------- #
# Main run coroutine
# --------------------------------------------------------------------------- #
async def run_analysis(jid: str, raw_input: str, niche: str, settings: config.Settings) -> None:
    job = JOBS[jid]
    handle = apify.parse_handle(raw_input)
    try:
        if not handle:
            raise ValueError("Could not parse an X handle from the input.")
        job["status"] = "running"
        job["handle"] = handle
        job["niche"] = niche

        # ---- force refresh clears caches ---------------------------------- #
        if settings.force_refresh:
            db.clear_followers(handle)
            db.clear_scores(handle, niche)
            _log(jid, "Force refresh: cleared cached followers + scores.")

        # ---- 1. followers (cache first) ----------------------------------- #
        job["phase"] = "Scraping followers"
        cached = db.get_cached_followers(handle)
        if len(cached) >= settings.sample_size:
            followers = cached[: settings.sample_size]
            _log(jid, f"Using {len(followers)} cached followers (no Apify spend).")
        else:
            followers = await apify.fetch_followers(
                handle, settings.sample_size, progress=lambda m: _log(jid, m)
            )
            db.save_followers(handle, followers)
            if not config.APIFY_MOCK:
                job["spend"]["apify"] = round(
                    len(followers) / 1000.0 * config.APIFY_COST_PER_1000_FOLLOWERS, 4
                )

        followers = followers[: settings.sample_size]
        job["scraped"] = len(followers)
        job["total"] = len(followers)
        if not followers:
            raise RuntimeError("No followers returned. Check the handle / Apify token.")
        _log(jid, f"Scoring {len(followers)} followers (concurrency {settings.concurrency})…")

        # ---- 2. score (cache first, then concurrent Haiku) ---------------- #
        job["phase"] = "Scoring followers"
        cached_scores = db.get_cached_scores(handle, niche)
        scorer = Scorer(niche, settings.concurrency)

        results: list[dict] = []
        to_score: list[dict] = []
        for f in followers:
            sn = (f.get("screen_name") or "").lower()
            if sn in cached_scores:
                results.append(cached_scores[sn])
                job["scored"] += 1
            else:
                to_score.append(f)
        if results:
            _log(jid, f"{len(results)} followers already scored (cache hit).")

        # optional web-lookup gate: top accounts by follower_count
        lookup_targets = set()
        if settings.web_lookup:
            ranked = sorted(to_score, key=lambda f: f.get("followers_count", 0), reverse=True)
            cap = min(
                config.WEB_LOOKUP_MAX_PER_RUN,
                max(1, int(len(followers) * config.WEB_LOOKUP_TOP_PERCENTILE)),
            )
            for f in ranked[:cap]:
                if _qualifies_for_lookup(f):
                    lookup_targets.add((f.get("screen_name") or "").lower())
            if lookup_targets:
                _log(jid, f"Web lookup enabled for {len(lookup_targets)} top account(s).")

        async def worker(f: dict) -> None:
            web_ctx = None
            sn = (f.get("screen_name") or "").lower()
            if sn in lookup_targets:
                web_ctx = await scorer.web_context(f)
            s = await scorer.score_one(f, web_context=web_ctx)
            if s is None:
                job["skipped"] += 1
                return
            results.append(s)
            db.save_score(handle, niche, f.get("screen_name", ""), s)
            job["scored"] += 1
            job["spend"]["anthropic"] = round(scorer.spend_usd, 4)
            job["spend"]["total"] = round(job["spend"]["apify"] + scorer.spend_usd, 4)

        await asyncio.gather(*(worker(f) for f in to_score))

        if not results:
            raise RuntimeError("All followers failed to score.")

        # ---- 3. aggregate + summary --------------------------------------- #
        job["phase"] = "Writing summary"
        agg = aggregate(handle, niche, results)
        agg["summary"] = await scorer.write_summary(handle, agg)
        agg["skipped"] = job["skipped"]
        agg["spend"] = {
            "apify": job["spend"]["apify"],
            "anthropic": round(scorer.spend_usd, 4),
            "total": round(job["spend"]["apify"] + scorer.spend_usd, 4),
        }
        agg["mock"] = {"apify": config.APIFY_MOCK, "anthropic": config.ANTHROPIC_MOCK}
        agg["sample_size"] = settings.sample_size

        analysis_id = uuid.uuid4().hex[:12]
        agg["id"] = analysis_id
        db.save_analysis(analysis_id, handle, niche, agg)

        job["spend"]["anthropic"] = agg["spend"]["anthropic"]
        job["spend"]["total"] = agg["spend"]["total"]
        job["result"] = agg
        job["phase"] = "Done"
        job["status"] = "done"
        _log(jid, f"Done. Audience score {agg['audience_score']}/100.")
    except Exception as e:  # surface, don't crash the server
        job["status"] = "error"
        job["error"] = str(e)
        _log(jid, f"ERROR: {e}")
