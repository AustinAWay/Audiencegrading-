"""Aggregation math and a full offline run through the engine (mock mode)."""
from nichefit import config
from nichefit.scoring import engine


def _score(total, followers, tier=None):
    # Distribute `total` across criteria just enough to sum correctly isn't
    # needed here — aggregate() reads `total`, per-criterion keys, tier, etc.
    return {
        "niche_relevance": min(35, total),
        "influence_reach": 0, "authority": 0,
        "engagement_quality": 0, "authenticity": 0,
        "total": total,
        "tier": tier or config.RUBRIC.tier_for(total),
        "confidence": 0.8,
        "screen_name": f"u{total}",
        "followers_count": followers,
    }


def test_aggregate_scores_and_tiers():
    scores = [_score(90, 100000), _score(70, 5000), _score(30, 50)]
    agg = engine.aggregate("acct", "tech / SaaS", scores)
    assert agg["scored"] == 3
    assert agg["audience_score"] == round((90 + 70 + 30) / 3, 1)
    assert agg["tiers"] == {"A": 1, "B": 1, "C": 0, "D": 1}
    # influence weighting lifts the score (the 90 has the most followers)
    assert agg["weighted_score"] >= agg["audience_score"]
    assert agg["top_followers"][0]["total"] == 90


def test_aggregate_empty():
    agg = engine.aggregate("acct", "n", [])
    assert agg["scored"] == 0
    assert agg["audience_score"] == 0
    assert agg["top_followers"] == []


async def test_full_run_in_mock_mode():
    assert config.APIFY_MOCK and config.ANTHROPIC_MOCK  # conftest forces this
    jid = engine.new_job()
    settings = config.Settings(sample_size=20, concurrency=8, force_refresh=True)
    await engine.run_analysis(jid, "https://x.com/naval", "tech / SaaS", settings)

    job = engine.JOBS[jid]
    assert job["status"] == "done", job["error"]
    result = job["result"]
    assert result["scored"] == 20
    assert 0 <= result["audience_score"] <= 100
    assert sum(result["tiers"].values()) == 20
    assert len(result["top_followers"]) <= 25
    assert result["summary"]
    # mock mode never spends
    assert result["spend"]["total"] == 0.0
