"""
gdelt.py — GDELT DOC 2.0 API wrapper
Border Pulse v1.0

Fetches articles from GDELT for each theatre using configurable keyword queries.
GDELT is a free public API — no key required.
"""

import httpx
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

GDELT_API_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"

THEATRE_QUERIES = {
    "loc":        "India Pakistan border",
    "lac":        "India China LAC border",
    "bangladesh": "India Bangladesh border",
    "naval":      "Bay of Bengal naval Pakistan China",
}

INCIDENT_KEYWORDS = [
    "firing", "airstrike", "incursion", "violation", "clash",
    "troops", "shelling", "ceasefire breach", "infiltration", "standoff",
]

DIPLOMATIC_POSITIVE = ["talks", "ceasefire", "dialogue", "negotiations", "agreement", "summit"]
DIPLOMATIC_NEGATIVE = ["expelled", "sanctions", "suspended", "withdrawn", "escalation", "ultimatum"]


async def fetch_theatre_articles(
    theatre: str,
    max_articles: int = 20,
    timespan: str = "1d",
    client: Optional[httpx.AsyncClient] = None,
) -> List[Dict]:
    """
    Fetch articles from GDELT DOC 2.0 API for a given theatre.

    Returns a list of article dicts with keys:
      url, title, domain, seendate, tone, sourcecountry, language, theatre
    """
    query = THEATRE_QUERIES.get(theatre)
    if not query:
        logger.warning(f"Unknown theatre: {theatre}")
        return []

    params = {
        "query":    query,
        "mode":     "artlist",
        "format":   "json",
        "maxrecords": max_articles,
        "timespan": timespan,
        "sort":     "datedesc",
    }

    try:
        should_close = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            should_close = True

        resp = await client.get(GDELT_API_BASE, params=params)
        resp.raise_for_status()
        data = resp.json()

        if should_close:
            await client.aclose()

        articles = data.get("articles", [])

        # Enrich each article
        enriched = []
        for a in articles:
            enriched.append({
                "url":           a.get("url", ""),
                "title":         a.get("title", ""),
                "domain":        a.get("domain", ""),
                "seendate":      a.get("seendate", ""),
                "tone":          a.get("tone", 0),
                "sourcecountry": a.get("sourcecountry", ""),
                "language":      a.get("language", "English"),
                "theatre":       theatre,
                "_sourceCount":  1,
            })

        logger.info(f"[GDELT] {theatre}: fetched {len(enriched)} articles")
        return enriched

    except httpx.HTTPStatusError as e:
        logger.error(f"[GDELT] HTTP error for {theatre}: {e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.error(f"[GDELT] Request error for {theatre}: {e}")
        return []
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[GDELT] Parse error for {theatre}: {e}")
        return []


def count_incident_keywords(articles: List[Dict]) -> int:
    """Count articles containing incident-related keywords (last 48h)."""
    count = 0
    cutoff = datetime.utcnow() - timedelta(hours=48)
    for a in articles:
        title = (a.get("title") or "").lower()
        if any(kw in title for kw in INCIDENT_KEYWORDS):
            count += 1
    return count


def get_diplomatic_signal(articles: List[Dict]) -> float:
    """
    Returns a modifier for the tension score based on diplomatic language.
    Positive = de-escalatory signals detected (reduces tension).
    Negative = escalatory signals detected (increases tension).
    Range: -15 to +15.
    """
    pos_count = sum(
        1 for a in articles
        if any(kw in (a.get("title") or "").lower() for kw in DIPLOMATIC_POSITIVE)
    )
    neg_count = sum(
        1 for a in articles
        if any(kw in (a.get("title") or "").lower() for kw in DIPLOMATIC_NEGATIVE)
    )
    # Net signal, clamped to ±15
    signal = (neg_count - pos_count) * 3
    return max(-15.0, min(15.0, signal))
