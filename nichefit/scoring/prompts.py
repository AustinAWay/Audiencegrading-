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
        "- Use the web research provided (if any) to judge real-world influence "
        "and authority — who this person actually is.\n"
        "- Judge influence by WHO THE PERSON IS, never by follower count.\n"
        "- A major real-world figure (founder, executive, investor, billionaire, "
        "public figure) is a valuable audience member even if they are not in the "
        "niche — score their influence on its merits.\n"
        "- If evidence is thin, score on what you have and lower your `confidence`.\n"
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
    "<friends_count>2500</friends_count>\n"
    "<statuses_count>28000</statuses_count>\n"
    "<favourites_count>12000</favourites_count>\n"
    "<created_at>Wed Jun 11 09:30:00 +0000 2008</created_at>\n"
    "<verified>true</verified>\n"
    "</follower>\n"
    "<web_context>Dharmesh Shah is the co-founder and CTO of HubSpot, a public "
    "company worth tens of billions; a prominent SaaS angel investor and author.</web_context>"
)
_FEWSHOT_HIGH_OUT = (
    '{"niche_relevance": 28, "influence_reach": 31, "authority": 19, '
    '"engagement_quality": 7, "authenticity": 7, "total": 92, "tier": "A", '
    '"confidence": 0.95, "reasoning": "Co-founder/CTO of HubSpot, a major SaaS '
    'company — high real-world influence and authority, directly in the niche, '
    'with a long active account."}'
)

_FEWSHOT_LOW = (
    "<follower>\n"
    "<screen_name>promo_bot_9931</screen_name>\n"
    "<name>🔥 FOLLOW BACK 🔥</name>\n"
    "<bio>Follow 4 follow! DM for promo. Crypto signals 100% accurate!!!</bio>\n"
    "<location></location>\n"
    "<links>http://sketchy.link/promo</links>\n"
    "<friends_count>4900</friends_count>\n"
    "<statuses_count>88000</statuses_count>\n"
    "<favourites_count>3</favourites_count>\n"
    "<created_at>Wed Jan 03 01:00:00 +0000 2024</created_at>\n"
    "<verified>false</verified>\n"
    "</follower>\n"
    "<web_context>No information found — appears to be an anonymous promo/spam "
    "account.</web_context>"
)
_FEWSHOT_LOW_OUT = (
    '{"niche_relevance": 2, "influence_reach": 1, "authority": 0, '
    '"engagement_quality": 0, "authenticity": 0, "total": 3, "tier": "D", '
    '"confidence": 0.9, "reasoning": "Spam/bot signature — follow-for-follow promo '
    'bio, brand-new account, near-zero real activity, and no identifiable real-world '
    'influence."}'
)


def _bool(v) -> str:
    return "true" if v else "false"


def follower_to_xml(f: dict) -> str:
    """Render a follower as the labelled XML block the model scores against.

    Note: this data source does not include the follower's tweets, so there is no
    tweet text — the model judges from the profile + web research + activity counts.
    """
    return (
        "<follower>\n"
        f"<screen_name>{f.get('screen_name','')}</screen_name>\n"
        f"<name>{f.get('name','') or ''}</name>\n"
        f"<bio>{f.get('description','') or ''}</bio>\n"
        f"<location>{f.get('location','') or ''}</location>\n"
        f"<links>{f.get('url','') or ''}</links>\n"
        # follower_count / listed_count are intentionally omitted: influence is
        # judged from who the person is (web research), not audience size.
        f"<friends_count>{f.get('friends_count',0)}</friends_count>\n"
        f"<statuses_count>{f.get('statuses_count',0)}</statuses_count>\n"
        f"<favourites_count>{f.get('favourites_count',0)}</favourites_count>\n"
        f"<created_at>{f.get('created_at','') or ''}</created_at>\n"
        f"<verified>{_bool(f.get('verified'))}</verified>\n"
        f"{_tweets_block(f.get('tweets'))}"
        "</follower>"
    )


def batch_prompt(followers: list) -> str:
    """Prompt to grade MANY followers in one call (cheap, no web research).

    Returns instructions for a JSON array, one object per follower, each echoing
    its screen_name so results can be matched back.
    """
    blocks = "\n".join(follower_to_xml(f) for f in followers)
    return (
        f"Grade EACH of the following {len(followers)} X followers against the rubric. "
        "No web research is available — judge from the bio and activity counts; when "
        "real-world influence/authority can't be established from the profile, score "
        "those low and lower confidence (don't invent).\n\n"
        f"<followers>\n{blocks}\n</followers>\n\n"
        "Return ONLY a JSON array with one object per follower, in the same order, and "
        "include each follower's exact screen_name. Each object uses the schema:\n"
        '{"screen_name": str, "niche_relevance": int, "influence_reach": int, '
        '"authority": int, "engagement_quality": int, "authenticity": int, '
        '"total": int, "tier": "A|B|C|D", "confidence": 0.0-1.0, "reasoning": "short"}'
    )


def _tweets_block(tweets) -> str:
    if not tweets:
        return ""
    lines = "\n".join(f"- {t}" for t in tweets[:12])
    return f"<recent_tweets>\n{lines}\n</recent_tweets>\n"


def user_prompt(f: dict, web_context: str | None = None, note: str | None = None) -> str:
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
            "\nWeb research about this person (use it to judge real-world influence "
            f"and authority):\n<web_context>{web_context}</web_context>"
        )
    if note:
        parts.append(f"\n{note}")
    parts.append("\nReason briefly, then output the strict JSON object.")
    return "\n".join(parts)
