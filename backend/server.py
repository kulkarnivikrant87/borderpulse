"""
server.py -- FastAPI server (CORS proxy + in-memory caching)
Border Pulse v1.1

Endpoints:
  GET /health                  -- health check
  GET /api/news/{theatre}      -- GDELT + RSS articles (cached 15 min)
  GET /api/tension/{theatre}   -- tension score (cached 15 min)
  GET /api/summary/{theatre}   -- Claude Haiku summary (cached 60 min)
  GET /api/economic            -- currency + Brent crude (cached 30 min)
  GET /api/flashpoints         -- flashpoints.json with live status
  GET /api/aviation            -- real-time aircraft via OpenSky (cached 3 min)
  GET /api/naval               -- naval vessels + strategic zones (cached 5 min)
  GET /api/satellites          -- satellite positions via Celestrak+sgp4 (cached 10 min)

Run locally:
  uvicorn server:app --reload --port 8000

Deploy to Railway:
  Start command: uvicorn server:app --host 0.0.0.0 --port $PORT
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from gdelt import fetch_theatre_articles
from rss import fetch_rss_for_theatre, deduplicate_articles
from tension_engine import calculate_tension
from ai_summary import generate_summary, get_summary_history, init_db
from aviation import fetch_aviation
from naval import fetch_naval
from satellites import fetch_satellites

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("borderpulse")

CORS_ORIGIN = os.getenv("CORS_ORIGIN", "*")
PORT = int(os.getenv("PORT", 8000))
THEATRES = ["loc", "lac", "bangladesh", "naval"]

app = FastAPI(title="Border Pulse API", description="CORS proxy and intelligence aggregation backend.", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[CORS_ORIGIN] if CORS_ORIGIN != "*" else ["*"], allow_credentials=True, allow_methods=["GET"], allow_headers=["*"])

_cache: Dict[str, Dict[str, Any]] = {}

TTL = {
    "news":        15 * 60,
    "tension":     15 * 60,
    "summary":     60 * 60,
    "economic":    30 * 60,
    "flashpoints":  5 * 60,
    "aviation":     3 * 60,
    "naval":        5 * 60,
    "satellites":  10 * 60,
}


def cache_get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry and time.time() < entry["expires"]:
        return entry["data"]
    return None


def cache_set(key: str, data: Any, ttl_seconds: int):
    _cache[key] = {"data": data, "expires": time.time() + ttl_seconds}


@app.on_event("startup")
async def startup():
    logger.info("Border Pulse API v1.1 starting up...")
    try:
        init_db()
        logger.info("SQLite summary database initialised")
    except Exception as e:
        logger.error(f"DB init failed: {e}")


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z", "version": "1.1.0", "theatres": THEATRES}


@app.get("/api/news/{theatre}")
async def get_news(theatre: str):
    if theatre not in THEATRES:
        raise HTTPException(status_code=404, detail=f"Unknown theatre: {theatre}")
    cache_key = f"news_{theatre}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            gdelt_articles = await fetch_theatre_articles(theatre, client=client)
            rss_articles = await fetch_rss_for_theatre(theatre, client=client)
        combined = gdelt_articles + rss_articles
        deduplicated = deduplicate_articles(combined)
        deduplicated.sort(key=lambda a: a.get("seendate") or a.get("published") or "", reverse=True)
        articles = deduplicated[:20]
        result = {"theatre": theatre, "articles": articles, "count": len(articles), "fetched_at": datetime.utcnow().isoformat() + "Z"}
        cache_set(cache_key, result, TTL["news"])
        return result
    except Exception as e:
        logger.error(f"[News] Error for {theatre}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/tension/{theatre}")
async def get_tension(theatre: str):
    if theatre not in THEATRES:
        raise HTTPException(status_code=404, detail=f"Unknown theatre: {theatre}")
    cache_key = f"tension_{theatre}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        news_cached = cache_get(f"news_{theatre}")
        articles = news_cached["articles"] if news_cached else []
        if not articles:
            async with httpx.AsyncClient(timeout=15.0) as client:
                articles = await fetch_theatre_articles(theatre, client=client)
        polymarket_prob = 0.5
        try:
            async with httpx.AsyncClient(timeout=5.0) as pm_client:
                pm_resp = await pm_client.get("https://clob.polymarket.com/markets", params={"tag": "south-asia-conflict"}, timeout=5.0)
                if pm_resp.status_code == 200:
                    pm_data = pm_resp.json()
                    if pm_data and isinstance(pm_data, list):
                        prices = [float(m.get("last_trade_price", 0.5)) for m in pm_data[:3]]
                        if prices:
                            polymarket_prob = sum(prices) / len(prices)
        except Exception:
            pass
        result = calculate_tension(articles, theatre, polymarket_prob)
        cache_set(cache_key, result, TTL["tension"])
        return result
    except Exception as e:
        logger.error(f"[Tension] Error for {theatre}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/summary/{theatre}")
async def get_summary(theatre: str):
    if theatre not in THEATRES:
        raise HTTPException(status_code=404, detail=f"Unknown theatre: {theatre}")
    cache_key = f"summary_{theatre}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        news_cached = cache_get(f"news_{theatre}")
        articles = news_cached["articles"][:10] if news_cached else []
        tension_cached = cache_get(f"tension_{theatre}")
        tension_score = tension_cached["score"] if tension_cached else 50
        avg_tone = sum(float(a.get("tone", 0) or 0) for a in articles) / len(articles) if articles else 0.0
        result = await generate_summary(theatre, articles, tension_score, avg_tone)
        cache_set(cache_key, result, TTL["summary"])
        return result
    except Exception as e:
        logger.error(f"[Summary] Error for {theatre}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/summary/{theatre}/history")
async def get_summary_history_endpoint(theatre: str, hours: int = 48):
    if theatre not in THEATRES:
        raise HTTPException(status_code=404, detail=f"Unknown theatre: {theatre}")
    return {"theatre": theatre, "history": get_summary_history(theatre, hours)}


@app.get("/api/economic")
async def get_economic():
    cache_key = "economic"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        pairs = {"INR_USD": "INRUSD=X", "PKR_USD": "PKRUSD=X", "BDT_USD": "BDTUSD=X", "BRENT": "BZ=F"}
        result = {}
        async with httpx.AsyncClient(timeout=10.0) as client:
            for pair_id, ticker in pairs.items():
                try:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                    r = await client.get(url, params={"interval": "1d", "range": "2d"})
                    if r.status_code == 200:
                        data = r.json()
                        meta = data.get("chart", {}).get("result", [{}])[0].get("meta", {})
                        value = meta.get("regularMarketPrice")
                        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                        if value is not None:
                            result[pair_id] = {"value": value, "change_pct": ((value - prev) / prev * 100) if prev else None}
                        else:
                            result[pair_id] = {"value": None, "change_pct": None}
                except Exception as ex:
                    logger.warning(f"[Economic] Failed {ticker}: {ex}")
                    result[pair_id] = {"value": None, "change_pct": None}
        result["fetched_at"] = datetime.utcnow().isoformat() + "Z"
        cache_set(cache_key, result, TTL["economic"])
        return result
    except Exception as e:
        logger.error(f"[Economic] Error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/flashpoints")
async def get_flashpoints():
    cache_key = "flashpoints"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        data_path = Path(__file__).parent.parent / "data" / "flashpoints.json"
        if data_path.exists():
            with open(data_path) as f:
                data = json.load(f)
        else:
            raise FileNotFoundError(f"flashpoints.json not found at {data_path}")
        for feature in data.get("features", []):
            theatre = feature["properties"].get("theatre", "").lower().replace("-", "")
            theatre_id = None
            if "pakistan" in theatre: theatre_id = "loc"
            elif "china" in theatre:  theatre_id = "lac"
            elif "bangladesh" in theatre: theatre_id = "bangladesh"
            elif "naval" in theatre:  theatre_id = "naval"
            if theatre_id:
                tension_cached = cache_get(f"tension_{theatre_id}")
                if tension_cached:
                    feature["properties"]["live_tension"] = tension_cached["score"]
        data["fetched_at"] = datetime.utcnow().isoformat() + "Z"
        cache_set(cache_key, data, TTL["flashpoints"])
        return data
    except Exception as e:
        logger.error(f"[Flashpoints] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/aviation")
async def get_aviation():
    cache_key = "aviation"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            aircraft = await fetch_aviation(client)
        result = {
            "aircraft": aircraft, "count": len(aircraft),
            "military": sum(1 for a in aircraft if a.get("military")),
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source": "OpenSky Network",
            "bbox": {"lat": "5-45N", "lon": "55-105E"},
        }
        cache_set(cache_key, result, TTL["aviation"])
        return result
    except Exception as e:
        logger.error(f"[Aviation] Endpoint error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/naval")
async def get_naval():
    cache_key = "naval"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            result = await fetch_naval(client)
        cache_set(cache_key, result, TTL["naval"])
        return result
    except Exception as e:
        logger.error(f"[Naval] Endpoint error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/satellites")
async def get_satellites():
    cache_key = "satellites"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            sats = await fetch_satellites(client)
        result = {
            "satellites": sats, "count": len(sats),
            "over_region": sum(1 for s in sats if s.get("over_south_asia")),
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "source": "Celestrak + sgp4",
            "region": "South Asia + Indian Ocean",
        }
        cache_set(cache_key, result, TTL["satellites"])
        return result
    except Exception as e:
        logger.error(f"[Satellites] Endpoint error: {e}")
        raise HTTPException(status_code=502, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
