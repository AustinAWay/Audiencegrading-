"""The rubric: totals, tier boundaries, and prompt rendering."""
from nichefit import config


def test_max_total_is_100():
    assert config.RUBRIC.max_total == 100


def test_tier_boundaries():
    tier_for = config.RUBRIC.tier_for
    assert tier_for(100) == "A"
    assert tier_for(80) == "A"
    assert tier_for(79) == "B"
    assert tier_for(60) == "B"
    assert tier_for(59) == "C"
    assert tier_for(40) == "C"
    assert tier_for(39) == "D"
    assert tier_for(0) == "D"


def test_rubric_prompt_text_includes_every_criterion_and_bands():
    text = config.rubric_as_prompt_text()
    for c in config.RUBRIC.criteria:
        assert c.label in text
        assert f"0 to {c.max_points} points" in text
    assert "Total = sum of the five criteria (0-100)." in text
    assert "Tiers:" in text
