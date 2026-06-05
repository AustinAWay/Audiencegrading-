"""
Scoring engine — one Haiku "sub-agent" call per follower.

The Scorer owns the async mechanics: bounded concurrency via an
asyncio.Semaphore, retry with exponential backoff, JSON extraction +
validation, and token accounting for the live spend counter. Prompt text lives
in prompts.py; the rubric lives in config.py.

A follower is skipped after N failed attempts rather than failing the whole run.
When ANTHROPIC_API_KEY is missing, a deterministic heuristic stands in so the
full flow works with zero spend.
"""
from __future__ import annotations

import asyncio
import json
import math
import re

from .. import config
from . import prompts

try:
    from anthropic import AsyncAnthropic
except Exception:  # pragma: no cover - SDK optional in pure-mock installs
    AsyncAnthropic = None  # type: ignore

_CRITERIA_KEYS = [c.key for c in config.RUBRIC.criteria]


# --------------------------------------------------------------------------- #
# JSON extraction / validation
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> dict | None:
    """Return the last valid JSON object in the text (the model may reason first).

    Scans every '{' and tries to decode a JSON value there, keeping the last
    one that parses. Robust to prose — and to braces — appearing before the
    final object.
    """
    decoder = json.JSONDecoder()
    found: dict | None = None
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(text[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                found = obj
    return found


def _coerce_and_validate(raw: dict, f: dict) -> dict:
    """Clamp each criterion to its band, then recompute total + tier authoritatively.

    This guarantees the returned record is always internally consistent
    regardless of what the model emitted.
    """
    out: dict = {}
    for c in config.RUBRIC.criteria:
        try:
            v = int(round(float(raw.get(c.key, 0))))
        except Exception:
            v = 0
        out[c.key] = max(0, min(c.max_points, v))
    out["total"] = sum(out[k] for k in _CRITERIA_KEYS)
    out["tier"] = config.RUBRIC.tier_for(out["total"])
    try:
        conf = float(raw.get("confidence", 0.5))
    except Exception:
        conf = 0.5
    out["confidence"] = max(0.0, min(1.0, conf))
    out["reasoning"] = str(raw.get("reasoning", ""))[:400]
    out["screen_name"] = f.get("screen_name", "")
    out["name"] = f.get("name", "")
    out["followers_count"] = f.get("followers_count", 0)
    out["bot"] = False
    return out


# --------------------------------------------------------------------------- #
# Free bot / junk pre-filter (no LLM, no web research)
# --------------------------------------------------------------------------- #
def is_junk(f: dict) -> bool:
    """Deterministically flag an obvious bot / empty / spam account.

    Deliberately conservative: verified accounts are never flagged, and a real
    account is only flagged when it has no bio AND almost no activity, or shows an
    explicit spam signature. This is bot *detection*, not influence scoring — it
    is the one place follower-adjacent activity signals are used.
    """
    if f.get("verified"):
        return False
    bio = (f.get("description") or "").strip()
    name = f.get("name") or ""
    tweet = (f.get("status") or {}).get("full_text") or ""
    text = f"{bio} {name} {tweet}".lower()
    if any(p in text for p in config.BOT_SPAM_PHRASES):
        return True
    statuses = f.get("statuses_count", 0) or 0
    has_tweet = bool((f.get("status") or {}).get("full_text"))
    # Empty bio and essentially no activity -> treat as bot / dormant.
    return not bio and statuses < config.BOT_MIN_STATUSES and not has_tweet


def junk_score(f: dict) -> dict:
    """A free 'fake' score for a flagged account — tier D, no spend."""
    out = _coerce_and_validate(dict.fromkeys(_CRITERIA_KEYS, 0), f)
    out["confidence"] = 0.9
    out["reasoning"] = "Flagged by the pre-filter as a bot / inactive / spam account (no LLM call)."
    out["bot"] = True
    return out


# --------------------------------------------------------------------------- #
# Mock heuristic scorer (no ANTHROPIC_API_KEY)
# --------------------------------------------------------------------------- #
def heuristic_score(f: dict, niche: str) -> dict:
    """Deterministic stand-in used in mock mode — rough but plausible."""
    bio = ((f.get("description") or "") + " " + (f.get("name") or "")).lower()
    tweet = ((f.get("status") or {}).get("full_text") or "").lower()
    text = bio + " " + tweet
    niche_words = [w for w in re.split(r"[^a-z0-9]+", niche.lower()) if len(w) > 2]
    hits = sum(1 for w in niche_words if w in text)
    rel = min(35, 8 + hits * 12) if niche_words else 12
    if any(s in text for s in ("follow back", "promo", "f4f", "100% accurate")):
        rel = min(rel, 4)

    fc = f.get("followers_count", 0) or 0
    reach = min(25, int(math.log10(fc + 1) / 6 * 25))
    if f.get("verified"):
        reach = min(25, reach + 3)

    auth = 0
    for kw in (
        "founder", "ceo", "cto", "phd", "engineer", "lead", "head",
        "author", "investor", "coach", "pm", "trainer",
    ):
        if kw in bio:
            auth = max(auth, 12)
    if f.get("verified"):
        auth = max(auth, 14)
    auth = min(20, auth)

    status = f.get("status") or {}
    eng_raw = (status.get("favorite_count", 0) + status.get("retweet_count", 0)) / max(1, fc)
    eng = min(10, int(eng_raw * 4000))

    friends = f.get("friends_count", 1) or 1
    ratio = fc / max(1, friends)
    statuses = f.get("statuses_count", 0) or 0
    authn = 6
    if ratio < 0.2 and statuses > 20000:
        authn = 1  # spammy
    elif fc < 100 and statuses < 30:
        authn = 3  # dormant
    elif ratio > 1 and statuses > 500:
        authn = 9
    authn = min(10, authn)

    raw = {
        "niche_relevance": rel,
        "influence_reach": reach,
        "authority": auth,
        "engagement_quality": eng,
        "authenticity": authn,
        "confidence": 0.55,
        "reasoning": "Heuristic mock score (no ANTHROPIC_API_KEY set).",
    }
    return _coerce_and_validate(raw, f)


# --------------------------------------------------------------------------- #
# Live Haiku scorer
# --------------------------------------------------------------------------- #
class Scorer:
    """Scores followers concurrently with Claude Haiku (or the heuristic fallback)."""

    def __init__(self, niche: str, concurrency: int):
        self.niche = niche
        self.sem = asyncio.Semaphore(max(1, concurrency))
        self.client = (
            AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
            if (not config.ANTHROPIC_MOCK and AsyncAnthropic)
            else None
        )
        # token accounting for the live spend counter
        self.input_tokens = 0
        self.output_tokens = 0

    async def _call(self, system: str, user: str, stricter: bool = False) -> dict | None:
        if stricter:
            user += (
                "\n\nIMPORTANT: Your previous reply was not valid JSON. Respond with "
                "ONLY the JSON object, nothing else."
            )
        msg = await self.client.messages.create(
            model=config.HAIKU_MODEL,
            max_tokens=config.SCORER_MAX_TOKENS,
            temperature=config.SCORER_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if msg.usage:
            self.input_tokens += msg.usage.input_tokens
            self.output_tokens += msg.usage.output_tokens
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return _extract_json(text)

    async def score_one(self, f: dict, web_context: str | None = None) -> dict | None:
        """Score a single follower. Returns None if it fails after all retries."""
        if self.client is None:
            return heuristic_score(f, self.niche)

        system = prompts.system_prompt(self.niche)
        user = prompts.user_prompt(f, web_context)
        async with self.sem:
            for attempt in range(config.MAX_RETRIES_PER_FOLLOWER):
                try:
                    raw = await self._call(system, user, stricter=(attempt > 0))
                    if raw is None:
                        continue  # malformed JSON -> retry stricter
                    return _coerce_and_validate(raw, f)
                except Exception:
                    # exponential backoff on errors / rate limits
                    await asyncio.sleep(min(8.0, 0.8 * (2 ** attempt)))
            return None  # skip this follower after N failures

    @property
    def spend_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * config.HAIKU_INPUT_PRICE_PER_MTOK
            + self.output_tokens / 1_000_000 * config.HAIKU_OUTPUT_PRICE_PER_MTOK
        )

    async def web_context(self, f: dict) -> str | None:
        """Best-effort web research on who a follower actually is.

        Drives the real-world influence and authority scores — the whole point of
        the rubric is to value people by their real stature, not follower count.
        Skips gracefully (returns None) if the web_search tool isn't available on
        the account.
        """
        if self.client is None:
            return None
        name = f.get("name") or f.get("screen_name")
        try:
            msg = await self.client.messages.create(
                model=config.HAIKU_MODEL,
                max_tokens=300,
                tools=[{"type": "web_search_20250305", "name": "web_search",
                        "max_uses": config.WEB_SEARCH_MAX_USES}],
                messages=[{
                    "role": "user",
                    "content": (
                        f"Research who this X (Twitter) user is and what they post about. "
                        f"Name: {name}. Handle: @{f.get('screen_name')}. "
                        f"Bio: \"{f.get('description','')}\". Search the web (including "
                        "their recent tweets/posts if findable). In 2-4 sentences summarize: "
                        "(1) their real-world influence and authority — founder/executive "
                        "roles and company size, investments, wealth/billionaire status, "
                        "public prominence, recognized expertise; and (2) the main themes "
                        "of their recent posts. If you cannot confidently identify them, "
                        "say so plainly."
                    ),
                }],
            )
            if msg.usage:
                self.input_tokens += msg.usage.input_tokens
                self.output_tokens += msg.usage.output_tokens
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            return text.strip() or None
        except Exception:
            return None

    async def write_summary(self, handle: str, agg: dict) -> str:
        """Final Haiku call: a 3-4 sentence plain-English audience summary."""
        bot_rate = agg.get("bot_rate", 0)
        if self.client is None:
            return (
                f"[Mock summary] @{handle}'s real audience scored "
                f"{agg['audience_score']}/100 for the \"{self.niche}\" niche, with "
                f"~{bot_rate}% of the pool flagged as bots/inactive. Tier mix: "
                f"{agg['tiers']}. Add ANTHROPIC_API_KEY for a real Claude-written summary."
            )
        top = ", ".join(f"@{t['screen_name']}" for t in agg["top_followers"][:8])
        prompt = (
            f"You estimated @{handle}'s audience fit for the \"{self.niche}\" niche "
            f"from a random sample of {agg.get('analyzed', agg['scored'])} real "
            f"followers (out of a pool of {agg.get('pool_size', '?')}). About "
            f"{bot_rate}% of the pool were flagged as bots/inactive. The real "
            f"followers scored {agg['audience_score']}/100 with tier distribution "
            f"{agg['tiers']}. Notable high-value followers: {top}. Write a 3-4 "
            "sentence plain-English summary of this audience, its fit for the niche, "
            "and what the bot rate implies. Be specific and candid."
        )
        try:
            msg = await self.client.messages.create(
                model=config.HAIKU_MODEL,
                max_tokens=config.SUMMARY_MAX_TOKENS,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
            if msg.usage:
                self.input_tokens += msg.usage.input_tokens
                self.output_tokens += msg.usage.output_tokens
            return "".join(
                b.text for b in msg.content if getattr(b, "type", "") == "text"
            ).strip()
        except Exception:
            return (
                f"@{handle}'s sampled audience scored {agg['audience_score']}/100 for "
                f"the \"{self.niche}\" niche (summary generation failed)."
            )
