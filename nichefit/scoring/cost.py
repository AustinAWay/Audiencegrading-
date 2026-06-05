"""Pre-run cost estimate (Apify pool scrape + Haiku scoring + web research).

Cost is decoupled from account size: we scrape a cheap POOL, bot-filter it for
free, then deeply analyze only a capped SAMPLE of the real accounts.
"""
from __future__ import annotations

from .. import config


def estimate(
    sample_size: int,
    pool_size: int,
    web_lookup: bool,
    skip_bots: bool = True,
    cached_followers: int = 0,
    cached_scores: int = 0,
) -> dict:
    """Estimate the spend for a run, discounting whatever is already cached."""
    # Apify: scrape the whole pool (only the part not already cached).
    to_scrape = max(0, pool_size - cached_followers)
    apify_cost = to_scrape / 1000.0 * config.APIFY_COST_PER_1000_FOLLOWERS

    # How many real (non-bot) accounts we expect to deeply analyze.
    est_real = pool_size * config.EST_ANALYZABLE_FRACTION if skip_bots else pool_size
    to_analyze = min(sample_size, int(round(est_real)))
    to_score = max(0, to_analyze - cached_scores)

    in_tok = to_score * config.EST_INPUT_TOKENS_PER_FOLLOWER
    out_tok = to_score * config.EST_OUTPUT_TOKENS_PER_FOLLOWER
    haiku_cost = (
        in_tok / 1_000_000 * config.HAIKU_INPUT_PRICE_PER_MTOK
        + out_tok / 1_000_000 * config.HAIKU_OUTPUT_PRICE_PER_MTOK
    )

    # Web research runs once per analyzed follower (one search + tokens each).
    lookups = 0
    web_cost = 0.0
    if web_lookup:
        lookups = to_score
        web_tokens_cost = lookups * config.WEB_LOOKUP_EST_TOKENS / 1_000_000 * (
            config.HAIKU_INPUT_PRICE_PER_MTOK + config.HAIKU_OUTPUT_PRICE_PER_MTOK
        )
        web_cost = web_tokens_cost + lookups * config.WEB_SEARCH_COST_PER_CALL

    total = apify_cost + haiku_cost + web_cost
    return {
        "sample_size": sample_size,
        "pool_size": pool_size,
        "to_scrape": to_scrape,
        "to_score": to_score,            # deeply-analyzed (estimated, after bot filter)
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
