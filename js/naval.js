// naval.js — Naval vessel tracking + strategic zone layer
// Border Pulse v1.1 | South Asia Geopolitical Intelligence Dashboard

const NavalModule = (() => {
  let vesselLayer = null;
  let zoneLayer   = null;
  let refreshTimer = null;

  const REFRESH_INTERVAL = 5 * 60 * 1000; // 5 minutes

  const VESSEL_COLOURS = {
    warship:  '#E63946',
    carrier:  '#E63946',
    submarine:'#9B5DE5',
    patrol:   '#F4A261',
    tanker:   '#457B9D',
    cargo:    '#2EC4B6',
    merchant: '#8899AA',
  };

  const THREAT_COLOURS = {
    active:    '#E63946',
    elevated:  '#F4A261',
    monitoring:'#457B9D',
    stable:    '#2EC4B6',
  };

  const ZONE_ICONS = {
    chokepoint:    '⚓',
    naval_base:    '⚔️',
    base:          '⚔️',
    strategic_port:'🏭',
    patrol_zone:   '🔵',
  };

  function shipIcon(type, heading) {
    const colour = VESSEL_COLOURS[type] || '#8899AA';
    const isMil  = ['warship', 'carrier', 'submarine', 'patrol'].includes(type);
    const size   = isMil ? 20 : 16;
    const glow   = isMil ? 5 : 2;
    return L.divIcon({
      className: '',
      html: `
        <div style="
          width:${size}px; height:${size}px;
          transform: rotate(${heading || 0}deg);
          filter: drop-shadow(0 0 ${glow}px ${colour});
        ">
          <svg viewBox="0 0 24 24" fill="${colour}" xmlns="http://www.w3.org/2000/svg"
               style="width:100%;height:100%;">
            <path d="M3 17l2-8 7-4 7 4 2 8H3z"
                  stroke="rgba(255,255,255,0.35)" stroke-width="0.6"/>
            <rect x="10" y="2" width="4" height="6" fill="${colour}" opacity="0.8"/>
          </svg>
        </div>
      `,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -size / 2],
    });
  }

  function hexToRgb(hex) {
    const m = (hex || '#888').replace('#','').match(/.{2}/g);
    if (!m) return '136,136,136';
    return m.map(x => parseInt(x,16)).join(',');
  }

  function zoneIcon(zone) {
    const colour = THREAT_COLOURS[zone.threat] || '#8899AA';
    const iconChar = ZONE_ICONS[zone.type] || '●';
    const size = 28;
    return L.divIcon({
      className: '',
      html: `
        <div style="
          width:${size}px; height:${size}px;
          position:relative; display:flex;
          align-items:center; justify-content:center;
        ">
          <div style="
            position:absolute;
            width:${size}px; height:${size}px;
            border-radius:50%;
            border:2px solid ${colour};
            opacity:0;
            animation:pulse 3s ease-out infinite;
          "></div>
          <div style="
            width:20px; height:20px;
            border-radius:50%;
            background:rgba(${hexToRgb(colour)},0.15);
            border:1.5px solid ${colour};
            display:flex; align-items:center; justify-content:center;
            font-size:10px; line-height:1;
            box-shadow: 0 0 6px ${colour};
          ">${iconChar}</div>
        </div>
      `,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -size / 2],
    });
  }

  function vesselPopup(v) {
    const spd = v.speed != null ? `${v.speed} kts` : '—';
    const hdg = v.heading != null ? `${v.heading}°` : '—';
    const typeBadge = `<span style="background:${VESSEL_COLOURS[v.type]||'#8899AA'};color:#fff;font-size:9px;padding:2px 5px;border-radius:2px;font-family:Rajdhani,sans-serif;letter-spacing:0.08em;font-weight:700;text-transform:uppercase;">${v.type}</span>`;
    return `
      <div class="bp-popup">
        <div class="bp-popup-header">
          <div>
            <div class="bp-popup-name">⚓ ${v.name}</div>
            <div class="bp-popup-theatre">${v.flag || ''} ${typeBadge}</div>
          </div>
        </div>
        <div class="bp-popup-body">
          <div class="bp-popup-description" style="font-size:11px;line-height:1.7;">
            <span style="color:var(--text-dim);">SPD</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${spd}</span>
            &nbsp;&nbsp;
            <span style="color:var(--text-dim);">HDG</span>
            <span class="font-data" style="color:var(--text-bright);margin-left:4px;">${hdg}</span>
            ${v.dest ? `<br><span style="color:var(--text-dim);">DEST</span> <span class="font-data" style="color:var(--text-secondary);margin-left:4px;">${v.dest}</span>` : ''}
            ${v.mmsi ? `<br><span style="color:var(--text-dim);">MMSI</span> <span class="font-data" style="color:var(--text-secondary);margin-left:4px;font-size:10px;">${v.mmsi}</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }

  function zonePopup(z) {
    return `
      <div class="bp-popup">
        <div class="bp-popup-header">
          <div>
            <div class="bp-popup-name">${ZONE_ICONS[z.type] || '●'} ${z.name}</div>
            <div class="bp-popup-theatre">${z.flag || ''} ${z.country}</div>
          </div>
          <span class="status-badge ${z.threat}" style="font-size:9px;padding:2px 6px;">
            ${(z.threat || 'unknown').toUpperCase()}
          </span>
        </div>
        <div class="bp-popup-body">
          <div class="bp-popup-description">${z.description}</div>
          <div class="bp-popup-meta">
            <span style="color:var(--text-dim);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;">${z.type.replace(/_/g,' ')}</span>
          </div>
        </div>
      </div>
    `;
  }

  function renderVessels(vessels) {
    if (!vesselLayer) return;
    vesselLayer.clearLayers();
    (vessels || []).forEach(v => {
      if (!v.lat || !v.lon) return;
      const icon = shipIcon(v.type, v.heading);
      const marker = L.marker([v.lat, v.lon], { icon });
      marker.bindPopup(vesselPopup(v), { maxWidth: 260, className: 'bp-map-popup' });
      vesselLayer.addLayer(marker);
    });
  }

  function renderZones(zones) {
    if (!zoneLayer) return;
    zoneLayer.clearLayers();
    (zones || []).forEach(z => {
      if (!z.lat || !z.lon) return;
      const icon = zoneIcon(z);
      const marker = L.marker([z.lat, z.lon], { icon });
      marker.bindPopup(zonePopup(z), { maxWidth: 280, className: 'bp-map-popup' });
      zoneLayer.addLayer(marker);
    });
  }

  async function fetchAndRender() {
    try {
      const resp = await fetch(`${CONFIG.API_BASE_URL}/api/naval`,
        { signal: AbortSignal.timeout(25000) });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      renderVessels(data.vessels);
      renderZones(data.zones);
      updateNavalBadge(data.vessel_count, data.zone_count);
      console.log(`[Naval] ${data.vessel_count} vessels, ${data.zone_count} strategic zones`);
    } catch (err) {
      console.warn('[Naval] Fetch failed:', err.message);
    }
  }

  function updateNavalBadge(vessels, zones) {
    const el = document.getElementById('naval-count');
    if (el) el.textContent = vessels > 0 ? `${vessels} vessels` : `${zones} zones`;
  }

  function init(map, layerControlOverlays) {
    vesselLayer = L.layerGroup();
    zoneLayer   = L.layerGroup();
    const vesselLabel = `
      <span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">
        ⚓ Naval Vessels
        <span id="naval-count" style="color:var(--text-dim);font-size:10px;margin-left:4px;font-family:JetBrains Mono,monospace;">—</span>
      </span>
    `;
    const zoneLabel = `
      <span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">
        ⚔️ Strategic Zones
      </span>
    `;
    if (layerControlOverlays) {
      layerControlOverlays[vesselLabel] = vesselLayer;
      layerControlOverlays[zoneLabel]   = zoneLayer;
    }
    fetchAndRender();
    refreshTimer = setInterval(fetchAndRender, REFRESH_INTERVAL);
    return { vesselLayer, zoneLayer };
  }

  function destroy() {
    if (refreshTimer) clearInterval(refreshTimer);
  }

  return { init, fetchAndRender, destroy };
})();
