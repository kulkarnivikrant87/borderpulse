"""
satellites.py -- Real-time satellite position tracking via Celestrak + sgp4
Border Pulse v1.1
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
import httpx

logger = logging.getLogger("borderpulse.satellites")

SATELLITE_CATALOGUE = [
    {"name": "RISAT-2B",   "norad": 44233, "country": "India",   "type": "SAR",       "role": "All-weather maritime & border surveillance"},
    {"name": "RISAT-2BR1", "norad": 45359, "country": "India",   "type": "SAR",       "role": "High-resolution SAR reconnaissance"},
    {"name": "RISAT-2BR2", "norad": 47511, "country": "India",   "type": "SAR",       "role": "SAR intelligence gathering"},
    {"name": "CARTOSAT-3", "norad": 45026, "country": "India",   "type": "Optical",   "role": "Sub-metre resolution imaging (~0.25m)"},
    {"name": "EMISAT",     "norad": 44326, "country": "India",   "type": "SIGINT",    "role": "Electronic intelligence / signals monitoring"},
    {"name": "MICROSAT-R", "norad": 44112, "country": "India",   "type": "Optical",   "role": "ASAT target / tech demo satellite"},
    {"name": "IRNSS-1I",   "norad": 43286, "country": "India",   "type": "NavIC",     "role": "Indian regional navigation (military-grade)"},
    {"name": "YAOGAN-33",  "norad": 46028, "country": "China",   "type": "Optical",   "role": "High-resolution optical reconnaissance"},
    {"name": "YAOGAN-34",  "norad": 47774, "country": "China",   "type": "SAR",       "role": "SAR imaging constellation"},
    {"name": "YAOGAN-36A", "norad": 53323, "country": "China",   "type": "ELINT",     "role": "Electronic intelligence triplet"},
    {"name": "YAOGAN-36B", "norad": 53324, "country": "China",   "type": "ELINT",     "role": "Electronic intelligence triplet"},
    {"name": "YAOGAN-36C", "norad": 53325, "country": "China",   "type": "ELINT",     "role": "Electronic intelligence triplet"},
    {"name": "SHIYAN-13",  "norad": 54237, "country": "China",   "type": "Classified","role": "Technology experiment (recon-adjacent)"},
    {"name": "PRSS-1",     "norad": 43638, "country": "Pakistan","type": "Optical",   "role": "Pakistan Remote Sensing Satellite (Chinese-built)"},
    {"name": "PAKTES-1A",  "norad": 43937, "country": "Pakistan","type": "Optical",   "role": "Technology demonstration / observation"},
    {"name": "USA-224",    "norad": 36830, "country": "USA",     "type": "Classified","role": "NRO KH-class optical reconnaissance"},
    {"name": "USA-290",    "norad": 43647, "country": "USA",     "type": "Classified","role": "NRO advanced reconnaissance"},
    {"name": "ISS",        "norad": 25544, "country": "International","type": "Station","role": "International Space Station (reference)"},
]

TLE_GROUP_URLS = [
    "https://celestrak.org/pub/TLE/resource.txt",
    "https://celestrak.org/pub/TLE/tle-new.txt",
    "https://celestrak.org/pub/TLE/visual.txt",
    "https://celestrak.org/pub/TLE/military.txt",
]

CELESTRAK_SINGLE_URL = "https://celestrak.org/TLE/query.php?CATNR={norad}"
SOUTH_ASIA_BBOX = {"lat_min": -10, "lat_max": 48, "lon_min": 50, "lon_max": 110}
COUNTRY_COLOURS = {
    "India": "#FF9933", "China": "#DE2910", "Pakistan": "#01411C",
    "USA": "#3C3B6E", "International": "#2EC4B6",
}


def parse_tle_text(text: str) -> dict:
    result = {}
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    i = 0
    while i < len(lines) - 2:
        line1 = lines[i + 1] if i + 1 < len(lines) else ""
        line2 = lines[i + 2] if i + 2 < len(lines) else ""
        if line1.startswith("1 ") and line2.startswith("2 "):
            try:
                norad = int(line1[2:7].strip())
                result[norad] = (lines[i], line1, line2)
            except ValueError:
                pass
            i += 3
        else:
            i += 1
    return result


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


async def fetch_satellites(client: httpx.AsyncClient) -> list:
    try:
        from sgp4.api import Satrec
    except ImportError:
        logger.error("[Satellites] sgp4 library not installed")
        return []

    tle_master: dict = {}

    async def fetch_group(url: str):
        try:
            r = await client.get(url, timeout=15.0, headers={"User-Agent": "BorderPulse/1.1"})
            if r.status_code == 200:
                parsed = parse_tle_text(r.text)
                logger.debug(f"[Satellites] {url.split('/')[-1]}: {len(parsed)} TLEs")
                return parsed
        except Exception as exc:
            logger.debug(f"[Satellites] Failed to fetch {url}: {exc}")
        return {}

    group_results = await asyncio.gather(*[fetch_group(u) for u in TLE_GROUP_URLS])
    for gr in group_results:
        tle_master.update(gr)

    logger.info(f"[Satellites] Loaded {len(tle_master)} TLEs from group files")

    now_utc = datetime.now(timezone.utc)
    jd_now = now_utc.timestamp() / 86400.0 + 2440587.5

    results = []
    missing_norads = []

    for sat_info in SATELLITE_CATALOGUE:
        norad = sat_info["norad"]
        tle_entry = tle_master.get(norad)
        if tle_entry is None:
            missing_norads.append(sat_info)
            continue
        _, tle1, tle2 = tle_entry
        try:
            sat_rec = Satrec.twoline2rv(tle1, tle2)
            jd_whole = math.floor(jd_now)
            jd_frac = jd_now - jd_whole
            e, r, v = sat_rec.sgp4(jd_whole, jd_frac)
            if e != 0 or r[0] is None:
                continue
            lat, lon, alt_km = eci_to_geodetic(r, jd_now)
            speed_kms = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
            ground_track = compute_ground_track(sat_rec, jd_now)
            bbox = SOUTH_ASIA_BBOX
            over_region = (bbox["lat_min"] <= lat <= bbox["lat_max"] and bbox["lon_min"] <= lon <= bbox["lon_max"])
            results.append({
                "name": sat_info["name"], "norad": norad, "country": sat_info["country"],
                "type": sat_info["type"], "role": sat_info["role"],
                "colour": COUNTRY_COLOURS.get(sat_info["country"], "#8899AA"),
                "lat": round(lat, 3), "lon": round(lon, 3),
                "altitude_km": round(alt_km, 1), "speed_kms": round(speed_kms, 2),
                "period_min": round(2 * math.pi * (alt_km + 6371) ** 1.5 / math.sqrt(398600.4 * (alt_km + 6371)) / 60, 1),
                "ground_track": ground_track, "over_south_asia": over_region,
                "computed_at": now_utc.isoformat() + "Z",
            })
        except Exception as exc:
            logger.warning(f"[Satellites] Position error for {sat_info['name']}: {exc}")

    if missing_norads:
        for sat_info in missing_norads[:5]:
            try:
                url = CELESTRAK_SINGLE_URL.format(norad=sat_info["norad"])
                r = await client.get(url, timeout=10.0)
                if r.status_code == 200 and r.text.strip():
                    parsed = parse_tle_text(r.text)
                    norad = sat_info["norad"]
                    if norad not in parsed and parsed:
                        norad = next(iter(parsed))
                    if norad in parsed:
                        _, tle1, tle2 = parsed[norad]
                        sat_rec = Satrec.twoline2rv(tle1, tle2)
                        jd_whole = math.floor(jd_now)
                        jd_frac = jd_now - jd_whole
                        e, r_vec, v = sat_rec.sgp4(jd_whole, jd_frac)
                        if e == 0:
                            lat, lon, alt_km = eci_to_geodetic(r_vec, jd_now)
                            speed_kms = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
                            bbox = SOUTH_ASIA_BBOX
                            results.append({
                                "name": sat_info["name"], "norad": sat_info["norad"],
                                "country": sat_info["country"], "type": sat_info["type"],
                                "role": sat_info["role"],
                                "colour": COUNTRY_COLOURS.get(sat_info["country"], "#8899AA"),
                                "lat": round(lat, 3), "lon": round(lon, 3),
                                "altitude_km": round(alt_km, 1), "speed_kms": round(speed_kms, 2),
                                "period_min": round(2 * math.pi * (alt_km + 6371)**1.5 / math.sqrt(398600.4 * (alt_km + 6371)) / 60, 1),
                                "ground_track": compute_ground_track(sat_rec, jd_now),
                                "over_south_asia": (bbox["lat_min"] <= lat <= bbox["lat_max"] and bbox["lon_min"] <= lon <= bbox["lon_max"]),
                                "computed_at": now_utc.isoformat() + "Z",
                            })
            except Exception as exc:
                logger.debug(f"[Satellites] Individual query failed for {sat_info['name']}: {exc}")

    over_count = sum(1 for s in results if s.get("over_south_asia"))
    logger.info(f"[Satellites] {len(results)} satellites computed, {over_count} over South Asia")
    return results
