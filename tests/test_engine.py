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
    assert agg["top_followers"][0]["total"] == 90


def test_aggregate_empty():
    agg = engine.aggregate("acct", "n", [])
    assert agg["scored"] == 0
    assert agg["audience_score"] == 0
    assert agg["top_followers"] == []


async def test_full_run_grades_every_real_follower():
    assert config.APIFY_MOCK and config.ANTHROPIC_MOCK  # conftest forces this
    jid = engine.new_job()
    settings = config.Settings(pool_size=200, force_refresh=True)  # selection="random" (full)
    await engine.run_analysis(jid, "https://x.com/naval", "tech / SaaS", settings)

    job = engine.JOBS[jid]
    assert job["status"] == "done", job["error"]
    result = job["result"]
    # Full account grades EVERY real follower (not a capped sample): analyzed + bots
    # account for the whole pool.
    assert result["analyzed"] + result["flagged_bots"] == result["pool_size"]
    assert result["flagged_bots"] >= 1
    assert sum(result["tiers"].values()) == result["analyzed"]
    # tier-weighted account score is the headline
    assert 0 <= result["account_score"] <= 100
    assert result["audience_score"] == result["account_score"]
    assert "high_value_pct" in result and "star_a" in result
    assert result["summary"]
    assert result["spend"]["total"] == 0.0  # mock never spends
    assert abs(sum(result["projected"].values()) - 100) < 2.0
    # full ranked roster, sorted by grade desc
    roster = result["followers"]
    assert len(roster) == result["analyzed"]
    assert all(roster[i]["total"] >= roster[i + 1]["total"] for i in range(len(roster) - 1))


def test_bell_percentile():
    mean, std = config.ACCOUNT_SCORE_MEAN, config.ACCOUNT_SCORE_STD
    assert engine.bell_percentile(mean) == 50.0            # at the mean -> 50th percentile
    assert engine.bell_percentile(mean + std) > 80         # +1 std -> ~84th
    assert engine.bell_percentile(0) < 10                  # well below mean
    # adapts to the data: the same score ranks higher among low scorers than high ones
    low_pop = [5, 8, 10, 12, 15] * 4
    high_pop = [60, 65, 70, 75, 80] * 4
    assert engine.bell_percentile(50, low_pop) > engine.bell_percentile(50, high_pop)


async def test_leaderboard_and_clear():
    from nichefit.data import cache
    cache.clear_all()
    jid = engine.new_job()
    await engine.run_analysis(jid, "@acct", "tech / SaaS", config.Settings(pool_size=60, force_refresh=True))
    board = cache.leaderboard()
    assert len(board) >= 1 and "account_score" in board[0]
    assert "bell_percentile" in engine.JOBS[jid]["result"]
    cache.clear_all()
    assert cache.leaderboard() == []


async def test_analyze_person_returns_a_grade():
    res = await engine.analyze_person("@sama", "AI / machine learning")
    assert res["handle"] == "sama"
    assert 0 <= res["total"] <= 100
    assert res["tier"] in ("A", "B", "C", "D")
    assert "niche_relevance" in res


async def test_top_selection_picks_highest_reach():
    jid = engine.new_job()
    settings = config.Settings(
        sample_size=5, pool_size=200, selection="top",
        web_lookup=False, force_refresh=True,
    )
    await engine.run_analysis(jid, "@whoever", "tech / SaaS", settings)
    result = engine.JOBS[jid]["result"]
    assert result["selection"] == "top"
    assert result["analyzed"] == 5  # top mode is capped at sample_size
    # the highest-reach real follower in the mock cast has millions of followers
    assert result["top_followers"][0]["followers_count"] >= 1_000_000
    assert 0 <= result["account_score"] <= 100
