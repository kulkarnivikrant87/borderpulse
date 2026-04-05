"""
ai_summary.py — Claude Haiku API integration + SQLite history store
Border Pulse v1.0

Generates hourly analyst-grade situation summaries per theatre using
Claude Haiku 4.5 via the Anthropic API.

Stores last 48 hours of summaries in SQLite for historical browsing.
"""

import os
import json
import sqlite3
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import anthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a neutral geopolitical intelligence analyst specialising in South Asia. "
    "Given the latest news headlines and data for a specific border theatre, produce a "
    "concise 3-sentence situation briefing. "
    "Rules: (1) Strictly neutral — no political bias toward any country. "
    "(2) State facts only — no speculation. "
    "(3) End with a one-word status: ESCALATING / STABLE / DE-ESCALATING. "
    "(4) Maximum 80 words total. "
    "Format: [Briefing text]. Status: [WORD]"
)

THEATRE_NAMES = {
    "loc":        "Line of Control (India-Pakistan)",
    "lac":        "Line of Actual Control (India-China)",
    "bangladesh": "India-Bangladesh Border",
    "naval":      "Bay of Bengal / Arabian Sea",
}

DB_PATH = os.path.join(os.path.dirname(__file__), "summaries.db")


# ── Database setup ────────────────────────────────────────────────
def init_db():
    """Initialise SQLite database for summary history."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            theatre     TEXT NOT NULL,
            summary     TEXT NOT NULL,
            status      TEXT NOT NULL,
            tension     INTEGER,
            generated_at INTEGER NOT NULL,
            raw_response TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_theatre_time ON summaries (theatre, generated_at)")
    conn.commit()
    conn.close()


def save_summary(theatre: str, summary: str, status: str, tension: int, raw: str):
    """Save a generated summary to SQLite."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT INTO summaries (theatre, summary, status, tension, generated_at, raw_response) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (theatre, summary, status, tension, int(time.time()), raw)
        )
        # Purge summaries older than 48 hours
        cutoff = int(time.time()) - 48 * 3600
        conn.execute("DELETE FROM summaries WHERE generated_at < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[DB] Failed to save summary for {theatre}: {e}")


def get_summary_history(theatre: str, hours: int = 48) -> List[Dict]:
    """Retrieve summary history for a theatre (last N hours)."""
    try:
        init_db()
        cutoff = int(time.time()) - hours * 3600
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT theatre, summary, status, tension, generated_at "
            "FROM summaries WHERE theatre=? AND generated_at >= ? "
            "ORDER BY generated_at DESC",
            (theatre, cutoff)
        ).fetchall()
        conn.close()
        return [
            {"theatre": r[0], "summary": r[1], "status": r[2],
             "tension": r[3], "generated_at": r[4]}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"[DB] Failed to retrieve history for {theatre}: {e}")
        return []


# ── Claude Haiku API call ─────────────────────────────────────────
async def generate_summary(
    theatre: str,
    articles: List[Dict],
    tension_score: int,
    tone_score: float,
) -> Dict:
    """
    Generate a situation summary using Claude Haiku 4.5.

    Args:
        theatre:       Theatre ID.
        articles:      Last 10 articles for the theatre.
        tension_score: Current composite tension score (0–100).
        tone_score:    Average GDELT tone score for the theatre.

    Returns:
        Dict with keys: theatre, summary, status, generated_at, tension
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("[AI] ANTHROPIC_API_KEY not set")
        return _fallback_summary(theatre, tension_score)

    theatre_name = THEATRE_NAMES.get(theatre, theatre.upper())
    headlines = "\n".join(
        f"- {a.get('title', 'No title')}"
        for a in (articles or [])[:10]
    ) or "No recent headlines available."

    user_prompt = (
        f"Theatre: {theatre_name}\n"
        f"Current tension score: {tension_score}/100\n"
        f"Average news tone: {tone_score:.1f} (negative = hostile reporting)\n"
        f"\nLatest headlines:\n{headlines}\n"
        f"\nProvide your 3-sentence briefing:"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = message.content[0].text.strip()
        summary, status = parse_response(raw)

        init_db()
        save_summary(theatre, summary, status, tension_score, raw)

        logger.info(f"[AI] {theatre}: status={status} | summary={summary[:60]}...")

        return {
            "theatre":      theatre,
            "summary":      summary,
            "status":       status,
            "generated_at": int(time.time()),
            "tension":      tension_score,
        }

    except anthropic.APIConnectionError as e:
        logger.error(f"[AI] Connection error for {theatre}: {e}")
    except anthropic.RateLimitError:
        logger.warning(f"[AI] Rate limited for {theatre}")
    except anthropic.APIStatusError as e:
        logger.error(f"[AI] API error for {theatre}: {e.status_code} — {e.message}")
    except Exception as e:
        logger.error(f"[AI] Unexpected error for {theatre}: {e}")

    return _fallback_summary(theatre, tension_score)


def parse_response(raw: str) -> tuple[str, str]:
    """Extract summary text and status word from model response."""
    status = "STABLE"
    for word in ["ESCALATING", "DE-ESCALATING", "STABLE"]:
        if word in raw.upper():
            status = word
            break

    # Remove "Status: WORD" from the summary text
    summary = raw
    for suffix in [f"Status: {status}", f"Status: {status.lower()}", f"Status: {status.capitalize()}"]:
        summary = summary.replace(suffix, "").strip()
    summary = summary.rstrip(".").strip()
    if summary and not summary.endswith("."):
        summary += "."

    return summary, status


def _fallback_summary(theatre: str, tension_score: int) -> Dict:
    """Return a generic fallback when the API is unavailable."""
    zone = "elevated" if tension_score > 50 else "moderate"
    summary = (
        f"Intelligence feeds for this theatre show {zone} activity levels. "
        "Real-time AI analysis is temporarily unavailable. "
        "Manual review of the news feed is recommended."
    )
    status = "ESCALATING" if tension_score > 70 else "STABLE"
    return {
        "theatre":      theatre,
        "summary":      summary,
        "status":       status,
        "generated_at": int(time.time()),
        "tension":      tension_score,
        "_fallback":    True,
    }
