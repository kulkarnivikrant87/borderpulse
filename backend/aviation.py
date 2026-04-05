"""
aviation.py — Real-time aviation data via adsb.fi (primary) + OpenSky (fallback)
Border Pulse v1.1

Primary:  https://opendata.adsb.fi/api/v2  — free, public, no rate-limit on server IPs
Fallback: https://opensky-network.org/api  — requires auth from server IPs

South Asia bounding box: lat 5-45N, lon 55-105E
"""

import logging
import os
import httpx
from datetime import datetime, timezone

logger = logging.getLogger("borderpulse.aviation")

ADSBFI_URL   = "https://opendata.adsb.fi/api/v2/lat/25/lon/80/dist/1500"
OPENSKY_URL  = "https://opensky-network.org/api/states/all"
SOUTH_ASIA_BBOX = {"lamin": 5, "lomin": 55, "lamax": 45, "lomax": 105}

BBOX = {"lat_min": 5, "lat_max": 45, "lon_min": 55, "lon_max": 105}

MILITARY_CALLSIGN_PREFIXES = [
    "IAF", "INDIA", "INACC", "INS", "COAST",
    "PAF", "PAKAF",
    "PLAAF", "PLAN",
    "REACH", "RCH", "JAKE", "IRON", "VALOR", "DEMON",
    "VIPER", "COBRA", "EAGLE", "RAPTOR", "HAVOC", "SABER",
    "KNIGHT", "FURY", "REAPER", "PREDATOR",
    "P8I", "P8A", "ATLAS", "POSEID",
    "HERKY", "TRASH75",
    "SENTRY", "AWACS",
    "BAF", "SLAF",
]

MILITARY_SQUAWKS = {"7700", "7600", "7500", "7777"}

COUNTRY_FLAG = {
    "India": "\U0001f1ee\U0001f1f3", "Pakistan": "\U0001f1f5\U0001f1f0",
    "China": "\U0001f1e8\U0001f1f3", "United States": "\U0001f1fa\U0001f1f8",
    "Bangladesh": "\U0001f1e7\U0001f1e9", "Sri Lanka": "\U0001f1f1\U0001f1f0",
    "Nepal": "\U0001f1f3\U0001f1f5", "Maldives": "\U0001f1f2\U0001f1fb",
    "Bhutan": "\U0001f1e7\U0001f1f9", "Afghanistan": "\U0001f1e6\U0001f1eb",
    "Iran": "\U0001f1ee\U0001f1f7", "Oman": "\U0001f1f4\U0001f1f2",
    "United Arab Emirates": "\U0001f1e6\U0001f1ea", "Saudi Arabia": "\U0001f1f8\U0001f1e6",
}

INTEREST_COUNTRIES = {
    "India", "Pakistan", "China", "Bangladesh", "Sri Lanka",
    "Nepal", "United States", "United Arab Emirates", "Iran",
    "Oman", "Saudi Arabia", "Afghanistan",
}


def classify_military(callsign: str, squawk: str, db_flags: int = 0) -> bool:
    if db_flags and (db_flags & 1):
        return True
    if squawk and squawk in MILITARY_SQUAWKS:
        return True
    if not callsign:
        return False
    cs = callsign.strip().upper()
    return any(cs.startswith(p) for p in MILITARY_CALLSIGN_PREFIXES)


def categorise_aircraft(callsign: str, country: str) -> str:
    cs = (callsign or "").upper()
    if any(x in cs for x in ["P8", "P3", "POSEID", "ATLAS", "NEPTUNE"]):
        return "Maritime Patrol"
    if any(x in cs for x in ["REAPER", "PREDATOR", "GLOBAL HAWK"]):
        return "UAV/Drone"
    if any(x in cs for x in ["AWACS", "SENTRY", "HAWKEYE"]):
        return "AEW&C"
    if any(x in cs for x in ["REACH", "HERKY", "TRASH", "ATLAS"]):
        return "Transport"
    if classify_military(callsign, ""):
        return "Military"
    return "Civil"


def _reg_to_country(reg: str, icao24: str) -> str:
    if icao24:
        prefix = icao24[:2].upper()
        icao_map = {
            "80": "India", "81": "India", "82": "India",
            "76": "Pakistan",
            "78": "China", "79": "China", "7B": "China",
            "73": "Iran",
            "71": "Saudi Arabia",
            "74": "United Arab Emirates",
            "77": "Bangladesh",
            "AE": "United States", "A0": "United States", "A1": "United States",
            "A2": "United States", "A3": "United States", "A4": "United States",
            "A5": "United States", "A6": "United States", "A7": "United States",
            "A8": "United States", "A9": "United States", "AA": "United States",
            "AB": "United States", "AC": "United States", "AD": "United States",
        }
        country = icao_map.get(prefix)
        if country:
            return country
    if reg:
        reg_map = {
            "VT": "India", "AP": "Pakistan", "B-": "China",
            "S2": "Bangladesh", "4R": "Sri Lanka", "9N": "Nepal",
            "EP": "Iran", "A4O": "Oman", "A6": "United Arab Emirates",
            "HZ": "Saudi Arabia", "N": "United States",
        }
        for prefix, country in reg_map.items():
            if reg.startswith(prefix):
                return country
    return "Unknown"


def _parse_adsbfi(data: dict) -> list:
    aircraft = []
    for ac in data.get("ac") or []:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue
        if not (BBOX["lat_min"] <= lat <= BBOX["lat_max"] and
                BBOX["lon_min"] <= lon <= BBOX["lon_max"]):
            continue
        if ac.get("alt_baro") == "ground":
            continue

        callsign  = (ac.get("flight") or ac.get("r") or ac.get("hex") or "").strip()
        icao24    = ac.get("hex", "")
        alt_ft    = ac.get("alt_baro") or ac.get("alt_geom")
        alt_m     = round(alt_ft / 3.28084) if isinstance(alt_ft, (int, float)) else None
        speed_kts = ac.get("gs")
        heading   = ac.get("track")
        squawk    = str(ac.get("squawk") or "")
        db_flags  = ac.get("dbFlags", 0) or 0
        reg       = ac.get("r") or ""
        country   = _reg_to_country(reg, icao24)
        is_mil    = classify_military(callsign, squawk, db_flags)
        category  = categorise_aircraft(callsign, country)

        aircraft.append({
            "icao24":      icao24,
            "callsign":    callsign or icao24,
            "country":     country,
            "flag":        COUNTRY_FLAG.get(country, "\U0001f3f3"),
            "lat":         round(lat, 5),
            "lon":         round(lon, 5),
            "altitude_m":  alt_m,
            "altitude_ft": int(alt_ft) if isinstance(alt_ft, (int, float)) else None,
            "speed_kts":   round(speed_kts) if speed_kts else None,
            "heading":     round(heading) if heading else 0,
            "squawk":      squawk or None,
            "military":    is_mil,
            "category":    category,
            "interest":    country in INTEREST_COUNTRIES or is_mil,
            "last_seen":   ac.get("seen"),
        })
    return aircraft


def _parse_opensky(states: list) -> list:
    aircraft = []
    for s in (states or []):
        if len(s) < 10:
            continue
        lon, lat = s[5], s[6]
        if lon is None or lat is None:
            continue
        if s[8]:
            continue
        callsign  = (s[1] or "").strip() or s[0]
        country   = s[2] or "Unknown"
        alt_m     = s[7] or s[13] or 0
        speed_ms  = s[9] or 0
        heading   = s[10] or 0
        squawk    = s[14] or ""
        is_mil    = classify_military(callsign, squawk)
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
            "category":    categorise_aircraft(callsign, country),
            "interest":    country in INTEREST_COUNTRIES or is_mil,
            "last_seen":   s[4],
        })
    return aircraft


async def fetch_aviation(client: httpx.AsyncClient) -> list:
    """Try adsb.fi first (open public API, no server IP restrictions).
    Fall back to OpenSky Network if adsb.fi fails."""

    # Primary: adsb.fi
    try:
        resp = await client.get(
            ADSBFI_URL,
            timeout=20.0,
            headers={"User-Agent": "BorderPulse/1.1 OSINT (non-commercial)"},
        )
        if resp.status_code == 200:
            aircraft = _parse_adsbfi(resp.json())
            mil = sum(1 for a in aircraft if a["military"])
            logger.info(f"[Aviation] adsb.fi: {len(aircraft)} aircraft ({mil} military)")
            return aircraft
        logger.warning(f"[Aviation] adsb.fi HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning(f"[Aviation] adsb.fi failed: {exc}")

    # Fallback: OpenSky
    logger.info("[Aviation] Falling back to OpenSky Network")
    try:
        opensky_user = os.getenv("OPENSKY_USER")
        opensky_pass = os.getenv("OPENSKY_PASS")
        auth = (opensky_user, opensky_pass) if opensky_user else None

        resp = await client.get(
            OPENSKY_URL,
            params=SOUTH_ASIA_BBOX,
            auth=auth,
            timeout=20.0,
            headers={"User-Agent": "BorderPulse/1.1 OSINT (non-commercial)"},
        )
        if resp.status_code == 429:
            logger.warning("[Aviation] OpenSky rate-limited")
            return []
        if resp.status_code != 200:
            logger.warning(f"[Aviation] OpenSky HTTP {resp.status_code}")
            return []

        aircraft = _parse_opensky(resp.json().get("states") or [])
        mil = sum(1 for a in aircraft if a["military"])
        logger.info(f"[Aviation] OpenSky: {len(aircraft)} aircraft ({mil} military)")
        return aircraft

    except Exception as exc:
        logger.error(f"[Aviation] Both sources failed: {exc}")
        return []
