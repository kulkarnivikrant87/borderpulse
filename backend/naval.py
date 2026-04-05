"""
naval.py -- Naval vessel tracking for Border Pulse v1.1
Sources:
  1. MarineTraffic public tile API (best-effort, no key)
  2. VesselFinder public endpoint (fallback)
  3. Known Indian Ocean strategic zones (always returned)
"""

import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger("borderpulse.naval")

STRATEGIC_ZONES = [
    {"id": "strait_hormuz", "name": "Strait of Hormuz", "lat": 26.57, "lon": 56.39, "type": "chokepoint", "threat": "elevated", "description": "~20% global oil transits here. Iran-US tension flash-point.", "country": "Multi"},
    {"id": "strait_malacca", "name": "Strait of Malacca", "lat": 2.50, "lon": 102.00, "type": "chokepoint", "threat": "monitoring", "description": "Busiest maritime lane. ~80% of China oil imports transit here.", "country": "Multi"},
    {"id": "diego_garcia", "name": "Diego Garcia (BIOT)", "lat": -7.31, "lon": 72.42, "type": "base", "threat": "active", "description": "US Navy / RAF joint base. B-2 capable runway.", "country": "USA/UK"},
    {"id": "karachi_naval", "name": "PNS Iqbal -- Karachi", "lat": 24.84, "lon": 67.01, "type": "naval_base", "threat": "monitoring", "description": "Pakistan Navy HQ. Agosta-class submarine base.", "country": "Pakistan"},
    {"id": "mumbai_naval", "name": "INS Shivaji -- Mumbai", "lat": 18.92, "lon": 72.82, "type": "naval_base", "threat": "active", "description": "Western Naval Command HQ. Carrier berthing.", "country": "India"},
    {"id": "visakhapatnam", "name": "HQENC -- Visakhapatnam", "lat": 17.70, "lon": 83.30, "type": "naval_base", "threat": "active", "description": "Eastern Naval Command HQ. Arihant-class SSBN base.", "country": "India"},
    {"id": "ins_kadamba", "name": "INS Kadamba -- Karwar", "lat": 14.81, "lon": 74.14, "type": "naval_base", "threat": "active", "description": "India largest naval base (Project Seabird). Deep-water submarine pens.", "country": "India"},
    {"id": "gwadar", "name": "Gwadar Deep-Sea Port", "lat": 25.12, "lon": 62.33, "type": "strategic_port", "threat": "elevated", "description": "CPEC terminus. China PLAN access agreement.", "country": "Pakistan/China"},
    {"id": "hambantota", "name": "Hambantota Port", "lat": 6.12, "lon": 81.10, "type": "strategic_port", "threat": "monitoring", "description": "99-year Chinese lease. Surveillance hub for Indian Ocean.", "country": "China (leased)"},
    {"id": "colombo", "name": "Port of Colombo", "lat": 6.93, "lon": 79.86, "type": "strategic_port", "threat": "monitoring", "description": "Major transshipment hub. Chinese submarine port-calls.", "country": "Sri Lanka"},
    {"id": "djibouti", "name": "PLA-N Overseas Base -- Djibouti", "lat": 11.59, "lon": 43.09, "type": "naval_base", "threat": "elevated", "description": "China first overseas military base. PLAN logistics hub.", "country": "China"},
    {"id": "bay_of_bengal_patrol", "name": "Bay of Bengal Patrol Zone", "lat": 12.00, "lon": 87.00, "type": "patrol_zone", "threat": "monitoring", "description": "IN Eastern Fleet area. Regular IN-USN MALABAR exercises.", "country": "India"},
]


def classify_vessel(type_name: str, ship_name: str) -> str:
    tn = (type_name or "").upper()
    sn = (ship_name or "").upper()
    if any(x in tn or x in sn for x in ["CARRIER", "CVN", "INS VIK"]):
        return "carrier"
    if any(x in tn for x in ["MILITARY", "WARSHIP", "DESTROYER", "FRIGATE", "CORVETTE", "CRUISER"]):
        return "warship"
    if any(x in tn or x in sn for x in ["SUBMARINE", "SSN", "SSK", "SSBN"]):
        return "submarine"
    if any(x in tn for x in ["PATROL", "COAST GUARD", "OPV"]):
        return "patrol"
    if "TANKER" in tn:
        return "tanker"
    if any(x in tn for x in ["CARGO", "CONTAINER", "BULK"]):
        return "cargo"
    return "merchant"


async def _try_marinetraffic(client: httpx.AsyncClient) -> list:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.marinetraffic.com/",
            "Accept": "application/json, text/javascript, */*",
        }
        resp = await client.get(
            "https://www.marinetraffic.com/getData/get_data_json_4/z:3/X:40/Y:12/station:0",
            headers=headers, timeout=12.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            rows = data.get("data", {}).get("rows", [])
            vessels = []
            for row in rows[:80]:
                lat = row.get("LAT")
                lon = row.get("LON")
                if lat is None or lon is None:
                    continue
                try:
                    lat, lon = float(lat), float(lon)
                except (ValueError, TypeError):
                    continue
                vtype = classify_vessel(row.get("TYPE_NAME", ""), row.get("SHIPNAME", ""))
                vessels.append({
                    "mmsi": row.get("MMSI"), "name": row.get("SHIPNAME") or "Unknown",
                    "lat": lat, "lon": lon, "speed": row.get("SPEED"),
                    "heading": row.get("HEADING"), "type": vtype,
                    "flag": row.get("FLAG"), "dest": row.get("DESTINATION"), "source": "AIS",
                })
            logger.info(f"[Naval] MarineTraffic: {len(vessels)} vessels")
            return vessels
    except Exception as exc:
        logger.debug(f"[Naval] MarineTraffic unavailable: {exc}")
    return []


async def _try_vesseltracking(client: httpx.AsyncClient) -> list:
    try:
        resp = await client.get(
            "https://www.myshiptracking.com/requests/vesselsonmap.php",
            params={"type": "vessels", "region": "5,55,30,105", "zoom": "3"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.myshiptracking.com/"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            vessels = []
            for item in (data if isinstance(data, list) else [])[:60]:
                lat = item.get("lat") or item.get("LAT")
                lon = item.get("lng") or item.get("LON") or item.get("lon")
                if not lat or not lon:
                    continue
                try:
                    lat, lon = float(lat), float(lon)
                except (ValueError, TypeError):
                    continue
                vtype = classify_vessel(item.get("type", ""), item.get("name", ""))
                vessels.append({
                    "mmsi": item.get("mmsi"), "name": item.get("name") or "Unknown",
                    "lat": lat, "lon": lon, "speed": item.get("speed"),
                    "heading": item.get("course"), "type": vtype, "source": "AIS",
                })
            logger.info(f"[Naval] VesselTracking: {len(vessels)} vessels")
            return vessels
    except Exception as exc:
        logger.debug(f"[Naval] VesselTracking unavailable: {exc}")
    return []


async def fetch_naval(client: httpx.AsyncClient) -> dict:
    """Fetch naval data -- vessels + strategic zones."""
    vessels = await _try_marinetraffic(client)
    if not vessels:
        vessels = await _try_vesseltracking(client)
    return {
        "vessels": vessels, "zones": STRATEGIC_ZONES,
        "vessel_count": len(vessels), "zone_count": len(STRATEGIC_ZONES),
        "has_ais": len(vessels) > 0,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "source": "AIS/MarineTraffic" if vessels else "strategic_zones_only",
    }
