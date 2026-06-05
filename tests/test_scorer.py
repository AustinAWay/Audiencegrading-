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
        "niche_relevance": 999,   # over max (35) -> clamp
        "influence_reach": -5,    # under 0 -> clamp
        "authority": 20,
        "engagement_quality": 10,
        "authenticity": 10,
        "total": 3,               # wrong -> recomputed
        "tier": "D",              # wrong -> recomputed
        "confidence": 5.0,        # over 1 -> clamp
    }
    out = scorer._coerce_and_validate(raw, FOLLOWER)
    assert out["niche_relevance"] == 35
    assert out["influence_reach"] == 0
    assert out["total"] == 35 + 0 + 20 + 10 + 10  # == 75
    assert out["tier"] == config.RUBRIC.tier_for(75) == "B"
    assert out["confidence"] == 1.0
    assert out["screen_name"] == "x"


def test_heuristic_scores_are_valid_records():
    for f in MOCK_FOLLOWERS:
        s = scorer.heuristic_score(f, "tech / SaaS")
        assert 0 <= s["total"] <= 100
        assert s["tier"] in ("A", "B", "C", "D")
        for c in config.RUBRIC.criteria:
            assert 0 <= s[c.key] <= c.max_points


def test_heuristic_ranks_expert_above_bot():
    expert = next(f for f in MOCK_FOLLOWERS if f["screen_name"] == "dharmesh")
    bot = next(f for f in MOCK_FOLLOWERS if f["screen_name"] == "promo_bot_9931")
    assert (
        scorer.heuristic_score(expert, "tech / SaaS")["total"]
        > scorer.heuristic_score(bot, "tech / SaaS")["total"]
    )
