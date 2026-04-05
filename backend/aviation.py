"""
aviation.py — Real-time aviation data via adsb.fi (primary) + OpenSky (fallback)
Border Pulse v1.1

Primary:  https://opendata.adsb.fi/api/v2  — free, public, no rate-limit on server IPs
Fallback: https://opensky-network.org/api  — requires auth from server IPs

South Asia bounding box: lat 5–45°N, lon 55–105°E
Covers: LoC, LAC, Bangladesh theatre, Indian Ocean, Bay of Bengal
"""

import asyncio
import logging
import os
import httpx
from datetime import datetime, timezone

logger = logging.getLogger("borderpulse.aviation")

# adsb.fi — primary (open public feed, no auth needed)
# adsb.fi max radius is ~250nm — use 8 overlapping queries to tile South Asia
ADSBFI_BASE  = "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/250"
ADSBFI_CENTRES = [
    (28.0,  70.0),   # NW India / Pakistan
    (25.0,  89.0),   # NE India / Bangladesh
    (15.0,  78.0),   # South India / Sri Lanka
    (20.0,  63.0),   # Arabian Sea
    (15.0,  88.0),   # Bay of Bengal
    (24.0,  57.0),   # Persian Gulf / Oman
    (22.0,  80.0),   # Central India (MP, Chhattisgarh, Telangana, Odisha)
    (22.0,  72.0),   # Gujarat / Mumbai corridor
]
OPENSKY_URL  = "https://opensky-network.org/api/states/all"
SOUTH_ASIA_BBOX = {"lamin": 5, "lomin": 55, "lamax": 45, "lomax": 105}

# Lat/lon bbox for filtering adsb.fi results (which returns a radius)
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
    "India": "🇨🇳", "Pakistan": "🇵🇰", "China": "🇨🇳",
    "United States": "🇺🇸", "Bangladesh": "🇧🇩", "Sri Lanka": "🇱🇰",
    "Nepal": "🇳🇵", "Maldives": "🇲🇻", "Bhutan": "🇧🇹",
    "Afghanistan": "🇦🇫", "Iran": "🇮🇷", "Oman": "🇴🇲",
    "United Arab Emirates": "🇦🇪", "Saudi Arabia": "🇸🇦",
}

INTEREST_COUNTRIES = {
    "India", "Pakistan", "China", "Bangladesh", "Sri Lanka",
    "Nepal", "United States", "United Arab Emirates", "Iran",
    "Oman", "Saudi Arabia", "Afghanistan",
}


def classify_military(callsign: str, squawk: str, db_flags: int = 0) -> bool:
    """Detect military aircraft via callsign prefix, squawk code, or adsb.fi dbFlags."""
    if db_flags and (db_flags & 1):   # bit 0 = military in adsb.fi
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


def _parse_adsbfi(data: dict) -> list:
    """Parse adsb.fi /v2/lat/lon/dist response into our aircraft format."""
    aircraft = []
    for ac in data.get("aircraft") or data.get("ac") or []:
        lat = ac.get("lat")
        lon = ac.get("lon")
        if lat is None or lon is None:
            continue
        # Filter to our bounding box (adsb.fi returns a circle)
        if not (BBOX["lat_min"] <= lat <= BBOX["lat_max"] and
                BBOX["lon_min"] <= lon <= BBOX["lon_max"]):
            continue
        # Skip ground traffic
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

        reg = ac.get("r") or ""
        country = _reg_to_country(reg, icao24)

        is_mil   = classify_military(callsign, squawk, db_flags)
        category = categorise_aircraft(callsign, country)

        aircraft.append({
            "icao24":      icao24,
            "callsign":    callsign or icao24,
            "country":     country,
            "flag":        COUNTRY_FLAG.get(country, "🏳"),
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


def _reg_to_country(reg: str, icao24: str) -> str:
    """Rough country lookup from ICAO prefix or registration."""
    if icao24:
        prefix = icao24[:2].upper()
        icao_map = {
            "80": "India", "81": "India", "82": "India",
            "76": "Pakistan",
            "78": "China", "79": "China", "7B": "China",
            "70": "Afghanistan",
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
            "flag":        COUNTRY_FLAG.get(country, "🏳"),
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
    """
    Try adsb.fi first (open public API, works from server IPs).
    Uses 8 parallel 250nm-radius queries to tile South Asia (adsb.fi max is ~250nm).
    Falls back to OpenSky Network if all adsb.fi queries fail.
    """

    async def fetch_one_tile(lat: float, lon: float) -> list:
        url = ADSBFI_BASE.format(lat=lat, lon=lon)
        try:
            resp = await client.get(
                url,
                timeout=20.0,
                headers={"User-Agent": "BorderPulse/1.1 OSINT (non-commercial)"},
            )
            if resp.status_code == 200:
                return _parse_adsbfi(resp.json())
            logger.debug(f"[Aviation] adsb.fi ({lat},{lon}) HTTP {resp.status_code}")
        except Exception as exc:
            logger.debug(f"[Aviation] adsb.fi tile ({lat},{lon}) failed: {exc}")
        return []

    try:
        tile_results = await asyncio.gather(
            *[fetch_one_tile(lat, lon) for lat, lon in ADSBFI_CENTRES]
        )
        seen: set = set()
        aircraft: list = []
        for tile in tile_results:
            for ac in tile:
                if ac["icao24"] not in seen:
                    seen.add(ac["icao24"])
                    aircraft.append(ac)

        if aircraft:
            mil = sum(1 for a in aircraft if a["military"])
            logger.info(f"[Aviation] adsb.fi: {len(aircraft)} aircraft ({mil} military) from {len(ADSBFI_CENTRES)} tiles")
            return aircraft
        logger.warning("[Aviation] adsb.fi returned 0 aircraft across all tiles")
    except Exception as exc:
        logger.warning(f"[Aviation] adsb.fi failed: {exc}")

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

        data = resp.json()
        aircraft = _parse_opensky(data.get("states") or [])
        mil = sum(1 for a in aircraft if a["military"])
        logger.info(f"[Aviation] OpenSky: {len(aircraft)} aircraft ({mil} military)")
        return aircraft

    except Exception as exc:
        logger.error(f"[Aviation] Both sources failed: {exc}")
        return []
