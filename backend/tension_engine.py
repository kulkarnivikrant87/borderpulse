"""
tension_engine.py — Composite tension score algorithm
Border Pulse v1.0

Calculates a 0–100 tension score per theatre using 5 weighted signals:
  - News volume spike   (25%)
  - GDELT tone score    (25%)
  - Incident keyword count (25%)
  - Diplomatic signal   (15%)
  - Prediction market   (10%)
"""

import math
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Rolling baseline (articles per 24h per theatre — approximate)
BASELINE_ARTICLE_COUNTS = {
    "loc":        12,
    "lac":        8,
    "bangladesh": 6,
    "naval":      5,
}

INCIDENT_KEYWORDS = [
    "firing", "airstrike", "incursion", "violation", "clash",
    "troops", "shelling", "ceasefire breach", "infiltration",
    "standoff", "provocation", "intrusion", "engagement",
    "military action", "cross-border",
]

DIPLOMATIC_POSITIVE = ["talks", "ceasefire", "dialogue", "negotiations", "agreement", "summit", "meeting"]
DIPLOMATIC_NEGATIVE = ["expelled", "sanctions", "suspended", "withdrawn", "escalation", "ultimatum", "warning"]

WEIGHTS = {
    "volume_spike":     0.25,
    "tone_score":       0.25,
    "incident_count":   0.25,
    "diplomatic":       0.15,
    "prediction_market": 0.10,
}


def calculate_tension(
    articles: List[Dict],
    theatre: str,
    polymarket_prob: float = 0.5,
) -> Dict:
    """
    Calculate composite tension score for a theatre.

    Args:
        articles:        List of normalised article dicts for this theatre.
        theatre:         Theatre ID ('loc', 'lac', 'bangladesh', 'naval').
        polymarket_prob: Probability from Polymarket (0–1). Default 0.5 (neutral).

    Returns:
        Dict with keys: score, breakdown, theatre, calculated_at
    """
    baseline = BASELINE_ARTICLE_COUNTS.get(theatre, 8)
    article_count = len(articles)

    # ── Signal 1: News volume spike (0–100) ──────────────────────
    # Score increases linearly above baseline, maxes at 2x baseline
    ratio = article_count / max(baseline, 1)
    if ratio >= 2.0:
        volume_score = 100.0
    elif ratio <= 0.5:
        volume_score = 0.0
    else:
        volume_score = ((ratio - 0.5) / 1.5) * 100.0
    volume_score = clamp(volume_score)

    # ── Signal 2: GDELT tone score (0–100, inverted) ──────────────
    # GDELT tone: -100 (very negative) to +100 (very positive)
    # We invert: more negative tone → higher tension
    tones = [float(a.get("tone", 0) or 0) for a in articles if a.get("tone") is not None]
    avg_tone = sum(tones) / len(tones) if tones else 0.0
    # Normalise: -100 → 100, +100 → 0
    tone_score = clamp(((-avg_tone) + 100) / 2)

    # ── Signal 3: Incident keyword count (0–100) ──────────────────
    incident_count = sum(
        1 for a in articles
        if any(kw in (a.get("title") or "").lower() for kw in INCIDENT_KEYWORDS)
    )
    # Scale: 0 incidents → 0, 5+ incidents → 100
    incident_score = clamp(incident_count / 5 * 100)

    # ── Signal 4: Diplomatic signal (modifier, -15 to +15) ────────
    pos_count = sum(
        1 for a in articles
        if any(kw in (a.get("title") or "").lower() for kw in DIPLOMATIC_POSITIVE)
    )
    neg_count = sum(
        1 for a in articles
        if any(kw in (a.get("title") or "").lower() for kw in DIPLOMATIC_NEGATIVE)
    )
    # Diplomatic score: positive diplomatic language reduces tension
    # Net: 0 baseline. Escalatory language pushes toward 100, de-escalatory toward 0.
    diplomatic_raw = (neg_count - pos_count) * 3
    diplomatic_modifier = max(-15.0, min(15.0, diplomatic_raw))
    # Convert to 0–100 scale: neutral=50, escalatory=100, de-escalatory=0
    diplomatic_score = clamp(50.0 + diplomatic_modifier * (50 / 15))

    # ── Signal 5: Prediction market (0–100) ──────────────────────
    # Polymarket probability directly maps to tension score
    prediction_score = clamp(polymarket_prob * 100)

    # ── Composite score ───────────────────────────────────────────
    composite = (
        volume_score     * WEIGHTS["volume_spike"] +
        tone_score       * WEIGHTS["tone_score"] +
        incident_score   * WEIGHTS["incident_count"] +
        diplomatic_score * WEIGHTS["diplomatic"] +
        prediction_score * WEIGHTS["prediction_market"]
    )

    composite = clamp(round(composite))

    breakdown = {
        "volume_spike":     round(volume_score, 1),
        "tone_score":       round(tone_score, 1),
        "incident_count":   round(incident_score, 1),
        "diplomatic":       round(diplomatic_score, 1),
        "prediction_market": round(prediction_score, 1),
        "article_count":    article_count,
        "avg_tone":         round(avg_tone, 2),
        "incident_articles": incident_count,
    }

    logger.info(
        f"[Tension] {theatre}: score={composite} | "
        f"vol={volume_score:.0f} tone={tone_score:.0f} "
        f"inc={incident_score:.0f} dip={diplomatic_score:.0f} pm={prediction_score:.0f}"
    )

    return {
        "theatre":      theatre,
        "score":        composite,
        "breakdown":    breakdown,
        "calculated_at": datetime.utcnow().isoformat() + "Z",
    }


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def get_tension_zone(score: int) -> str:
    if score <= 30: return "stable"
    if score <= 60: return "warning"
    if score <= 80: return "high"
    return "critical"
