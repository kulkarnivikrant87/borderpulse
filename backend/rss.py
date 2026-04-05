"""
rss.py — RSS feed parser + deduplicator
Border Pulse v1.0

Fetches RSS feeds from configured sources and normalises them to the same
article format used by the GDELT module.
"""

import feedparser
import httpx
import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# RSS source list (mirrors data/sources.json)
RSS_SOURCES = [
    {"domain": "thehindu.com",    "name": "The Hindu",       "flag": "🇮🇳", "state_media": False,
     "url": "https://www.thehindu.com/feeder/default.rss",
     "theatres": ["loc", "lac", "bangladesh", "naval"]},

    {"domain": "ndtv.com",        "name": "NDTV",            "flag": "🇮🇳", "state_media": False,
     "url": "https://feeds.feedburner.com/ndtvnews-top-stories",
     "theatres": ["loc", "lac", "bangladesh", "naval"]},

    {"domain": "dawn.com",        "name": "Dawn",            "flag": "🇵🇰", "state_media": False,
     "url": "https://www.dawn.com/feeds/home",
     "theatres": ["loc", "naval"]},

    {"domain": "geo.tv",          "name": "Geo News",        "flag": "🇵🇰", "state_media": False,
     "url": "https://www.geo.tv/rss/1",
     "theatres": ["loc", "naval"]},

    {"domain": "thedailystar.net","name": "Daily Star BD",   "flag": "🇧🇩", "state_media": False,
     "url": "https://www.thedailystar.net/frontpage/rss.xml",
     "theatres": ["bangladesh"]},

    {"domain": "xinhuanet.com",   "name": "Xinhua",          "flag": "🇨🇳", "state_media": True,
     "url": "http://www.xinhuanet.com/english/rss/worldrss.xml",
     "theatres": ["lac", "bangladesh", "naval"]},

    {"domain": "globaltimes.cn",  "name": "Global Times",    "flag": "🇨🇳", "state_media": True,
     "url": "https://www.globaltimes.cn/rss/outbrain.xml",
     "theatres": ["lac", "naval"]},

    {"domain": "ptv.com.pk",      "name": "PTV News",        "flag": "🇵🇰", "state_media": True,
     "url": "https://www.ptv.com.pk/feed/",
     "theatres": ["loc"]},

    {"domain": "thewire.in",      "name": "The Wire",        "flag": "🇮🇳", "state_media": False,
     "url": "https://thewire.in/feed",
     "theatres": ["loc", "lac", "bangladesh"]},

    {"domain": "aljazeera.com",   "name": "Al Jazeera Asia", "flag": "🇶🇦", "state_media": False,
     "url": "https://www.aljazeera.com/xml/rss/all.xml",
     "theatres": ["loc", "lac", "bangladesh", "naval"]},
]

THEATRE_KEYWORDS = {
    "loc":        ["india pakistan", "line of control", "kashmir", "loc", "siachen", "ceasefire violation"],
    "lac":        ["india china", "line of actual control", "lac", "ladakh", "arunachal", "galwan", "depsang"],
    "bangladesh": ["india bangladesh", "bengal border", "siliguri", "rohingya", "bsf", "bgb"],
    "naval":      ["bay of bengal", "arabian sea", "strait of hormuz", "gwadar", "naval", "ins ", "pns "],
}


async def fetch_rss_for_theatre(
    theatre: str,
    client: Optional[httpx.AsyncClient] = None,
    max_per_source: int = 10,
) -> List[Dict]:
    """
    Fetch and parse RSS feeds relevant to the given theatre.
    Returns normalised article dicts.
    """
    sources = [s for s in RSS_SOURCES if theatre in s.get("theatres", [])]
    keywords = THEATRE_KEYWORDS.get(theatre, [])

    results = []
    seen_urls = set()
    seen_titles = set()

    should_close = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        should_close = True

    for source in sources:
        try:
            resp = await client.get(source["url"])
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            count = 0
            for entry in feed.entries:
                if count >= max_per_source:
                    break

                title = entry.get("title", "").strip()
                url   = entry.get("link", "").strip()

                if not title or not url:
                    continue

                # Keyword filter — only include if relevant to theatre
                title_lower = title.lower()
                summary_lower = entry.get("summary", "").lower()
                combined = title_lower + " " + summary_lower

                relevant = any(kw in combined for kw in keywords)
                # RSS feeds are broader — include all for source-specific feeds
                # but always keyword-filter general feeds (Al Jazeera, Xinhua)
                if source["domain"] in ("aljazeera.com", "xinhuanet.com", "globaltimes.cn"):
                    if not relevant:
                        continue

                # Dedup
                url_hash = hashlib.md5(url.encode()).hexdigest()
                title_key = title[:60].lower()
                if url_hash in seen_urls or title_key in seen_titles:
                    continue
                seen_urls.add(url_hash)
                seen_titles.add(title_key)

                # Parse date
                published = ""
                if entry.get("published_parsed"):
                    try:
                        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        published = dt.isoformat()
                    except Exception:
                        pass

                results.append({
                    "url":          url,
                    "title":        title,
                    "domain":       source["domain"],
                    "seendate":     published,
                    "tone":         0,  # RSS has no tone score
                    "sourcecountry": "",
                    "language":     "English",
                    "theatre":      theatre,
                    "_sourceCount": 1,
                    "_state_media": source.get("state_media", False),
                    "_source_name": source["name"],
                    "_source_flag": source["flag"],
                    "_source":      "rss",
                })
                count += 1

        except Exception as e:
            logger.warning(f"[RSS] Failed to fetch {source['name']}: {e}")
            continue

    if should_close:
        await client.aclose()

    logger.info(f"[RSS] {theatre}: fetched {len(results)} articles from {len(sources)} sources")
    return results


def deduplicate_articles(articles: List[Dict]) -> List[Dict]:
    """
    Deduplicate a list of articles by URL and title similarity.
    Collapsed articles get a _sourceCount > 1.
    """
    by_url: Dict[str, Dict] = {}
    by_title: Dict[str, Dict] = {}

    for a in articles:
        url = a.get("url", "")
        if not url:
            continue

        url_hash = hashlib.md5(url.encode()).hexdigest()
        title_key = (a.get("title") or "")[:60].lower().strip()

        if url_hash in by_url:
            by_url[url_hash]["_sourceCount"] += 1
            continue

        if title_key and title_key in by_title:
            by_title[title_key]["_sourceCount"] += 1
            continue

        a["_sourceCount"] = a.get("_sourceCount", 1)
        by_url[url_hash] = a
        if title_key:
            by_title[title_key] = a

    return list(by_url.values())
