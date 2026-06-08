"""JSON extraction, score validation/clamping, and the heuristic fallback."""
from nichefit import config
from nichefit.data.mock import MOCK_FOLLOWERS
from nichefit.scoring import scorer

FOLLOWER = {"screen_name": "x", "name": "X", "followers_count": 1234}


def test_extract_json_grabs_last_block_after_reasoning():
    text = 'Let me think... {"a": 1}\nFinal: {"niche_relevance": 5}'
    assert scorer._extract_json(text) == {"niche_relevance": 5}


def test_extract_json_returns_none_on_garbage():
    assert scorer._extract_json("no json here") is None


def test_coerce_clamps_out_of_range_and_recomputes_total_and_tier():
    raw = {
        "niche_relevance": 999,   # over max -> clamp to band max
        "influence_reach": -5,    # under 0 -> clamp
        "authority": 20,
        "engagement_quality": 99,
        "authenticity": 99,
        "total": 3,               # wrong -> recomputed
        "tier": "D",              # wrong -> recomputed
        "confidence": 5.0,        # over 1 -> clamp
    }
    out = scorer._coerce_and_validate(raw, FOLLOWER)
    maxes = {c.key: c.max_points for c in config.RUBRIC.criteria}
    assert out["niche_relevance"] == maxes["niche_relevance"]
    assert out["influence_reach"] == 0
    assert out["engagement_quality"] == maxes["engagement_quality"]
    expected_total = maxes["niche_relevance"] + 0 + 20 + maxes["engagement_quality"] + maxes["authenticity"]
    assert out["total"] == expected_total
    assert out["tier"] == config.RUBRIC.tier_for(expected_total)
    assert out["confidence"] == 1.0
    assert out["screen_name"] == "x"


def test_heuristic_scores_are_valid_records():
    for f in MOCK_FOLLOWERS:
        s = scorer.heuristic_score(f, "tech / SaaS")
        assert 0 <= s["total"] <= 100
        assert s["tier"] in ("A", "B", "C", "D")
        for c in config.RUBRIC.criteria:
            assert 0 <= s[c.key] <= c.max_points


def test_is_junk_flags_spam_and_empty_but_not_real():
    spam = {"description": "Follow back! DM for promo", "statuses_count": 100}
    empty = {"description": "", "name": "", "statuses_count": 0, "status": None}
    real = next(f for f in MOCK_FOLLOWERS if f["screen_name"] == "dharmesh")
    verified_sparse = {"description": "", "statuses_count": 0, "status": None, "verified": True}
    assert scorer.is_junk(spam) is True
    assert scorer.is_junk(empty) is True
    assert scorer.is_junk(real) is False
    assert scorer.is_junk(verified_sparse) is False  # verified is never junk
    # a blank/silent but HIGH-REACH account is kept (likely a real, influential lurker)
    high_reach_blank = {"description": "", "statuses_count": 0, "status": None, "followers_count": 5000}
    assert scorer.is_junk(high_reach_blank) is False


def test_junk_score_is_free_tier_d():
    f = {"screen_name": "bot1", "name": "bot", "followers_count": 0}
    s = scorer.junk_score(f)
    assert s["bot"] is True
    assert s["total"] == 0
    assert s["tier"] == "D"


def test_heuristic_ranks_expert_above_bot():
    expert = next(f for f in MOCK_FOLLOWERS if f["screen_name"] == "dharmesh")
    bot = next(f for f in MOCK_FOLLOWERS if f["screen_name"] == "promo_bot_9931")
    assert (
        scorer.heuristic_score(expert, "tech / SaaS")["total"]
        > scorer.heuristic_score(bot, "tech / SaaS")["total"]
    )
