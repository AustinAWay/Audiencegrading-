"""Pre-run cost estimate, including the cache discount."""
from nichefit.scoring.cost import estimate


def test_estimate_scales_with_sample_size():
    small = estimate(100, web_lookup=False)
    big = estimate(1000, web_lookup=False)
    assert big["total_cost"] > small["total_cost"]
    assert small["to_scrape"] == 100 and small["to_score"] == 100


def test_cache_discounts_cost_to_zero():
    est = estimate(200, web_lookup=False, cached_followers=200, cached_scores=200)
    assert est["to_scrape"] == 0
    assert est["to_score"] == 0
    assert est["apify_cost"] == 0.0
    assert est["haiku_cost"] == 0.0
    assert est["total_cost"] == 0.0


def test_web_lookup_adds_capped_cost():
    est = estimate(2000, web_lookup=True)
    assert est["web_lookups"] > 0
    assert est["web_cost"] > 0
    no_web = estimate(2000, web_lookup=False)
    assert est["total_cost"] > no_web["total_cost"]
