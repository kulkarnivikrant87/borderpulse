"""
aviation.py — Real-time aviation data via OpenSky Network (free, no key required)
Border Pulse v1.1

South Asia bounding box: lat 5-45N, lon 55-105E
Covers: LoC, LAC, Bangladesh theatre, Indian Ocean, Bay of Bengal
"""

import logging
import httpx

logger = logging.getLogger("borderpulse.aviation")

OPENSKY_URL = "https://opensky-network.org/api/states/all"
SOUTH_ASIA_BBOX = {"lamin": 5, "lomin": 55, "lamax": 45, "lomax": 105}

MILITARY_CALLSIGN_PREFIXES = [
    "IAF", "INDIA", "INACC", "INS", "COAST",
    "PAF", "PAKAF", "PLAAF", "PLAN",
    "REACH", "RCH", "JAKE", "IRON", "VALOR", "DEMON",
    "VIPER", "COBRA", "EAGLE", "RAPTOR", "HAVOC", "SABER",
    "KNIGHT", "FURY", "REAPER", "PREDATOR",
    "P8I", "P8A", "ATLAS", "POSEID", "HERKY", "TRASH75",
    "SENTRY", "AWACS", "BAF", "SLAF",
]

MILITARY_SQUAWKS = {"7700", "7600", "7500", "7777"}

COUNTRY_FLAG = {
    "India": "\U0001f1ee\U0001f1f3",
    "Pakistan": "\U0001f1f5\U0001f1f0",
    "China": "\U0001f1e8\U0001f1f3",
    "United States": "\U0001f1fa\U0001f1f8",
    "Bangladesh": "\U0001f1e7\U0001f1e9",
    "Sri Lanka": "\U0001f1f1\U0001f1f0",
    "Nepal": "\U0001f1f3\U0001f1f5",
    "Afghanistan": "\U0001f1e6\U0001f1eb",
    "Iran": "\U0001f1ee\U0001f1f7",
    "Oman": "\U0001f1f4\U0001f1f2",
    "United Arab Emirates": "\U0001f1e6\U0001f1ea",
    "Saudi Arabia": "\U0001f1f8\U0001f1e6",
}

INTEREST_COUNTRIES = {
    "India", "Pakistan", "China", "Bangladesh", "Sri Lanka",
    "Nepal", "United States", "United Arab Emirates", "Iran",
    "Oman", "Saudi Arabia", "Afghanistan",
}


def classify_military(callsign: str, squawk: str) -> bool:
    if squawk and squawk in MILITARY_SQUAWKS:
        return True
    if not callsign:
        return False
    cs = callsign.strip().upper()
    for prefix in MILITARY_CALLSIGN_PREFIXES:
        if cs.startswith(prefix):
            return True
    return False


def categorise_aircraft(callsign: str, country: str) -> str:
    cs = (callsign or "").upper()
    if any(x in cs for x in ["P8", "P3", "POSEID", "NEPTUNE"]):
        return "Maritime Patrol"
    if any(x in cs for x in ["REAPER", "PREDATOR", "GLOBAL HAWK"]):
        return "UAV/Drone"
    if any(x in cs for x in ["AWACS", "SENTRY", "HAWKEYE"]):
        return "AEW&C"
    if any(x in cs for x in ["REACH", "HERKY", "TRASH"]):
        return "Transport"
    if classify_military(callsign, ""):
        return "Military"
    return "Civil"


async def fetch_aviation(client: httpx.AsyncClient) -> list:
    """Fetch real-time aircraft positions from OpenSky Network."""
    try:
        resp = await client.get(
            OPENSKY_URL,
            params=SOUTH_ASIA_BBOX,
            timeout=20.0,
            headers={"User-Agent": "BorderPulse/1.1 OSINT-Dashboard (non-commercial research)"},
        )
        if resp.status_code == 429:
            logger.warning("[Aviation] OpenSky rate limited")
            return []
        if resp.status_code != 200:
            logger.warning(f"[Aviation] OpenSky HTTP {resp.status_code}")
            return []

        data = resp.json()
        states = data.get("states") or []

        aircraft = []
        for s in states:
            if len(s) < 10:
                continue
            lon, lat = s[5], s[6]
            if lon is None or lat is None:
                continue
            if s[8]:
                continue

            callsign = (s[1] or "").strip() or s[0]
            country = s[2] or "Unknown"
            alt_m = s[7] or s[13] or 0
            speed_ms = s[9] or 0
            heading = s[10] or 0
            squawk = s[14] or ""
            is_mil = classify_military(callsign, squawk)
            category = categorise_aircraft(callsign, country)

            aircraft.append({
                "icao24":      s[0],
                "callsign":    callsign,
                "country":     country,
                "flag":        COUNTRY_FLAG.get(country, "\U0001f3f3"),
                "lat":         round(lat, 5),
                "lon":         round(lon, 5),
                "altitude_m":  round(alt_m) if alt_m else None,
                "altitude_ft": round(alt_m * 3.28084) if alt_m else None,
                "speed_kts":   round(speed_ms * 1.94384) if speed_ms else None,
                "heading":     round(heading) if heading else 0,
                "squawk":      squawk or None,
                "military":    is_mil,
                "category":    category,
                "interest":    country in INTEREST_COUNTRIES or is_mil,
                "last_seen":   s[4],
            })

        total = len(aircraft)
        military_count = sum(1 for a in aircraft if a["military"])
        logger.info(f"[Aviation] {total} aircraft ({military_count} military)")
        return aircraft

    except Exception as exc:
        logger.error(f"[Aviation] Fetch error: {exc}")
        return []
