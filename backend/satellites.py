"""
satellites.py — Real-time satellite position tracking
Border Pulse v1.1

Primary TLE source: tle.ivanstanojevic.me (free JSON API, no auth required)
Fallback: hardcoded TLEs for verified satellites (refreshed periodically via commit)
Library: sgp4 (Two-Line Element propagation)

Tracks reconnaissance, navigation, and dual-use satellites relevant to South Asia.

NOTE ON CATALOGUE:
  Many military/classified satellites (YAOGAN, USA-xxx) do not appear in public
  TLE databases under their real names. The catalogue below only includes
  satellites with VERIFIED correct NORAD IDs confirmed against the TLE API.
  Hardcoded fallback TLEs were captured 2026-04-06.
"""

import asyncio
import logging
import math
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("borderpulse.satellites")

# ── TLE source ──────────────────────────────────────────────────────────────────────────────
# Per-satellite JSON API — free, no auth, accessible from Railway
TLE_API_URL = "https://tle.ivanstanojevic.me/api/tle/{norad}"

# ── Satellite Catalogue ────────────────────────────────────────────────────────────────────────────
# Only satellites with VERIFIED correct NORAD IDs.
# name_match: substring that must appear in the API response name (case-insensitive)
SATELLITE_CATALOGUE = [
    # ── India — ISRO ──
    {
        "name": "RISAT-2B", "norad": 44233,
        "country": "India", "type": "SAR",
        "role": "All-weather border & maritime surveillance (C-band, 0.5m res)",
        "name_match": "RISAT-2B",
    },
    {
        "name": "IRNSS-1I", "norad": 43286,
        "country": "India", "type": "NavIC",
        "role": "Indian Regional Navigation Satellite System — military-grade positioning",
        "name_match": "IRNSS",
    },
    {
        "name": "GSAT-30", "norad": 45026,
        "country": "India", "type": "Comms",
        "role": "Geostationary C/Ku-band communications — civil & dual-use",
        "name_match": "GSAT-30",
    },
    # ── Reference ──
    {
        "name": "ISS", "norad": 25544,
        "country": "International", "type": "Station",
        "role": "International Space Station — reference orbit",
        "name_match": "ISS",
    },
]

# ── Hardcoded fallback TLEs (captured 2026-04-06, valid for ~2 weeks) ──────────────────
# Used when the API is unreachable. Update by re-fetching from ivanstanojevic.
FALLBACK_TLES = {
    25544: (
        "ISS (ZARYA)",
        "1 25544U 98067A   26094.84355279  .00009370  00000+0  17936-3 0  9991",
        "2 25544  51.6331 303.0545 0006326 272.5089  87.5175 15.48773610560388",
    ),
    43286: (
        "IRNSS-1I",
        "1 43286U 18035A   26094.01711129  .00000092  00000+0  00000+0 0  9992",
        "2 43286  29.0042  75.3378 0018350 190.1078 348.2572  1.00278898 29339",
    ),
    44233: (
        "RISAT-2B",
        "1 44233U 19028A   26094.93360068  .00004731  00000+0  36709-3 0  9994",
        "2 44233  36.9972  68.4378 0004918 180.4510 179.6229 15.01254688376812",
    ),
}

# South Asia + Indian Ocean bounding box for "overhead" classification
SOUTH_ASIA_BBOX = {"lat_min": -10, "lat_max": 48, "lon_min": 50, "lon_max": 110}

COUNTRY_COLOURS = {
    "India":         "#FF9933",
    "China":         "#DE2910",
    "Pakistan":      "#01411C",
    "USA":           "#3C3B6E",
    "International": "#2EC4B6",
}


# ── Coordinate Conversion ──────────────────────────────────────────────────────────────────────────────

def greenwich_mean_sidereal_time(jd: float) -> float:
    T = (jd - 2451545.0) / 36525.0
    theta_deg = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + T * T * (0.000387933 - T / 38710000.0)
    )
    return math.radians(theta_deg % 360.0)


def eci_to_geodetic(r: tuple, jd: float) -> tuple:
    theta = greenwich_mean_sidereal_time(jd)
    x = r[0] * math.cos(theta) + r[1] * math.sin(theta)
    y = -r[0] * math.sin(theta) + r[1] * math.cos(theta)
    z = r[2]
    a = 6378.137
    e2 = 0.00669437999014
    p = math.sqrt(x**2 + y**2)
    lat = math.atan2(z, p * (1.0 - e2))
    for _ in range(5):
        N = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * N * math.sin(lat), p)
    lon = math.atan2(y, x)
    N = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
    cos_lat = math.cos(lat)
    if abs(cos_lat) > 1e-4:
        alt = p / cos_lat - N
    else:
        alt = abs(z) / abs(math.sin(lat)) - N * (1.0 - e2)
    return math.degrees(lat), math.degrees(lon), alt


def compute_ground_track(sat_rec, jd_now: float, minutes: int = 100, step_min: int = 4) -> list:
    track = []
    jd_whole = math.floor(jd_now)
    jd_frac = jd_now - jd_whole
    for i in range(0, minutes, step_min):
        frac = jd_frac + i / 1440.0
        whole_offset = math.floor(frac)
        frac -= whole_offset
        e, r, _ = sat_rec.sgp4(jd_whole + whole_offset, frac)
        if e == 0 and r[0] is not None:
            try:
                lat, lon, _ = eci_to_geodetic(r, jd_whole + whole_offset + frac)
                track.append([round(lat, 2), round(lon, 2)])
            except Exception:
                pass
    return track


def _propagate(sat_rec, jd_now: float, sat_info: dict):
    """Run sgp4 propagation and return enriched satellite dict, or None on error."""
    try:
        jd_whole = math.floor(jd_now)
        jd_frac  = jd_now - jd_whole
        e, r, v  = sat_rec.sgp4(jd_whole, jd_frac)
        if e != 0 or r[0] is None:
            return None
        lat, lon, alt_km = eci_to_geodetic(r, jd_now)
        speed_kms = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
        ground_track = compute_ground_track(sat_rec, jd_now)
        bbox = SOUTH_ASIA_BBOX
        over = bbox["lat_min"] <= lat <= bbox["lat_max"] and bbox["lon_min"] <= lon <= bbox["lon_max"]
        now_utc = datetime.now(timezone.utc)
        return {
            "name":            sat_info["name"],
            "norad":           sat_info["norad"],
            "country":         sat_info["country"],
            "type":            sat_info["type"],
            "role":            sat_info["role"],
            "colour":          COUNTRY_COLOURS.get(sat_info["country"], "#8899AA"),
            "lat":             round(lat, 3),
            "lon":             round(lon, 3),
            "altitude_km":     round(alt_km, 1),
            "speed_kms":       round(speed_kms, 2),
            "period_min":      round(
                2 * math.pi * (alt_km + 6371)**1.5
                / math.sqrt(398600.4 * (alt_km + 6371)) / 60, 1
            ),
            "ground_track":    ground_track,
            "over_south_asia": over,
            "computed_at":     now_utc.isoformat() + "Z",
        }
    except Exception as exc:
        logger.debug(f"[Satellites] Propagation error for {sat_info['name']}: {exc}")
        return None


# ── Main fetch ────────────────────────────────────────────────────────────────────────────────────

async def fetch_satellites(client: httpx.AsyncClient) -> list:
    """
    Fetch TLE data from tle.ivanstanojevic.me (JSON, per satellite),
    verify name matches catalogue entry, compute current positions with sgp4.
    Falls back to hardcoded TLEs if the API is unreachable.
    """
    try:
        from sgp4.api import Satrec
    except ImportError:
        logger.error("[Satellites] sgp4 not installed — add sgp4 to requirements.txt")
        return []

    now_utc = datetime.now(timezone.utc)
    jd_now  = now_utc.timestamp() / 86400.0 + 2440587.5

    async def fetch_tle(sat_info: dict):
        """Return (name, tle1, tle2) or None."""
        norad = sat_info["norad"]
        url   = TLE_API_URL.format(norad=norad)
        try:
            resp = await client.get(
                url, timeout=10.0,
                headers={"User-Agent": "BorderPulse/1.1 OSINT (non-commercial)"},
            )
            if resp.status_code == 200:
                data  = resp.json()
                name  = data.get("name", "")
                line1 = data.get("line1", "")
                line2 = data.get("line2", "")
                match_key = sat_info.get("name_match", sat_info["name"])
                if line1 and line2 and match_key.upper() in name.upper():
                    logger.debug(f"[Satellites] API: {norad} → {name}")
                    return (name, line1, line2)
                elif line1 and line2:
                    logger.debug(f"[Satellites] Name mismatch {norad}: expected '{match_key}', got '{name}' — using fallback")
        except Exception as exc:
            logger.debug(f"[Satellites] API unreachable for {norad}: {exc}")

        # Fall back to hardcoded TLE
        if norad in FALLBACK_TLES:
            logger.debug(f"[Satellites] Using hardcoded TLE for {sat_info['name']}")
            return FALLBACK_TLES[norad]
        return None

    # Fetch all TLEs in parallel
    tle_results = await asyncio.gather(*[fetch_tle(s) for s in SATELLITE_CATALOGUE])

    results = []
    for sat_info, tle_entry in zip(SATELLITE_CATALOGUE, tle_results):
        if tle_entry is None:
            logger.debug(f"[Satellites] No TLE for {sat_info['name']}, skipping")
            continue
        _, tle1, tle2 = tle_entry
        sat_rec = Satrec.twoline2rv(tle1, tle2)
        result  = _propagate(sat_rec, jd_now, sat_info)
        if result:
            results.append(result)

    over_count = sum(1 for s in results if s.get("over_south_asia"))
    logger.info(f"[Satellites] {len(results)} satellites computed, {over_count} over South Asia")
    return results
