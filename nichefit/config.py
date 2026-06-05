"""
NicheFit configuration — the tunable core.

Everything you'd want to adjust lives here: the scoring rubric (weights + point
bands), tier thresholds, concurrency/sampling defaults, cost assumptions, and
the optional web-lookup gate. Edit this file to retune the engine; environment
variables (see .env.example) override the numeric defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level up from the package), regardless of
# CWD. override=True so the app's own .env wins over empty/placeholder shell env
# vars (some shells/harnesses export an empty ANTHROPIC_API_KEY that would
# otherwise shadow the real key and force mock mode).
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
load_dotenv(override=False)  # also pick up a CWD .env if present (lower priority)

# --------------------------------------------------------------------------- #
# Keys (server-side only — never sent to the browser)
# --------------------------------------------------------------------------- #
APIFY_API_TOKEN: str = os.getenv("APIFY_API_TOKEN", "").strip()
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()

# NICHEFIT_FORCE_MOCK=1 forces both layers into mock mode even when keys are
# present — used by the test suite so it always runs offline and free.
_FORCE_MOCK: bool = os.getenv("NICHEFIT_FORCE_MOCK", "").lower() in ("1", "true", "yes")

# Mock mode also kicks in automatically when a key is missing.
APIFY_MOCK: bool = _FORCE_MOCK or not bool(APIFY_API_TOKEN)
ANTHROPIC_MOCK: bool = _FORCE_MOCK or not bool(ANTHROPIC_API_KEY)

# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
DB_PATH: Path = Path(os.getenv("NICHEFIT_DB", str(ROOT / "nichefit.db")))

# --------------------------------------------------------------------------- #
# Apify
# --------------------------------------------------------------------------- #
APIFY_ACTOR_ID: str = os.getenv(
    "APIFY_ACTOR_ID", "kaitoeasyapi/premium-x-follower-scraper-following-data"
)
APIFY_BASE_URL: str = "https://api.apify.com/v2"

# --------------------------------------------------------------------------- #
# Anthropic / Haiku
# --------------------------------------------------------------------------- #
HAIKU_MODEL: str = os.getenv("HAIKU_MODEL", "claude-haiku-4-5")
SCORER_TEMPERATURE: float = float(os.getenv("SCORER_TEMPERATURE", "0.1"))
SCORER_MAX_TOKENS: int = 1024
SUMMARY_MAX_TOKENS: int = 512

# --------------------------------------------------------------------------- #
# Sampling / concurrency
# --------------------------------------------------------------------------- #
DEFAULT_SAMPLE_SIZE: int = int(os.getenv("DEFAULT_SAMPLE_SIZE", "2000"))
HARD_CAP_SAMPLE_SIZE: int = int(os.getenv("HARD_CAP_SAMPLE_SIZE", "50000"))
DEFAULT_CONCURRENCY: int = int(os.getenv("DEFAULT_CONCURRENCY", "8"))
MAX_RETRIES_PER_FOLLOWER: int = 3

# The Apify actor enforces a minimum of 200 for maxFollowers / maxFollowings.
APIFY_MIN_FOLLOWERS: int = 200

# --------------------------------------------------------------------------- #
# Cost assumptions (all editable). Used only for the pre-run estimate and the
# live "spent this run" counter approximation.
# --------------------------------------------------------------------------- #
APIFY_COST_PER_1000_FOLLOWERS: float = float(
    os.getenv("APIFY_COST_PER_1000_FOLLOWERS", "0.13")
)
# Haiku 4.5 list price (USD per million tokens). Adjust if pricing changes.
HAIKU_INPUT_PRICE_PER_MTOK: float = float(os.getenv("HAIKU_INPUT_PRICE_PER_MTOK", "1.0"))
HAIKU_OUTPUT_PRICE_PER_MTOK: float = float(os.getenv("HAIKU_OUTPUT_PRICE_PER_MTOK", "5.0"))
# Rough token footprint of one scoring call (big rubric + few-shot in, JSON out).
EST_INPUT_TOKENS_PER_FOLLOWER: int = 1800
EST_OUTPUT_TOKENS_PER_FOLLOWER: int = 130

# --------------------------------------------------------------------------- #
# Optional external web lookup (cost-gated). Default OFF for safety.
# --------------------------------------------------------------------------- #
WEB_LOOKUP_ENABLED_DEFAULT: bool = False
WEB_LOOKUP_TOP_PERCENTILE: float = 0.05      # only the top X% by follower_count...
WEB_LOOKUP_MAX_PER_RUN: int = 20             # ...never more than this many...
WEB_LOOKUP_MIN_FOLLOWERS: int = 25000        # ...and only above this follower count.
WEB_LOOKUP_EST_TOKENS: int = 2500            # extra tokens per lookup (web tool is chatty)

# --------------------------------------------------------------------------- #
# Preloaded niches for the dropdown (free-text "custom" is always allowed).
# --------------------------------------------------------------------------- #
PRELOADED_NICHES: list[str] = [
    "tech / SaaS",
    "crypto / web3",
    "fitness / health",
    "finance / investing",
    "beauty / skincare",
    "gaming",
    "marketing / growth",
    "politics",
    "B2B / enterprise",
    "AI / machine learning",
    "real estate",
    "ecommerce / DTC",
    "creator economy",
    "sports",
    "food / cooking",
]


# --------------------------------------------------------------------------- #
# THE RUBRIC — five weighted criteria, each with explicit point bands.
# This object is embedded verbatim into the Haiku prompt, so editing the band
# descriptions here directly changes how the model scores.
# --------------------------------------------------------------------------- #
@dataclass
class Criterion:
    key: str
    label: str
    max_points: int
    bands: list[str]  # human-readable point bands, shown to the model verbatim


@dataclass
class Rubric:
    criteria: list[Criterion] = field(default_factory=list)
    # Tier thresholds on the 0-100 total. (low_inclusive, high_inclusive)
    tiers: dict[str, tuple] = field(
        default_factory=lambda: {
            "A": (80, 100),
            "B": (60, 79),
            "C": (40, 59),
            "D": (0, 39),
        }
    )

    @property
    def max_total(self) -> int:
        return sum(c.max_points for c in self.criteria)

    def tier_for(self, total: int) -> str:
        for tier, (lo, hi) in self.tiers.items():
            if lo <= total <= hi:
                return tier
        return "D"


RUBRIC = Rubric(
    criteria=[
        Criterion(
            key="niche_relevance",
            label="Niche Relevance",
            max_points=35,
            bands=[
                "30-35: a recognized creator / expert / active voice in the niche.",
                "20-29: clearly adjacent or works in a related area.",
                "10-19: tangential or only occasional overlap.",
                "0-9: unrelated to the niche.",
            ],
        ),
        Criterion(
            key="influence_reach",
            label="Influence & Reach",
            max_points=25,
            bands=[
                "22-25: massive reach (100k+ followers, or heavily listed / verified authority).",
                "15-21: strong mid-tier (10k-100k followers).",
                "8-14: micro (1k-10k followers).",
                "0-7: small or inactive (<1k followers).",
            ],
        ),
        Criterion(
            key="authority",
            label="Authority / Expertise",
            max_points=20,
            bands=[
                "16-20: clear credentials, notable affiliations, or named recognition in the field.",
                "10-15: some credibility signals (relevant role/title) but not a marquee name.",
                "4-9: weak or generic credibility signals.",
                "0-3: no authority signals.",
                "If external web context is provided, weight it here.",
            ],
        ),
        Criterion(
            key="engagement_quality",
            label="Engagement Quality",
            max_points=10,
            bands=[
                "8-10: latest tweet shows strong resonance relative to follower count (high likes/RTs per follower).",
                "4-7: moderate engagement for their size.",
                "1-3: weak engagement relative to size.",
                "0: no tweet data or dead engagement.",
            ],
        ),
        Criterion(
            key="authenticity",
            label="Account Authenticity / Activity",
            max_points=10,
            bands=[
                "8-10: aged account, healthy follower/following ratio, consistently active, human.",
                "4-7: real but lightly active, or slightly off ratios.",
                "1-3: thin / dormant / spammy signals.",
                "0: bot or fake signature (egg-like, extreme ratios, zero activity).",
            ],
        ),
    ]
)


@dataclass
class Settings:
    """Per-run knobs the API accepts (with config defaults)."""
    sample_size: int = DEFAULT_SAMPLE_SIZE
    concurrency: int = DEFAULT_CONCURRENCY
    force_refresh: bool = False
    web_lookup: bool = WEB_LOOKUP_ENABLED_DEFAULT


def rubric_as_prompt_text(rubric: Rubric = RUBRIC) -> str:
    """Render the rubric verbatim for embedding in the Haiku system prompt."""
    lines: list[str] = []
    for i, c in enumerate(rubric.criteria, 1):
        lines.append(f"{i}. {c.label} — 0 to {c.max_points} points.")
        for band in c.bands:
            lines.append(f"   - {band}")
    lines.append("")
    lines.append(f"Total = sum of the five criteria (0-{rubric.max_total}).")
    tier_desc = ", ".join(f"{t} = {lo}-{hi}" for t, (lo, hi) in rubric.tiers.items())
    lines.append(f"Tiers: {tier_desc}.")
    return "\n".join(lines)
