"""Pre-run cost estimate.

Two grading paths with very different costs:
  - "full"  -> grade EVERY real follower, batched, no web research (cheap/follower).
  - "top"   -> research + grade only the top N by reach (expensive/follower).
"""
from __future__ import annotations

from .. import config


def estimate(
    sample_size: int,
    pool_size: int,
    web_lookup: bool,
    selection: str = "random",
    skip_bots: bool = True,
    cached_followers: int = 0,
    cached_scores: int = 0,
) -> dict:
    """Estimate the spend for a run, discounting whatever is already cached."""
    # Apify: scrape the pool (only the part not already cached).
    to_scrape = max(0, pool_size - cached_followers)
    apify_cost = to_scrape / 1000.0 * config.APIFY_COST_PER_1000_FOLLOWERS

    # Expected number of real (non-bot) accounts in the pool.
    est_real = pool_size * config.EST_ANALYZABLE_FRACTION if skip_bots else pool_size

    if selection == "top":
        # Deep dive: research + grade only the top N.
        to_grade = min(sample_size, int(round(est_real)))
        in_per = config.EST_INPUT_TOKENS_PER_FOLLOWER
        out_per = config.EST_OUTPUT_TOKENS_PER_FOLLOWER
    else:
        # Full account: grade ALL real followers, batched (much cheaper/follower).
        to_grade = int(round(est_real))
        in_per, out_per = (
            config.EST_BATCH_INPUT_TOKENS_PER_FOLLOWER,
            config.EST_BATCH_OUTPUT_TOKENS_PER_FOLLOWER,
        )

    to_score = max(0, to_grade - cached_scores)
    haiku_cost = (
        to_score * in_per / 1_000_000 * config.HAIKU_INPUT_PRICE_PER_MTOK
        + to_score * out_per / 1_000_000 * config.HAIKU_OUTPUT_PRICE_PER_MTOK
    )

    # Web research runs once per graded follower — only in "top" mode.
    lookups = 0
    web_cost = 0.0
    if web_lookup and selection == "top":
        lookups = to_score
        web_tokens_cost = lookups * config.WEB_LOOKUP_EST_TOKENS / 1_000_000 * (
            config.HAIKU_INPUT_PRICE_PER_MTOK + config.HAIKU_OUTPUT_PRICE_PER_MTOK
        )
        web_cost = web_tokens_cost + lookups * config.WEB_SEARCH_COST_PER_CALL

    total = apify_cost + haiku_cost + web_cost
    return {
        "sample_size": sample_size,
        "pool_size": pool_size,
        "selection": selection,
        "to_scrape": to_scrape,
        "to_score": to_score,            # followers graded (estimated, after bot filter)
        "cached_followers": cached_followers,
        "cached_scores": cached_scores,
        "skip_bots": skip_bots,
        "apify_cost": round(apify_cost, 4),
        "haiku_cost": round(haiku_cost, 4),
        "web_lookups": lookups,
        "web_cost": round(web_cost, 4),
        "total_cost": round(total, 4),
        "apify_mock": config.APIFY_MOCK,
        "anthropic_mock": config.ANTHROPIC_MOCK,
    }
