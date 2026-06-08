"""
SQLite caches so re-runs don't re-pay Apify or Anthropic.

Three tables:
  - followers : raw scraped follower rows, keyed by (handle, screen_name)
  - scores    : per-follower Haiku scores, keyed by (handle, niche, screen_name)
  - analyses  : saved run summaries, keyed by analysis id
"""
from __future__ import annotations

import json
import sqlite3
import time

from .. import config

DB_PATH = config.DB_PATH


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS followers (
                handle      TEXT NOT NULL,
                screen_name TEXT NOT NULL,
                data        TEXT NOT NULL,
                fetched_at  REAL NOT NULL,
                PRIMARY KEY (handle, screen_name)
            );

            CREATE TABLE IF NOT EXISTS scores (
                handle      TEXT NOT NULL,
                niche       TEXT NOT NULL,
                screen_name TEXT NOT NULL,
                score       TEXT NOT NULL,
                scored_at   REAL NOT NULL,
                PRIMARY KEY (handle, niche, screen_name)
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id          TEXT PRIMARY KEY,
                handle      TEXT NOT NULL,
                niche       TEXT NOT NULL,
                result      TEXT NOT NULL,
                created_at  REAL NOT NULL
            );
            """
        )


# --------------------------------------------------------------------------- #
# Followers
# --------------------------------------------------------------------------- #
def get_cached_followers(handle: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT data FROM followers WHERE handle = ?", (handle.lower(),)
        ).fetchall()
    return [json.loads(r["data"]) for r in rows]


def save_followers(handle: str, followers: list[dict]) -> None:
    now = time.time()
    handle = handle.lower()
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO followers (handle, screen_name, data, fetched_at) "
            "VALUES (?, ?, ?, ?)",
            [
                (handle, (f.get("screen_name") or "").lower(), json.dumps(f), now)
                for f in followers
                if f.get("screen_name")
            ],
        )


def clear_followers(handle: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM followers WHERE handle = ?", (handle.lower(),))


# --------------------------------------------------------------------------- #
# Scores
# --------------------------------------------------------------------------- #
def get_cached_scores(handle: str, niche: str) -> dict[str, dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT screen_name, score FROM scores WHERE handle = ? AND niche = ?",
            (handle.lower(), niche.lower()),
        ).fetchall()
    return {r["screen_name"]: json.loads(r["score"]) for r in rows}


def save_score(handle: str, niche: str, screen_name: str, score: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scores (handle, niche, screen_name, score, scored_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (handle.lower(), niche.lower(), screen_name.lower(), json.dumps(score), time.time()),
        )


def clear_scores(handle: str, niche: str) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM scores WHERE handle = ? AND niche = ?",
            (handle.lower(), niche.lower()),
        )


# --------------------------------------------------------------------------- #
# Saved analyses
# --------------------------------------------------------------------------- #
def save_analysis(analysis_id: str, handle: str, niche: str, result: dict) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analyses (id, handle, niche, result, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (analysis_id, handle.lower(), niche, json.dumps(result), time.time()),
        )


def list_analyses(limit: int = 25) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, handle, niche, created_at FROM analyses "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_analysis(analysis_id: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT result FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    return json.loads(row["result"]) if row else None


def clear_all() -> None:
    """Wipe every cached follower, score, and saved analysis."""
    with _conn() as conn:
        conn.executescript("DELETE FROM followers; DELETE FROM scores; DELETE FROM analyses;")


def leaderboard() -> list[dict]:
    """All analyzed accounts stack-ranked by account score (latest run per handle)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT handle, niche, result, created_at FROM analyses ORDER BY created_at DESC"
        ).fetchall()
    seen: set = set()
    out: list[dict] = []
    for r in rows:
        h = r["handle"]
        if h in seen:
            continue  # keep only the latest run per handle
        seen.add(h)
        try:
            res = json.loads(r["result"])
        except (ValueError, TypeError):
            continue
        score = res.get("account_score", res.get("audience_score"))
        if score is None:
            continue
        out.append({
            "handle": h, "niche": r["niche"],
            "account_score": round(float(score), 1), "created_at": r["created_at"],
        })
    out.sort(key=lambda x: x["account_score"], reverse=True)
    return out
