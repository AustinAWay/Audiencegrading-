"""
Prompt construction for the Haiku scorer.

Follows the prompt-design contract from the spec:
  - a system prompt that sets the evaluator role for the chosen niche,
  - the full rubric (with point bands) embedded verbatim,
  - the follower's data wrapped in labelled XML tags,
  - two few-shot worked examples (one high-value, one low-value),
  - brief chain-of-thought in a `reasoning` field, then strict JSON.

Keeping the prompt text here (separate from the async scoring mechanics in
scorer.py) makes the prompt engineering easy to read and tune in one place.
"""
from __future__ import annotations

from .. import config


def system_prompt(niche: str) -> str:
    return (
        f"You are an expert evaluator assessing whether an X (Twitter) user is a "
        f"high-value member of the \"{niche}\" audience.\n\n"
        "Score the user against this rubric. Follow the point bands exactly so "
        "scoring is consistent across users.\n\n"
        f"{config.rubric_as_prompt_text()}\n\n"
        "Rules:\n"
        "- Score only on the evidence provided. If fields are missing, score on "
        "what is available and lower your `confidence`.\n"
        "- `total` MUST equal the sum of the five criteria.\n"
        "- `tier` MUST follow the tier thresholds above.\n"
        "- Reason briefly first, then output the JSON.\n"
        "- Output STRICT JSON only, no prose around it, matching this schema:\n"
        '{"niche_relevance": int, "influence_reach": int, "authority": int, '
        '"engagement_quality": int, "authenticity": int, "total": int, '
        '"tier": "A|B|C|D", "confidence": 0.0-1.0, "reasoning": "one or two sentences"}'
    )


# Two worked examples, each showing the exact JSON output the model should emit.
_FEWSHOT_HIGH = (
    "<follower>\n"
    "<screen_name>dharmesh</screen_name>\n"
    "<name>Dharmesh Shah</name>\n"
    "<bio>Founder/CTO @HubSpot. I build SaaS and software for B2B marketers.</bio>\n"
    "<location>Boston, MA</location>\n"
    "<links>https://hubspot.com</links>\n"
    "<followers_count>480000</followers_count>\n"
    "<friends_count>2500</friends_count>\n"
    "<listed_count>7800</listed_count>\n"
    "<statuses_count>28000</statuses_count>\n"
    "<favourites_count>12000</favourites_count>\n"
    "<created_at>Wed Jun 11 09:30:00 +0000 2008</created_at>\n"
    "<verified>true</verified>\n"
    "<latest_tweet likes=\"5200\" retweets=\"410\">The best SaaS growth lever nobody "
    "talks about: making your free tier genuinely useful.</latest_tweet>\n"
    "</follower>"
)
_FEWSHOT_HIGH_OUT = (
    '{"niche_relevance": 34, "influence_reach": 24, "authority": 19, '
    '"engagement_quality": 9, "authenticity": 10, "total": 96, "tier": "A", '
    '"confidence": 0.95, "reasoning": "Founder/CTO of HubSpot — a marquee SaaS '
    'authority with massive verified reach, strong per-follower engagement, and a '
    'long active account."}'
)

_FEWSHOT_LOW = (
    "<follower>\n"
    "<screen_name>promo_bot_9931</screen_name>\n"
    "<name>🔥 FOLLOW BACK 🔥</name>\n"
    "<bio>Follow 4 follow! DM for promo. Crypto signals 100% accurate!!!</bio>\n"
    "<location></location>\n"
    "<links>http://sketchy.link/promo</links>\n"
    "<followers_count>1200</followers_count>\n"
    "<friends_count>4900</friends_count>\n"
    "<listed_count>1</listed_count>\n"
    "<statuses_count>88000</statuses_count>\n"
    "<favourites_count>3</favourites_count>\n"
    "<created_at>Wed Jan 03 01:00:00 +0000 2024</created_at>\n"
    "<verified>false</verified>\n"
    "<latest_tweet likes=\"0\" retweets=\"0\">DM ME FOR PROMO follow back guaranteed</latest_tweet>\n"
    "</follower>"
)
_FEWSHOT_LOW_OUT = (
    '{"niche_relevance": 3, "influence_reach": 4, "authority": 0, '
    '"engagement_quality": 0, "authenticity": 0, "total": 7, "tier": "D", '
    '"confidence": 0.9, "reasoning": "Spam/bot signature: follow-for-follow bio, '
    'extreme following ratio, 88k tweets with near-zero engagement, brand-new '
    'account — not a real niche member."}'
)


def _bool(v) -> str:
    return "true" if v else "false"


def follower_to_xml(f: dict) -> str:
    """Render a follower as the labelled XML block the model scores against."""
    status = f.get("status") or {}
    tweet = (status.get("full_text") or "").replace("\n", " ").strip()
    likes = status.get("favorite_count", 0)
    rts = status.get("retweet_count", 0)
    tweet_line = (
        f'<latest_tweet likes="{likes}" retweets="{rts}">{tweet}</latest_tweet>'
        if tweet
        else "<latest_tweet>none available</latest_tweet>"
    )
    return (
        "<follower>\n"
        f"<screen_name>{f.get('screen_name','')}</screen_name>\n"
        f"<name>{f.get('name','') or ''}</name>\n"
        f"<bio>{f.get('description','') or ''}</bio>\n"
        f"<location>{f.get('location','') or ''}</location>\n"
        f"<links>{f.get('url','') or ''}</links>\n"
        f"<followers_count>{f.get('followers_count',0)}</followers_count>\n"
        f"<friends_count>{f.get('friends_count',0)}</friends_count>\n"
        f"<listed_count>{f.get('listed_count',0)}</listed_count>\n"
        f"<statuses_count>{f.get('statuses_count',0)}</statuses_count>\n"
        f"<favourites_count>{f.get('favourites_count',0)}</favourites_count>\n"
        f"<created_at>{f.get('created_at','') or ''}</created_at>\n"
        f"<verified>{_bool(f.get('verified'))}</verified>\n"
        f"{tweet_line}\n"
        "</follower>"
    )


def user_prompt(f: dict, web_context: str | None = None) -> str:
    """Build the user-turn prompt: few-shot examples + the follower to score."""
    parts = [
        "Here are two worked examples of the expected output.",
        "\nExample A (high-value):",
        _FEWSHOT_HIGH,
        "Expected JSON:",
        _FEWSHOT_HIGH_OUT,
        "\nExample B (low-value):",
        _FEWSHOT_LOW,
        "Expected JSON:",
        _FEWSHOT_LOW_OUT,
        "\nNow score this follower:",
        follower_to_xml(f),
    ]
    if web_context:
        parts.append(
            "\nExternal web context about this person (use for the authority "
            f"score):\n<web_context>{web_context}</web_context>"
        )
    parts.append("\nReason briefly, then output the strict JSON object.")
    return "\n".join(parts)
