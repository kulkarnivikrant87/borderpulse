# 🛰 Border Pulse

**South Asia Geopolitical Intelligence Dashboard**

Real-time OSINT aggregator monitoring four active geopolitical theatres simultaneously:

| Theatre | Border Zone | Primary Signal |
|---------|-------------|----------------|
| India–Pakistan | Line of Control (LoC) | Ceasefire violations, airspace, nuclear posture |
| India–China | Line of Actual Control (LAC) | Infrastructure, patrol standoffs, Shaksgam Valley |
| India–Bangladesh | Eastern frontier | Border fencing, trade, minority incidents, China footprint |
| Bay of Bengal / Naval | Arabian Sea + BoB | Chinese port activity, naval visits, Strait of Hormuz |

---

## Features (Phase 1 MVP)

- **Interactive Border Map** — Leaflet.js with CartoDB Dark Matter tiles, 4 colour-coded border zones, 9 pulsing flashpoint markers with popups
- **Live Intelligence Feed** — GDELT DOC 2.0 API + RSS aggregation, deduplication, tone scoring, state media labelling
- **Tension Meter** — Composite 0–100 score per theatre (news volume + tone + incidents + diplomacy + Polymarket), animated SVG gauges
- **AI Situation Briefings** — Claude Haiku 4.5 generates hourly 3-sentence analyst summaries per theatre with ESCALATING / STABLE / DE-ESCALATING status
- **Economic Signals** — INR/USD, PKR/USD, BDT/USD, Brent Crude via Yahoo Finance proxy
- **Breaking News Ticker** — Live scrolling feed at the bottom of the screen
- **FastAPI Backend** — CORS proxy, in-memory caching, SQLite summary history

---

## Project Structure

```
borderpulse/
├── index.html              ← Single page app entry point
├── css/
│   ├── main.css            ← Design system variables + base styles
│   ├── layout.css          ← Grid, panels, sidebar, topbar
│   ├── map.css             ← Leaflet overrides + custom map styles
│   └── components.css      ← Cards, badges, tension meters, tickers
├── js/
│   ├── config.js           ← API settings (placeholders only)
│   ├── map.js              ← Leaflet map init, borders, incident pins
│   ├── news.js             ← GDELT + RSS fetch, dedup, render
│   ├── tension.js          ← Tension score calculation + gauge render
│   ├── summary.js          ← Claude Haiku API call + summary display
│   ├── economic.js         ← Yahoo Finance proxy + currency display
│   ├── ticker.js           ← Breaking news bottom ticker
│   └── app.js              ← Main init, refresh orchestration
├── data/
│   ├── borders.geojson     ← LoC, LAC, India-BD border polygons
│   ├── flashpoints.json    ← Flashpoint locations + metadata
│   └── sources.json        ← RSS feed URLs, bias labels, country flags
├── backend/
│   ├── server.py           ← FastAPI server (CORS proxy + caching)
│   ├── gdelt.py            ← GDELT API wrapper
│   ├── rss.py              ← RSS feed parser + deduplicator
│   ├── tension_engine.py   ← Composite tension score algorithm
│   ├── ai_summary.py       ← Claude Haiku API integration
│   ├── requirements.txt    ← Python dependencies
│   └── .env.example        ← Environment variable template
└── README.md
```

---

## Quick Start (Local Development)

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY

pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

Backend will be running at `http://localhost:8000`. Test it:
```bash
curl http://localhost:8000/health
# → {"status": "ok", ...}
```

### Frontend

No build step needed. Open `index.html` directly, or serve with any static server:

```bash
# Python
python -m http.server 3000

# Node
npx serve . -p 3000
```

Then visit `http://localhost:3000`.

The dashboard will connect to `http://localhost:8000` (set in `js/config.js`).

---

## Deployment

### Frontend → GitHub Pages

1. Create a public GitHub repo named `borderpulse`
2. Push all files (everything except `backend/`)
3. Go to repo Settings → Pages → Source: Deploy from branch → main → / (root)
4. Update `CONFIG.API_BASE_URL` in `js/config.js` to your Railway backend URL before pushing
5. Dashboard will be live at `https://[username].github.io/borderpulse`

### Backend → Railway.app

1. Log in to [railway.app](https://railway.app) with your existing account
2. New Project → Deploy from GitHub repo → select `borderpulse`
3. In project settings:
   - Root directory: `backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
4. In Variables tab, add:
   - `ANTHROPIC_API_KEY` = your key from platform.anthropic.com
   - `CORS_ORIGIN` = `https://[username].github.io`
5. Deploy — Railway auto-builds from GitHub

**Cost estimate:** Railway free tier ($5/month credit) + Anthropic Haiku (~$0.05–0.50/month) = effectively $0/month.

---

## Acceptance Testing Checklist

Before declaring Phase 1 complete:

- [ ] Map loads — dark map centred on South Asia, 4 border zones visible
- [ ] Flashpoint markers — 9 pulsing markers at correct locations
- [ ] Marker popup — click on Siachen → popup shows name, status, description
- [ ] Layer toggle — toggle switches show/hide borders correctly
- [ ] News feed loads — at least 10 articles appear on first load
- [ ] News refresh — new articles appear after 15 minutes without page reload
- [ ] Theatre filter — clicking LoC shows only LoC articles
- [ ] State media badge — Xinhua articles show '⚠️ State Media' badge
- [ ] Tension meter — 4 gauges render with animated needles
- [ ] Tension score — score changes after news refresh cycle
- [ ] AI summary — Claude Haiku generates 3-sentence summary per theatre
- [ ] Summary status badge — ESCALATING / STABLE / DE-ESCALATING badge appears
- [ ] API cache — second page load returns cached data (check Network tab)
- [ ] Mobile responsive — dashboard usable on 375px wide mobile screen
- [ ] Backend health — GET /health returns 200 OK

---

## Licence

MIT — open source. See [LICENSE](LICENSE).

---

## Disclaimer

> Border Pulse aggregates publicly available open-source intelligence (OSINT) data only. All tension scores are algorithmic estimates based on news volume and sentiment — not intelligence assessments. Information may be incomplete, delayed, or inaccurate. State-controlled media sources are clearly labelled. This tool has no affiliation with any government, military, or intelligence organisation. Not intended for operational use.

---

*Built by Vikrant Kulkarni — April 2026*
