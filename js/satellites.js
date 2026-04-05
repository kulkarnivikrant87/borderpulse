// satellites.js — Real-time satellite position layer (Celestrak + sgp4)
// Border Pulse v1.1 | South Asia Geopolitical Intelligence Dashboard

const SatelliteModule = (() => {
  let satLayer     = null;
  let trackLayer   = null;
  let refreshTimer = null;
  let allSats      = [];

  const REFRESH_INTERVAL = 10 * 60 * 1000; // 10 minutes

  const TYPE_ICONS = {
    SAR:        '📡',
    Optical:    '👁️',
    SIGINT:     '📻',
    ELINT:      '📻',
    NavIC:      '🛰️',
    Classified: '🔒',
    Station:    '🔩',
    Comms:      '📶',
  };

  const COUNTRY_COLOURS = {
    India:         '#FF9933',
    China:         '#DE2910',
    Pakistan:      '#01411C',
    USA:           '#3C3B6E',
    International: '#2EC4B6',
  };

  function hexToRgb(hex) {
    const m = (hex || '#888888').replace('#', '').match(/.{2}/g);
    if (!m) return '136,136,136';
    return m.map(x => parseInt(x, 16)).join(',');
  }

  function satelliteIcon(sat) {
    const colour = sat.colour || '#2EC4B6';
    const typeChar = TYPE_ICONS[sat.type] || '🛰️';
    const isOver = sat.over_south_asia;
    const size = isOver ? 26 : 20;
    const glowPx = isOver ? 8 : 3;
    return L.divIcon({
      className: '',
      html: `
        <div style="
          width:${size}px; height:${size}px;
          position:relative; display:flex;
          align-items:center; justify-content:center;
        ">
          ${isOver ? `<div style="
            position:absolute;
            width:${size}px; height:${size}px;
            border-radius:50%;
            border:1.5px solid ${colour};
            opacity:0;
            animation:pulse 2s ease-out infinite;
          "></div>` : ''}
          <div style="
            width:${size - 6}px; height:${size - 6}px;
            border-radius:3px;
            background:rgba(${hexToRgb(colour)},0.12);
            border:1.5px solid ${colour};
            display:flex; align-items:center; justify-content:center;
            font-size:${isOver ? 12 : 9}px; line-height:1;
            box-shadow: 0 0 ${glowPx}px ${colour};
            transform: rotate(-45deg);
          ">
            <span style="transform:rotate(45deg);">${typeChar}</span>
          </div>
        </div>
      `,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -size / 2],
    });
  }

  function drawGroundTrack(sat) {
    if (!trackLayer || !sat.ground_track || sat.ground_track.length < 2) return;
    const colour = sat.colour || '#2EC4B6';
    const opacity = sat.over_south_asia ? 0.7 : 0.25;
    const segments = [];
    let current = [sat.ground_track[0]];
    for (let i = 1; i < sat.ground_track.length; i++) {
      const prev = sat.ground_track[i - 1];
      const curr = sat.ground_track[i];
      if (Math.abs(curr[1] - prev[1]) > 180) {
        segments.push(current);
        current = [curr];
      } else {
        current.push(curr);
      }
    }
    segments.push(current);
    segments.forEach(seg => {
      if (seg.length < 2) return;
      L.polyline(seg, {
        color: colour,
        weight: sat.over_south_asia ? 1.5 : 0.8,
        opacity,
        dashArray: '4 6',
        interactive: false,
      }).addTo(trackLayer);
    });
  }

  function buildPopup(sat) {
    const colour = sat.colour || '#2EC4B6';
    const overBadge = sat.over_south_asia
      ? `<span style="background:#E63946;color:#fff;font-size:9px;padding:2px 5px;border-radius:2px;margin-left:6px;font-family:Rajdhani,sans-serif;letter-spacing:0.08em;font-weight:700;">OVERHEAD</span>`
      : '';
    const typeIcon = TYPE_ICONS[sat.type] || '🛰️';
    return `
      <div class="bp-popup">
        <div class="bp-popup-header">
          <div>
            <div class="bp-popup-name">${typeIcon} ${sat.name}</div>
            <div class="bp-popup-theatre" style="color:${colour};">${sat.country} — ${sat.type}${overBadge}</div>
          </div>
        </div>
        <div class="bp-popup-body">
          <div class="bp-popup-description" style="font-size:11px;line-height:1.8;">
            <span style="color:var(--text-dim);">ROLE</span>
            <span style="color:var(--text-secondary);margin-left:4px;">${sat.role}</span>
            <br>
            <span style="color:var(--text-dim);">ALT</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${sat.altitude_km} km</span>
            &nbsp;&nbsp;
            <span style="color:var(--text-dim);">SPD</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${sat.speed_kms} km/s</span>
            <br>
            <span style="color:var(--text-dim);">PERIOD</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${sat.period_min} min</span>
            <br>
            <span style="color:var(--text-dim);">NORAD</span>
            <span class="font-data" style="color:var(--text-secondary);margin-left:4px;font-size:10px;">#${sat.norad}</span>
            &nbsp;&nbsp;
            <span style="color:var(--text-dim);">POS</span>
            <span class="font-data" style="color:var(--text-secondary);margin-left:4px;font-size:10px;">${sat.lat}°, ${sat.lon}°</span>
          </div>
        </div>
      </div>
    `;
  }

  function renderSatellites(sats) {
    if (!satLayer || !trackLayer) return;
    satLayer.clearLayers();
    trackLayer.clearLayers();
    allSats = sats || [];
    allSats.forEach(sat => {
      if (!sat.lat || !sat.lon) return;
      drawGroundTrack(sat);
      const icon = satelliteIcon(sat);
      const marker = L.marker([sat.lat, sat.lon], { icon });
      marker.bindPopup(buildPopup(sat), { maxWidth: 300, className: 'bp-map-popup' });
      satLayer.addLayer(marker);
    });
  }

  async function fetchAndRender() {
    try {
      const resp = await fetch(`${CONFIG.API_BASE_URL}/api/satellites`,
        { signal: AbortSignal.timeout(90000) });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderSatellites(data.satellites);
      updateSatBadge(data.count, data.over_region);
      console.log(`[Satellites] ${data.count} sats (${data.over_region} over South Asia)`);
    } catch (err) {
      console.warn('[Satellites] Fetch failed:', err.message);
    }
  }

  function updateSatBadge(total, over) {
    const el = document.getElementById('sat-count');
    if (el) el.textContent = `${total} (${over} OVERHEAD)`;
  }

  function init(map, layerControlOverlays) {
    satLayer   = L.layerGroup();
    trackLayer = L.layerGroup();
    trackLayer.addTo(map);
    satLayer.addTo(map);
    const satLabel = `
      <span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">
        🛰️ Satellites
        <span id="sat-count" style="color:var(--text-dim);font-size:10px;margin-left:4px;font-family:JetBrains Mono,monospace;">—</span>
      </span>
    `;
    const trackLabel = `
      <span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:#445577;">
        ··· Ground Tracks
      </span>
    `;
    if (layerControlOverlays) {
      layerControlOverlays[satLabel]   = satLayer;
      layerControlOverlays[trackLabel] = trackLayer;
    }
    fetchAndRender();
    refreshTimer = setInterval(fetchAndRender, REFRESH_INTERVAL);
    return { satLayer, trackLayer };
  }

  function destroy() {
    if (refreshTimer) clearInterval(refreshTimer);
  }

  return { init, fetchAndRender, destroy };
})();
