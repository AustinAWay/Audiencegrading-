"""
NicheFit configuration — the tunable core.

Everything you'd want to adjust lives here: the scoring rubric (weights + point
bands), tier thresholds, concurrency/sampling defaults, cost assumptions, and
the optional web-lookup gate. Edit this file to retune the engine; environment
variables (see .env.example) override the numeric defaults.

DEMO NOTE: these defaults (especially the rubric weights/bands and the bot-filter
thresholds) are illustrative starting points, not validated values. Expect to
fine-tune them against real data before trusting the scores.
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
# Tweet scraper — used to pull a single person's profile + recent tweets (the
# tweet objects embed the author's full profile: bio, name, counts, verified).
APIFY_TWEET_ACTOR: str = os.getenv(
    "APIFY_TWEET_ACTOR", "kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest"
)
PERSON_TWEETS: int = int(os.getenv("PERSON_TWEETS", "20"))
APIFY_TWEET_COST_PER_1000: float = float(os.getenv("APIFY_TWEET_COST_PER_1000", "0.25"))
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
# Two knobs keep cost flat regardless of account size:
#   POOL  — how many followers we cheaply scrape and bot-filter (Apify is ~$0.13
#           per 1,000, so a large pool is cheap and gives an accurate bot rate).
#   SAMPLE — the cap on how many *real* (non-bot) followers we then deeply analyze
#            with web research + Haiku (the expensive part). A random sample of a
#            few hundred is statistically plenty to estimate the whole audience.
#
# IMPORTANT: the Apify actor returns followers newest-first, and recent followers
# are overwhelmingly bots/empty. Real, high-reach followers are deeper in the
# list, so the pool ("scan depth") must be large enough to reach them — ideally
# >= the account's total follower count for an accurate "top by reach".
DEFAULT_POOL_SIZE: int = int(os.getenv("DEFAULT_POOL_SIZE", "3000"))
DEFAULT_SAMPLE_SIZE: int = int(os.getenv("DEFAULT_SAMPLE_SIZE", "100"))
HARD_CAP_SAMPLE_SIZE: int = int(os.getenv("HARD_CAP_SAMPLE_SIZE", "50000"))
DEFAULT_CONCURRENCY: int = int(os.getenv("DEFAULT_CONCURRENCY", "8"))
MAX_RETRIES_PER_FOLLOWER: int = 3

# The Apify actor enforces a minimum of 200 for maxFollowers / maxFollowings.
APIFY_MIN_FOLLOWERS: int = 200

# --------------------------------------------------------------------------- #
# Bot / junk pre-filter (free — no LLM, no web research).
# Obvious bots / empty / spam accounts are flagged from the raw data alone and
# counted as "fake" (tier D) without spending anything. Kept deliberately
# conservative so a real (if sparse) person is unlikely to be mislabelled;
# verified accounts are never flagged.
# --------------------------------------------------------------------------- #
BOT_FILTER_ENABLED_DEFAULT: bool = True
BOT_MIN_STATUSES: int = 3              # empty bio + fewer tweets than this -> junk
BOT_SPAM_PHRASES: list[str] = [
    "follow back", "followback", "f4f", "follow 4 follow", "follow for follow",
    "dm for promo", "dm for promotion", "promo code", "100% accurate",
    "free followers", "crypto signals", "onlyfans", "link in bio for free",
]
# For the pre-run estimate only: assumed fraction of the pool that survives the
# bot filter and gets deeply analyzed (the rest are free).
EST_ANALYZABLE_FRACTION: float = float(os.getenv("EST_ANALYZABLE_FRACTION", "0.5"))

# --------------------------------------------------------------------------- #
# One-click run modes (exposed as buttons in the UI).
#   custom — use the form's own settings (full control).
#   full   — cheap whole-account estimate: large pool, bot-filter free, score a
#            random sample of the real ones WITHOUT web research, then project the
#            bot rate + real-audience mix across the entire account.
#   top    — deep-dive the highest-reach followers: pick the top-N followers by
#            their own follower count and analyze them WITH web research.
# --------------------------------------------------------------------------- #
# Note: pool_size ("scan depth") is taken from the request so the user can scan
# deep enough to cover their account; presets only set sample/research/selection.
FULL_MODE_SAMPLE: int = 120
TOP_MODE_SAMPLE: int = 100   # the top 100 followers by reach

MODE_PRESETS: dict = {
    "full": {"sample_size": FULL_MODE_SAMPLE, "web_lookup": False, "skip_bots": True, "selection": "random"},
    "top": {"sample_size": TOP_MODE_SAMPLE, "web_lookup": True, "skip_bots": True, "selection": "top"},
}

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
#
# When on, the engine researches EVERY follower being scored (not gated by
# follower count) so the model can judge real-world influence from who the
# person actually is. This costs an extra search + tokens per follower.
WEB_LOOKUP_ENABLED_DEFAULT: bool = True
WEB_SEARCH_MAX_USES: int = 1                 # searches per follower (cost control)
# Realistic token footprint of a research call: the web_search results are fed
# back as input tokens, so this is much larger than a plain scoring call.
WEB_LOOKUP_EST_TOKENS: int = 4000            # extra tokens per researched follower
WEB_SEARCH_COST_PER_CALL: float = 0.01       # Anthropic web_search ≈ $10 / 1000 searches

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


# The rubric measures how valuable each follower is as a member of THIS niche's
# audience. "Value" is driven by real-world influence — who the person actually
# is (founder, executive, investor, billionaire, public figure, recognized
# authority) — judged from web research, NOT from follower count. Major
# real-world influence makes someone a valuable audience member even when they
# are not topically in the niche.
#
# NOTE: the keys are kept stable (niche_relevance, influence_reach, authority,
# engagement_quality, authenticity) so stored scores and the UI keep working —
# only the meaning, weights, and bands change.
RUBRIC = Rubric(
    criteria=[
        Criterion(
            key="niche_relevance",
            label="Niche Relevance",
            max_points=30,
            bands=[
                "24-30: directly works in, builds in, or is a recognized voice of the niche.",
                "16-23: clearly adjacent or active in a closely related area.",
                "7-15: tangential or only occasional overlap.",
                "0-6: no connection to the niche.",
            ],
        ),
        Criterion(
            key="influence_reach",
            label="Real-World Influence",
            max_points=35,
            bands=[
                "Judge from who the person actually is (use the web research provided). "
                "Do NOT use follower count.",
                "28-35: a major real-world figure — billionaire, founder/CEO of a "
                "significant company, leading investor, senior official, or widely "
                "recognized public figure whose attention carries real weight.",
                "19-27: notable influence — established founder/executive, recognized "
                "professional, or someone with real institutional or industry sway.",
                "9-18: some genuine influence — mid-level leadership, a niche-known "
                "figure, or an emerging authority.",
                "0-8: a private individual with no notable real-world influence.",
                "A major figure from OUTSIDE the niche still scores high here — their "
                "influence is valuable to the audience regardless of topic. Influence "
                "that sits inside or adjacent to the niche scores at the top of its band.",
            ],
        ),
        Criterion(
            key="authority",
            label="Authority / Expertise",
            max_points=20,
            bands=[
                "Use the web research to assess credibility.",
                "16-20: clear credentials, notable affiliations, or a recognized track record.",
                "10-15: a solid relevant role/title or demonstrated expertise.",
                "4-9: weak or generic credibility signals.",
                "0-3: no authority signals.",
            ],
        ),
        Criterion(
            key="engagement_quality",
            label="Activity",
            max_points=8,
            bands=[
                "How active/established the account is, from statuses_count and "
                "favourites_count (we do not have their tweet text).",
                "7-8: highly active (many thousands of posts), clearly engaged.",
                "4-6: moderately active.",
                "1-3: light activity.",
                "0: essentially inactive.",
            ],
        ),
        Criterion(
            key="authenticity",
            label="Authenticity / Activity",
            max_points=7,
            bands=[
                "Real, active human — from account age and activity, NOT audience size.",
                "6-7: aged, consistently active, clearly human.",
                "3-5: real but lightly active.",
                "1-2: thin or dormant.",
                "0: bot / spam / fake signature.",
            ],
        ),
    ]
)


@dataclass
class Settings:
    """Per-run knobs the API accepts (with config defaults)."""
    sample_size: int = DEFAULT_SAMPLE_SIZE          # max real followers to deeply analyze
    pool_size: int = DEFAULT_POOL_SIZE              # followers to scrape + bot-filter
    concurrency: int = DEFAULT_CONCURRENCY
    force_refresh: bool = False
    web_lookup: bool = WEB_LOOKUP_ENABLED_DEFAULT
    skip_bots: bool = BOT_FILTER_ENABLED_DEFAULT
    selection: str = "random"                       # "random" (sample) or "top" (by reach)


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
