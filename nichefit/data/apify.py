"""
Apify data layer — runs the X follower-scraper actor and returns normalized
follower dicts. Falls back to the bundled mock dataset when no token is set.
"""
from __future__ import annotations

import asyncio
import re
from typing import Callable

import httpx

from .. import config
from .mock import expand_mock

# Fields we keep from the actor output (the signals for scoring).
KEEP_FIELDS = [
    "screen_name",
    "name",
    "description",
    "location",
    "url",
    "followers_count",
    "friends_count",
    "listed_count",
    "statuses_count",
    "favourites_count",
    "created_at",
    "verified",
]


def parse_handle(text: str) -> str:
    """Extract a bare screen_name from a URL, @handle, or plain name."""
    text = (text or "").strip()
    if not text:
        return ""
    # URL forms: x.com/foo, twitter.com/foo, with optional query/path.
    m = re.search(r"(?:twitter\.com|x\.com)/(@?[A-Za-z0-9_]+)", text, re.IGNORECASE)
    if m:
        text = m.group(1)
    text = text.lstrip("@")
    text = text.split("/")[0].split("?")[0]
    return text.strip()


def _normalize(item: dict) -> dict | None:
    """Pull the fields we care about (incl. nested status) into a flat dict.

    The actor exposes a few field-name variants across builds, so we read each
    signal leniently and coerce to consistent types.
    """
    screen = item.get("screen_name") or item.get("username") or item.get("userName")
    if not screen:
        return None
    out: dict = {f: item.get(f) for f in KEEP_FIELDS}
    out["screen_name"] = screen
    out["followers_count"] = int(item.get("followers_count") or item.get("followersCount") or 0)
    out["friends_count"] = int(item.get("friends_count") or item.get("friendsCount") or 0)
    out["listed_count"] = int(item.get("listed_count") or item.get("listedCount") or 0)
    out["statuses_count"] = int(item.get("statuses_count") or item.get("statusesCount") or 0)
    out["favourites_count"] = int(item.get("favourites_count") or item.get("favouritesCount") or 0)
    out["verified"] = bool(
        item.get("verified") or item.get("isVerified") or item.get("isBlueVerified")
    )

    status = item.get("status") or item.get("latest_tweet") or None
    if isinstance(status, dict):
        out["status"] = {
            "full_text": status.get("full_text") or status.get("text") or "",
            "retweet_count": int(status.get("retweet_count") or status.get("retweetCount") or 0),
            "favorite_count": int(status.get("favorite_count") or status.get("favoriteCount") or 0),
        }
    else:
        out["status"] = None
    return out


def _dedupe(followers: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for f in followers:
        sn = (f.get("screen_name") or "").lower()
        if sn and sn not in seen:
            seen.add(sn)
            out.append(f)
    return out


async def fetch_followers(
    handle: str,
    sample_size: int,
    progress: Callable[[str], None] | None = None,
) -> list[dict]:
    """Run the actor and return up to `sample_size` normalized, deduped followers."""
    def emit(msg: str) -> None:
        if progress:
            progress(msg)

    if config.APIFY_MOCK:
        emit("Mock mode: serving bundled sample followers (no Apify spend).")
        await asyncio.sleep(0.4)
        return _dedupe(expand_mock(min(sample_size, 200)))

    token = config.APIFY_API_TOKEN
    actor = config.APIFY_ACTOR_ID.replace("/", "~")  # API path form
    run_url = f"{config.APIFY_BASE_URL}/acts/{actor}/runs?token={token}"

    # Input shape per the actor's published input schema. Required fields:
    # maxFollowers, maxFollowings, getFollowers, getFollowing. The actor enforces
    # both maxima >= 200, so request at least that and trim back to sample_size.
    apify_max = max(config.APIFY_MIN_FOLLOWERS, sample_size)
    run_input = {
        "user_names": [handle],
        "user_ids": [],
        "maxFollowers": apify_max,
        "maxFollowings": config.APIFY_MIN_FOLLOWERS,  # required >= 200 even when off
        "getFollowers": True,
        "getFollowing": False,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        emit(f"Starting Apify actor for @{handle}…")
        r = await client.post(run_url, json=run_input)
        r.raise_for_status()
        run = r.json()["data"]
        run_id = run["id"]
        dataset_id = run["defaultDatasetId"]

        # Poll until the run finishes.
        status_url = f"{config.APIFY_BASE_URL}/actor-runs/{run_id}?token={token}"
        for _ in range(600):  # up to ~20 min at 2s
            await asyncio.sleep(2.0)
            s = await client.get(status_url)
            s.raise_for_status()
            st = s.json()["data"]["status"]
            emit(f"Apify run status: {st}")
            if st in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                if st != "SUCCEEDED":
                    raise RuntimeError(f"Apify run ended with status {st}")
                break
        else:
            raise RuntimeError("Apify run timed out while polling.")

        # Page through the dataset.
        items: list[dict] = []
        offset = 0
        page = 1000
        ds_url = f"{config.APIFY_BASE_URL}/datasets/{dataset_id}/items?token={token}"
        while len(items) < sample_size:
            resp = await client.get(
                ds_url, params={"offset": offset, "limit": page, "clean": "true"}
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            items.extend(batch)
            offset += len(batch)
            emit(f"Fetched {len(items)} follower records…")
            if len(batch) < page:
                break

    normalized = [n for n in (_normalize(i) for i in items) if n]
    return _dedupe(normalized)[:sample_size]
