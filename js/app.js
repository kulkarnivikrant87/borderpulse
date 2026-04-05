// app.js — Main init, refresh orchestration, module wiring
// Border Pulse v1.1 | South Asia Geopolitical Intelligence Dashboard

(async () => {
  console.log('[BorderPulse] Initialising v1.1...');

  if (document.readyState === 'loading') {
    await new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve));
  }

  updateLastUpdatedLabel('Initialising...');

  // 1. Ticker
  TickerModule.init();

  // 2. Map
  try {
    MapModule.init();
    console.log('[BorderPulse] Map loaded');
  } catch (err) {
    console.error('[BorderPulse] Map init failed:', err);
  }

  // 2a. Aviation layer
  try {
    const map = MapModule.getMap();
    if (map) {
      const aviationLayer = AviationModule.init(map, null);
      const aviationLabel = `<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">✈ Aviation <span id="aviation-count" style="color:var(--text-dim);font-size:10px;margin-left:4px;font-family:'JetBrains Mono',monospace;">—</span></span>`;
      MapModule.addOverlay(aviationLabel, aviationLayer, false);
      console.log('[BorderPulse] Aviation module loaded');
    }
  } catch (err) {
    console.error('[BorderPulse] Aviation init failed:', err);
  }

  // 2b. Naval layer
  try {
    const map = MapModule.getMap();
    if (map) {
      const { vesselLayer, zoneLayer } = NavalModule.init(map, null);
      const vesselLabel = `<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">⚓ Naval Vessels <span id="naval-count" style="color:var(--text-dim);font-size:10px;margin-left:4px;font-family:'JetBrains Mono',monospace;">—</span></span>`;
      const zoneLabel   = `<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">⚔️ Strategic Zones</span>`;
      MapModule.addOverlay(vesselLabel, vesselLayer, false);
      MapModule.addOverlay(zoneLabel,   zoneLayer,   false);
      console.log('[BorderPulse] Naval module loaded');
    }
  } catch (err) {
    console.error('[BorderPulse] Naval init failed:', err);
  }

  // 2c. Satellite layer
  try {
    const map = MapModule.getMap();
    if (map) {
      const { satLayer, trackLayer } = SatelliteModule.init(map, null);
      const satLabel   = `<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">🛰️ Satellites <span id="sat-count" style="color:var(--text-dim);font-size:10px;margin-left:4px;font-family:'JetBrains Mono',monospace;">—</span></span>`;
      const trackLabel = `<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:#445577;">··· Ground Tracks</span>`;
      MapModule.addOverlay(satLabel,   satLayer,   false);
      MapModule.addOverlay(trackLabel, trackLayer, false);
      console.log('[BorderPulse] Satellite module loaded');
    }
  } catch (err) {
    console.error('[BorderPulse] Satellite init failed:', err);
  }

  // 3. Tension
  try {
    await TensionModule.init();
    TensionModule.startAutoRefresh();
    console.log('[BorderPulse] Tension module loaded');
  } catch (err) {
    console.error('[BorderPulse] Tension init failed:', err);
  }

  // 4. News
  try {
    await NewsModule.init();
    NewsModule.startAutoRefresh();
    console.log('[BorderPulse] News module loaded');
  } catch (err) {
    console.error('[BorderPulse] News init failed:', err);
  }

  // 5. AI Summaries
  try {
    await SummaryModule.init();
    SummaryModule.startAutoRefresh();
    console.log('[BorderPulse] Summary module loaded');
  } catch (err) {
    console.error('[BorderPulse] Summary init failed:', err);
  }

  // 6. Economic panel
  try {
    await EconomicModule.init();
    EconomicModule.startAutoRefresh();
    console.log('[BorderPulse] Economic module loaded');
  } catch (err) {
    console.error('[BorderPulse] Economic init failed:', err);
  }

  // 7. Theatre selector
  setupTheatreSelector();

  // 8. Backend health check
  checkBackendHealth();

  console.log('[BorderPulse] All modules loaded. Dashboard operational.');
  updateLastUpdatedLabel();

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      console.log('[BorderPulse] Tab refocused — refreshing data');
      TensionModule.init();
      NewsModule.init();
    }
  });
})();

function setupTheatreSelector() {
  const selector = document.getElementById('theatre-selector');
  if (!selector) return;

  selector.innerHTML = '';
  CONFIG.THEATRES.forEach((theatre, i) => {
    const btn = document.createElement('button');
    btn.className = `theatre-btn ${i === 0 ? 'active' : ''}`;
    btn.dataset.theatre = theatre;
    btn.title = CONFIG.THEATRE_LABELS[theatre];
    btn.innerHTML = `
      <span class="theatre-btn-dot" style="background:${CONFIG.THEATRE_COLOURS[theatre]};"></span>
      <span class="theatre-btn-label">${CONFIG.THEATRE_SHORT[theatre]}</span>
      <span class="theatre-btn-score font-data">—</span>
    `;

    btn.addEventListener('click', () => {
      document.querySelectorAll('.theatre-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      panMapToTheatre(theatre);
    });

    selector.appendChild(btn);
  });
}

function panMapToTheatre(theatre) {
  const centres = {
    loc:        [34.2, 75.0],
    lac:        [33.5, 79.5],
    bangladesh: [24.5, 90.5],
    naval:      [15.0, 80.0],
  };
  const zooms = {
    loc: 6, lac: 6, bangladesh: 7, naval: 5,
  };
  const map = MapModule.getMap();
  if (map && centres[theatre]) {
    map.flyTo(centres[theatre], zooms[theatre] || 6, { duration: 1.2 });
  }
}

async function checkBackendHealth() {
  try {
    const r = await fetch(`${CONFIG.API_BASE_URL}/health`, { signal: AbortSignal.timeout(5000) });
    if (r.ok) {
      const data = await r.json();
      console.log('[BorderPulse] Backend healthy:', data);
    } else {
      console.warn('[BorderPulse] Backend health check failed:', r.status);
      showBackendWarning();
    }
  } catch {
    console.warn('[BorderPulse] Backend unreachable — running in offline mode');
    showBackendWarning();
  }
}

function showBackendWarning() {
  const el = document.getElementById('backend-status');
  if (el) {
    el.textContent = '⚠ BACKEND OFFLINE';
    el.style.color = 'var(--accent-amber)';
    el.style.display = 'inline';
  }
}

function updateLastUpdatedLabel(override) {
  const el = document.getElementById('last-updated');
  if (!el) return;
  if (override) {
    el.textContent = override.toUpperCase();
    return;
  }
  const now = new Date();
  el.textContent = `UPDATED ${now.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: false })} AEST`;
}
