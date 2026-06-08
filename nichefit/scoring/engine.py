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
from .scorer import Scorer, is_junk, junk_score


def bell_percentile(score: float, population: list[float] | None = None) -> float:
    """Where `score` falls on the bell curve of all account scores (0-100).

    Blends the assumed prior distribution with the empirical mean/std of the graded
    accounts so far — the curve adapts continuously as more runs are added (the
    prior is worth BELL_PRIOR_STRENGTH accounts). Returns the percentile
    (e.g. 84 = better than 84% of accounts).
    """
    prior_mean, prior_std = config.ACCOUNT_SCORE_MEAN, config.ACCOUNT_SCORE_STD
    w = config.BELL_PRIOR_STRENGTH
    pop = population or []
    n = len(pop)
    if n == 0:
        mu, sigma = prior_mean, prior_std
    else:
        emp_mean = sum(pop) / n
        emp_var = sum((x - emp_mean) ** 2 for x in pop) / n
        mu = (w * prior_mean + n * emp_mean) / (w + n)
        var = (w * prior_std ** 2 + n * emp_var) / (w + n)
        sigma = var ** 0.5
    sigma = max(1e-6, sigma)
    z = (score - mu) / sigma
    return round(0.5 * (1 + math.erf(z / (2 ** 0.5))) * 100, 1)

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


async def resolve_pool(handle: str, requested_pool: int) -> int:
    """Decide how many followers to scrape.

    requested_pool > 0  -> use it (an explicit Advanced override), clamped.
    requested_pool <= 0 -> "scan all": detect the account's follower count and
                           scrape that many (capped at the hard limit). Falls back
                           to the default pool if detection fails.
    """
    cap = config.HARD_CAP_SAMPLE_SIZE
    if requested_pool and int(requested_pool) > 0:
        return max(config.APIFY_MIN_FOLLOWERS, min(int(requested_pool), cap))
    count = await apify.fetch_follower_count(handle)
    if not count:
        return config.DEFAULT_POOL_SIZE
    return max(config.APIFY_MIN_FOLLOWERS, min(count, cap))


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

        # ---- 3. grade the real followers --------------------------------- #
        job["phase"] = "Grading followers"
        real_results: list[dict] = [obj for _, kind, obj in real_candidates if kind == "cached"]
        cached_count = len(real_results)

        def _bump_spend() -> None:
            job["spend"]["anthropic"] = round(scorer.spend_usd, 4)
            job["spend"]["total"] = round(job["spend"]["apify"] + scorer.spend_usd, 4)

        if settings.selection == "top":
            # Deep-dive: rank everyone by reach, research + grade the top N.
            research = settings.web_lookup
            real_candidates.sort(key=lambda t: t[0], reverse=True)
            chosen = real_candidates[: settings.sample_size]
            real_results = [obj for _, kind, obj in chosen if kind == "cached"]
            cached_count = len(real_results)
            to_grade = [obj for _, kind, obj in chosen if kind == "new"]
            job["total"] = len(bots) + len(chosen)
            job["scored"] = len(bots) + len(real_results)
            if to_grade:
                _log(jid, f"Researching & grading the top {len(to_grade)} follower(s) by reach…")

            async def worker(f: dict) -> None:
                web_ctx = await scorer.web_context(f) if research else None
                s = await scorer.score_one(f, web_context=web_ctx)
                if s is None:
                    job["skipped"] += 1
                    return
                real_results.append(s)
                db.save_score(handle, niche, f.get("screen_name", ""), s)
                job["scored"] += 1
                _bump_spend()

            await asyncio.gather(*(worker(f) for f in to_grade))
        else:
            # Full account: grade EVERY real follower, batched, no web research.
            research = False
            to_grade = [obj for _, kind, obj in real_candidates if kind == "new"]
            job["total"] = len(bots) + len(real_candidates)
            job["scored"] = len(bots) + len(real_results)
            bs = config.GRADE_BATCH_SIZE
            if to_grade:
                _log(jid, f"Grading all {len(to_grade)} real follower(s) in batches of {bs}…")
            batches = [to_grade[i:i + bs] for i in range(0, len(to_grade), bs)]

            async def grade_batch(batch: list[dict]) -> None:
                results = await scorer.score_batch(batch)
                for f, s in zip(batch, results):
                    if s is None:
                        job["skipped"] += 1
                        continue
                    real_results.append(s)
                    db.save_score(handle, niche, f.get("screen_name", ""), s)
                    job["scored"] += 1
                _bump_spend()

            await asyncio.gather(*(grade_batch(b) for b in batches))

        if len(bots) + len(real_results) == 0:
            raise RuntimeError(
                "No followers could be scored — the account may be private or have no "
                "followers. Check the handle and try again."
            )
        # We tried to grade real followers but every call failed — almost always an
        # Anthropic key / credit / rate-limit issue. Don't report an empty "0" result.
        if to_grade and len(real_results) == cached_count:
            raise RuntimeError(
                "Grading failed for every follower — this usually means an Anthropic "
                "API problem (invalid key, no credits, or rate limits). Please retry."
            )

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

        # The mean grade over the real (non-bot) accounts (a secondary reference).
        agg["real_audience_score"] = agg["audience_score"]

        # ---- Account Score (the headline) -------------------------------- #
        # Tier-weighted so high-value followers lift it far more than mediocre
        # ones. Full account: bots are in the denominator (they drag it down, and
        # the score reflects the WHOLE account). Top: only the graded cohort.
        whole = len(bots) + len(real_results)
        denom = whole if settings.selection != "top" else len(real_results)
        points = sum(config.TIER_POINTS.get(s.get("tier", "D"), 0) for s in real_results)
        agg["account_score"] = round(min(100.0, points / max(1, denom) * 10), 1)
        agg["audience_score"] = agg["account_score"]   # headline gauge uses this
        agg["star_a"] = sum(1 for s in real_results if s.get("tier") == "A")
        agg["star_b"] = sum(1 for s in real_results if s.get("tier") == "B")
        agg["high_value_pct"] = round(
            (agg["star_a"] + agg["star_b"]) / max(1, len(real_results)) * 100, 1
        )
        agg["score_basis"] = (
            "top cohort (tier-weighted)" if settings.selection == "top"
            else "whole account (tier-weighted)"
        )
        # Bell-curve percentile vs all previously-graded accounts.
        population = [a["account_score"] for a in db.leaderboard()]
        agg["bell_percentile"] = bell_percentile(agg["account_score"], population)

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


PERSON_NOTE = (
    "You have this person's actual profile (bio, location, links, activity counts, "
    "account age), their recent tweets, and web research. Grade all five criteria "
    "from this real evidence. Niche Relevance and Activity come mostly from the bio "
    "and recent tweets. For Real-World Influence and Authority, use the web research; "
    "if research is thin but the bio/tweets clearly show a notable role (e.g. founder/"
    "CEO of a real company, investor, recognized expert), credit it — do NOT score "
    "influence near zero just because web search was limited. Lower confidence when "
    "relying on self-reported info."
)


async def analyze_person(raw_input: str, niche: str) -> dict:
    """Analyze one specific person's influence/fit for a niche.

    Pulls the person's real profile + recent tweets (so we actually have data to
    judge), enriches with web research, then grades them. Does not scrape their
    followers.
    """
    handle = apify.parse_handle(raw_input)
    if not handle:
        raise ValueError("Could not parse an X handle from the input.")

    scorer = Scorer(niche, concurrency=1)
    apify_cost = 0.0

    # 1. Fetch the real profile + recent tweets (the reliable identity signal).
    follower = None
    if not config.APIFY_MOCK:
        follower = await apify.fetch_profile_and_tweets(handle)
        if follower is None:
            return {
                "status": "not_found",
                "handle": handle,
                "niche": niche,
                "research": "",
                "spend": 0.0,
            }
        apify_cost = round(config.PERSON_TWEETS / 1000.0 * config.APIFY_TWEET_COST_PER_1000, 4)
    else:
        follower = {"screen_name": handle, "name": handle}

    # 2. Enrich with web research (real-world influence/authority), then grade.
    web_ctx, _ = await scorer.research_person(follower, max_uses=config.PERSON_SEARCH_MAX_USES)
    score = await scorer.score_one(follower, web_context=web_ctx, note=PERSON_NOTE)
    if score is None:
        raise RuntimeError("Scoring failed — please try again.")

    result = dict(score)
    result["status"] = "ok"
    result["handle"] = handle
    result["niche"] = niche
    result["name"] = follower.get("name", handle)
    result["bio"] = follower.get("description", "")
    result["tweet_count"] = len(follower.get("tweets") or [])
    result["research"] = web_ctx or ""
    result["researched"] = web_ctx is not None
    result["spend"] = round(scorer.spend_usd + apify_cost, 4)
    result["mock"] = {"apify": config.APIFY_MOCK, "anthropic": config.ANTHROPIC_MOCK}
    return result
