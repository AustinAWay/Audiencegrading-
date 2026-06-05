"""Pre-run cost estimate (Apify followers + Haiku tokens + optional web lookups)."""
from __future__ import annotations

from .. import config


def estimate(
    sample_size: int,
    web_lookup: bool,
    cached_followers: int = 0,
    cached_scores: int = 0,
) -> dict:
    """Estimate the spend for a run, discounting whatever is already cached."""
    to_scrape = max(0, sample_size - cached_followers)
    to_score = max(0, sample_size - cached_scores)

    apify_cost = to_scrape / 1000.0 * config.APIFY_COST_PER_1000_FOLLOWERS

    in_tok = to_score * config.EST_INPUT_TOKENS_PER_FOLLOWER
    out_tok = to_score * config.EST_OUTPUT_TOKENS_PER_FOLLOWER
    haiku_cost = (
        in_tok / 1_000_000 * config.HAIKU_INPUT_PRICE_PER_MTOK
        + out_tok / 1_000_000 * config.HAIKU_OUTPUT_PRICE_PER_MTOK
    )

    lookups = 0
    web_cost = 0.0
    if web_lookup:
        lookups = min(
            config.WEB_LOOKUP_MAX_PER_RUN,
            max(1, int(sample_size * config.WEB_LOOKUP_TOP_PERCENTILE)),
        )
        web_cost = lookups * config.WEB_LOOKUP_EST_TOKENS / 1_000_000 * (
            config.HAIKU_INPUT_PRICE_PER_MTOK + config.HAIKU_OUTPUT_PRICE_PER_MTOK
        )

    total = apify_cost + haiku_cost + web_cost
    return {
        "sample_size": sample_size,
        "to_scrape": to_scrape,
        "to_score": to_score,
        "cached_followers": cached_followers,
        "cached_scores": cached_scores,
        "apify_cost": round(apify_cost, 4),
        "haiku_cost": round(haiku_cost, 4),
        "web_lookups": lookups,
        "web_cost": round(web_cost, 4),
        "total_cost": round(total, 4),
        "apify_mock": config.APIFY_MOCK,
        "anthropic_mock": config.ANTHROPIC_MOCK,
    }
