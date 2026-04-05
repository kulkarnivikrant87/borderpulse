// aviation.js — Real-time aviation layer (OpenSky Network)
// Border Pulse v1.1 | South Asia Geopolitical Intelligence Dashboard

const AviationModule = (() => {
  let aviationLayer = null;
  let allAircraft = [];
  let showMilitaryOnly = false;
  let refreshTimer = null;

  const REFRESH_INTERVAL = CONFIG.REFRESH_INTERVAL_NEWS || 3 * 60 * 1000; // 3 min

  // Country colour coding
  const COUNTRY_COLOURS = {
    'India':          '#FF9933',
    'Pakistan':       '#01411C',
    'China':          '#DE2910',
    'United States':  '#3C3B6E',
    'Bangladesh':     '#006A4E',
    'Sri Lanka':      '#8D153A',
    'Nepal':          '#003893',
    'Iran':           '#239F40',
    'Oman':           '#DB161B',
    'United Arab Emirates': '#009A44',
    'Saudi Arabia':   '#006C35',
  };

  const DEFAULT_COLOUR = '#8899AA';

  function countryColour(country) {
    return COUNTRY_COLOURS[country] || DEFAULT_COLOUR;
  }

  // Plane SVG icon (rotated to heading)
  function planeIcon(heading, colour, isMilitary) {
    const size = isMilitary ? 22 : 18;
    const glowColour = isMilitary ? '#E63946' : colour;
    const glowPx = isMilitary ? 6 : 3;
    return L.divIcon({
      className: '',
      html: `
        <div style="
          width:${size}px; height:${size}px;
          transform: rotate(${heading}deg);
          filter: drop-shadow(0 0 ${glowPx}px ${glowColour});
        ">
          <svg viewBox="0 0 24 24" fill="${colour}" xmlns="http://www.w3.org/2000/svg"
               style="width:100%;height:100%;">
            <path d="M12 2L8 10H4l2 2h2l-1 8h2l3-4 3 4h2l-1-8h2l2-2h-4L12 2z"
                  stroke="${isMilitary ? '#fff' : 'rgba(255,255,255,0.4)'}"
                  stroke-width="${isMilitary ? 0.8 : 0.4}"/>
          </svg>
        </div>
      `,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -size / 2],
    });
  }

  // Popup HTML
  function buildPopup(a) {
    const altFt = a.altitude_ft ? `${a.altitude_ft.toLocaleString()} ft` : '—';
    const altM  = a.altitude_m  ? `${a.altitude_m.toLocaleString()} m`  : '';
    const spd   = a.speed_kts   ? `${a.speed_kts} kts` : '—';
    const hdg   = a.heading     ? `${a.heading}°` : '—';
    const milBadge = a.military
      ? `<span style="background:#E63946;color:#fff;font-size:9px;padding:2px 5px;border-radius:2px;margin-left:6px;font-family:Rajdhani,sans-serif;letter-spacing:0.08em;font-weight:700;">MILITARY</span>`
      : '';
    return `
      <div class="bp-popup">
        <div class="bp-popup-header">
          <div>
            <div class="bp-popup-name">${a.flag || ''} ${a.callsign}</div>
            <div class="bp-popup-theatre">${a.country} ${milBadge}</div>
          </div>
          <span class="status-badge ${a.military ? 'active' : 'monitoring'}"
                style="font-size:9px;padding:2px 6px;">${a.category || 'Civil'}</span>
        </div>
        <div class="bp-popup-body">
          <div class="bp-popup-description" style="font-size:11px;line-height:1.6;">
            <span style="color:var(--text-dim);">ALT</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${altFt}</span>
            <span style="color:var(--text-dim);font-size:10px;margin-left:2px;">${altM}</span>
            <br>
            <span style="color:var(--text-dim);">SPD</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${spd}</span>
            &nbsp;&nbsp;
            <span style="color:var(--text-dim);">HDG</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${hdg}</span>
            <br>
            <span style="color:var(--text-dim);">ICAO</span>
            <span class="font-data" style="color:var(--text-secondary);margin-left:4px;font-size:10px;">${a.icao24 || '—'}</span>
            ${a.squawk ? `&nbsp;&nbsp;<span style="color:var(--text-dim);">SQK</span> <span class="font-data" style="color:var(--accent-amber);margin-left:4px;font-size:10px;">${a.squawk}</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }

  // Render layer
  function renderLayer(aircraft) {
    if (!aviationLayer) return;
    aviationLayer.clearLayers();
    const toShow = showMilitaryOnly ? aircraft.filter(a => a.military) : aircraft;
    toShow.forEach(a => {
      if (!a.lat || !a.lon) return;
      const colour = countryColour(a.country);
      const icon   = planeIcon(a.heading || 0, colour, a.military);
      const marker = L.marker([a.lat, a.lon], { icon });
      marker.bindPopup(buildPopup(a), { maxWidth: 260, className: 'bp-map-popup' });
      aviationLayer.addLayer(marker);
    });
  }

  // Fetch & update
  async function fetchAndRender() {
    try {
      const resp = await fetch(`${CONFIG.API_BASE_URL}/api/aviation`,
        { signal: AbortSignal.timeout(30000) });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      allAircraft = data.aircraft || [];
      renderLayer(allAircraft);
      updateAviationBadge(data.count, data.military);
      console.log(`[Aviation] ${data.count} aircraft (${data.military} military)`);
    } catch (err) {
      console.warn('[Aviation] Fetch failed:', err.message);
    }
  }

  // Badge on layer control
  function updateAviationBadge(total, military) {
    const el = document.getElementById('aviation-count');
    if (el) el.textContent = `${total} (${military} MIL)`;
  }

  // Military toggle
  function setMilitaryOnly(milOnly) {
    showMilitaryOnly = milOnly;
    renderLayer(allAircraft);
  }

  // Init
  function init(map, layerControlOverlays) {
    aviationLayer = L.layerGroup();
    const label = `
      <span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">
        ✈ Aviation
        <span id="aviation-count" style="color:var(--text-dim);font-size:10px;margin-left:4px;font-family:JetBrains Mono,monospace;">—</span>
      </span>
    `;
    if (layerControlOverlays) layerControlOverlays[label] = aviationLayer;
    fetchAndRender();
    refreshTimer = setInterval(fetchAndRender, REFRESH_INTERVAL);
    return aviationLayer;
  }

  function destroy() {
    if (refreshTimer) clearInterval(refreshTimer);
  }

  return { init, setMilitaryOnly, fetchAndRender, destroy };
})();
