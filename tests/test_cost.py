"""Pre-run cost estimate: pool scrape + capped real sample + cache discount."""
from nichefit.scoring.cost import estimate


def test_estimate_scales_with_sample_size():
    small = estimate(50, pool_size=100, web_lookup=False)
    big = estimate(500, pool_size=1000, web_lookup=False)
    assert big["total_cost"] > small["total_cost"]
    assert small["to_scrape"] == 100          # whole pool is scraped
    assert small["to_score"] <= 50            # capped by sample size (after bot filter)


def test_cache_discounts_cost_to_zero():
    est = estimate(200, pool_size=200, web_lookup=False, cached_followers=200, cached_scores=200)
    assert est["to_scrape"] == 0
    assert est["to_score"] == 0
    assert est["apify_cost"] == 0.0
    assert est["haiku_cost"] == 0.0
    assert est["total_cost"] == 0.0


def test_bot_filter_reduces_analyzed_count():
    with_filter = estimate(1000, pool_size=1000, web_lookup=False, skip_bots=True)
    without = estimate(1000, pool_size=1000, web_lookup=False, skip_bots=False)
    assert with_filter["to_score"] < without["to_score"]


def test_web_research_adds_capped_cost():
    est = estimate(200, pool_size=1000, web_lookup=True)
    no_web = estimate(200, pool_size=1000, web_lookup=False)
    assert est["web_lookups"] > 0
    assert est["web_cost"] > 0
    assert est["total_cost"] > no_web["total_cost"]
