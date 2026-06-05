"""
Run orchestration: scrape -> score (concurrently) -> aggregate -> summarize.

Progress is published into an in-memory job store that the API polls. Caching is
consulted before any paid call, and "force refresh" clears the relevant cache
rows first. Exceptions are captured into the job record so the server never
crashes on a bad run.
"""
from __future__ import annotations

import asyncio
import random
import time
import uuid

from .. import config
from ..data import apify
from ..data import cache as db
from .scorer import Scorer, is_junk, junk_score

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
            "audience_score": 0,
            "criteria_avg": {}, "tiers": {"A": 0, "B": 0, "C": 0, "D": 0},
            "top_followers": [], "avg_confidence": 0,
        }

    totals = [s["total"] for s in scores]
    audience = sum(totals) / n

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
        "criteria_avg": criteria_avg,
        "tiers": tiers,
        "top_followers": top,
        "avg_confidence": round(sum(s.get("confidence", 0) for s in scores) / n, 2),
    }


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

        # ---- 1. scrape a POOL of followers (cheap; cache first) ----------- #
        job["phase"] = "Scraping followers"
        cached = db.get_cached_followers(handle)
        if len(cached) >= settings.pool_size:
            followers = cached[: settings.pool_size]
            _log(jid, f"Using {len(followers)} cached followers (no Apify spend).")
        else:
            followers = await apify.fetch_followers(
                handle, settings.pool_size, progress=lambda m: _log(jid, m)
            )
            db.save_followers(handle, followers)
            if not config.APIFY_MOCK:
                job["spend"]["apify"] = round(
                    len(followers) / 1000.0 * config.APIFY_COST_PER_1000_FOLLOWERS, 4
                )

        followers = followers[: settings.pool_size]
        job["scraped"] = len(followers)
        if not followers:
            raise RuntimeError("No followers returned. Check the handle / Apify token.")

        # ---- 2. free bot/junk filter over the whole pool ------------------ #
        job["phase"] = "Filtering bots"
        cached_scores = db.get_cached_scores(handle, niche)
        scorer = Scorer(niche, settings.concurrency)

        bots: list[dict] = []            # flagged fake/inactive (free)
        # real candidates carried as (followers_count, kind, obj); kind: cached|new
        real_candidates: list[tuple] = []
        for f in followers:
            sn = (f.get("screen_name") or "").lower()
            if sn in cached_scores:
                rec = cached_scores[sn]
                if rec.get("bot"):
                    bots.append(rec)
                else:
                    real_candidates.append((rec.get("followers_count", 0), "cached", rec))
            elif settings.skip_bots and is_junk(f):
                rec = junk_score(f)
                db.save_score(handle, niche, f.get("screen_name", ""), rec)
                bots.append(rec)
            else:
                real_candidates.append((f.get("followers_count", 0), "new", f))
        _log(jid, f"Pool of {len(followers)}: {len(bots)} flagged as bots/inactive "
                  f"(free), {len(real_candidates)} look real.")

        # ---- 3. choose which real followers to deeply analyze ------------- #
        # "top" -> the highest-reach followers; "random" -> a representative sample.
        # Bots are skipped for free, so the sample tops up past them to stay full.
        if settings.selection == "top":
            real_candidates.sort(key=lambda t: t[0], reverse=True)
        else:
            random.shuffle(real_candidates)
        chosen = real_candidates[: settings.sample_size]

        real_results: list[dict] = [obj for _, kind, obj in chosen if kind == "cached"]
        to_analyze: list[dict] = [obj for _, kind, obj in chosen if kind == "new"]

        job["total"] = len(bots) + len(chosen)
        job["scored"] = len(bots) + len(real_results)

        research = settings.web_lookup
        job["phase"] = "Scoring followers"
        if to_analyze:
            extra = " with web research" if research else " (no research — cheap)"
            pick = "top-reach" if settings.selection == "top" else "random"
            _log(jid, f"Deeply analyzing {len(to_analyze)} {pick} real follower(s){extra} "
                      f"(concurrency {settings.concurrency})…")

        async def worker(f: dict) -> None:
            web_ctx = await scorer.web_context(f) if research else None
            s = await scorer.score_one(f, web_context=web_ctx)
            if s is None:
                job["skipped"] += 1
                return
            real_results.append(s)
            db.save_score(handle, niche, f.get("screen_name", ""), s)
            job["scored"] += 1
            job["spend"]["anthropic"] = round(scorer.spend_usd, 4)
            job["spend"]["total"] = round(job["spend"]["apify"] + scorer.spend_usd, 4)

        await asyncio.gather(*(worker(f) for f in to_analyze))

        if len(bots) + len(real_results) == 0:
            raise RuntimeError("No followers could be scored. Check the handle / tokens.")

        # ---- 4. aggregate (quality over the real sample) + bot stats ------ #
        job["phase"] = "Writing summary"
        pool = len(followers)
        agg = aggregate(handle, niche, real_results)
        agg["flagged_bots"] = len(bots)
        agg["bot_rate"] = round(len(bots) / max(1, pool) * 100, 1)
        agg["pool_size"] = pool
        agg["analyzed"] = len(real_results)
        agg["selection"] = settings.selection
        agg["researched"] = research
        # The full ranked roster (every analyzed real follower), highest grade first.
        agg["followers"] = sorted(
            real_results, key=lambda s: (s["total"], s.get("followers_count", 0)), reverse=True
        )

        # The mean over the real (non-bot) accounts.
        agg["real_audience_score"] = agg["audience_score"]
        if settings.selection == "top":
            # "Top followers": the headline is the quality of the elite cohort
            # itself, so the bot rate does not drag it down.
            agg["score_basis"] = "top followers by reach"
        else:
            # "Whole account": bots count against the audience — the bot rate
            # pulls the headline score down (real_avg x non-bot share).
            real_frac = 1 - agg["bot_rate"] / 100.0
            agg["audience_score"] = round(agg["real_audience_score"] * real_frac, 1)
            agg["score_basis"] = "whole account (bot-adjusted)"

        # Project the bot rate + real-audience mix across the WHOLE account.
        real_n = len(real_results) or 1
        real_frac = 1 - agg["bot_rate"] / 100.0
        projected = {"Bots": agg["bot_rate"]}
        for t in ("A", "B", "C", "D"):
            projected[t] = round(agg["tiers"].get(t, 0) / real_n * real_frac * 100, 1)
        agg["projected"] = projected

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
        _log(jid, f"Done. Real-audience score {agg['audience_score']}/100; "
                  f"{agg['bot_rate']}% flagged as bots.")
    except Exception as e:  # surface, don't crash the server
        job["status"] = "error"
        job["error"] = str(e)
        _log(jid, f"ERROR: {e}")


# Standalone person check: no account stats are available, so tell the model to
# judge on research and not penalise the activity/authenticity criteria.
PERSON_NOTE = (
    "This is a standalone person-influence check — only their handle, bio, and web "
    "research are available, with NO account activity statistics. Judge Niche "
    "Relevance, Real-World Influence, and Authority from the research; for Activity "
    "and Authenticity, score neutrally (mid-range) and lower your confidence rather "
    "than penalising for missing data."
)


async def analyze_person(raw_input: str, niche: str) -> dict:
    """Analyze one specific person's influence/fit for a niche (research + score).

    Does not scrape an account's followers — it researches the individual and
    scores them directly. Cheap (one research + one scoring call).
    """
    handle = apify.parse_handle(raw_input)
    if not handle:
        raise ValueError("Could not parse an X handle from the input.")
    scorer = Scorer(niche, concurrency=1)
    follower = {"screen_name": handle, "name": handle}
    web_ctx = await scorer.web_context(follower)
    score = await scorer.score_one(follower, web_context=web_ctx, note=PERSON_NOTE)
    if score is None:
        raise RuntimeError("Could not score this person — try again.")
    result = dict(score)
    result["handle"] = handle
    result["niche"] = niche
    result["research"] = web_ctx or ""
    result["researched"] = web_ctx is not None
    result["spend"] = round(scorer.spend_usd, 4)
    result["mock"] = {"apify": config.APIFY_MOCK, "anthropic": config.ANTHROPIC_MOCK}
    return result
