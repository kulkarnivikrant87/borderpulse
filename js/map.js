// map.js — Leaflet map init, border zone polygons, flashpoint markers
// Border Pulse v1.0

const MapModule = (() => {
  let map = null;
  let bordersLayer = null;
  let flashpointsLayer = null;
  let assetsLayer = null;
  let layerControl = null;
  let flashpointData = [];

  // ── Colour helpers ────────────────────────────────────────────
  function theatreColour(theatreId) {
    return CONFIG.THEATRE_COLOURS[theatreId] || '#8899AA';
  }

  function statusColour(status) {
    const map = {
      active:     '#E63946',
      elevated:   '#F4A261',
      monitoring: '#457B9D',
      stable:     '#2EC4B6',
    };
    return map[status] || '#8899AA';
  }

  // ── Map init ──────────────────────────────────────────────────
  function init() {
    map = L.map('map', {
      center: CONFIG.MAP_CENTER,
      zoom: CONFIG.MAP_ZOOM,
      zoomControl: false,
      attributionControl: true,
    });

    // CartoDB Dark Matter tiles
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19,
      }
    ).addTo(map);

    // Zoom control — top right
    L.control.zoom({ position: 'topright' }).addTo(map);

    // Scale bar — bottom left
    L.control.scale({ position: 'bottomleft', imperial: false }).addTo(map);

    // Fit to South Asia bounds
    map.fitBounds(CONFIG.MAP_BOUNDS);

    // Load layers
    loadBorders();
    loadFlashpoints();

    return map;
  }

  // ── Border Zones ──────────────────────────────────────────────
  function loadBorders() {
    fetch('./data/borders.geojson')
      .then(r => r.json())
      .then(geojson => {
        bordersLayer = L.geoJSON(geojson, {
          style: feature => ({
            color: feature.properties.stroke,
            weight: feature.properties.strokeWidth || 2,
            fillColor: feature.properties.fill,
            fillOpacity: 0.12,
            opacity: 0.7,
            dashArray: feature.properties.id === 'loc' ? '6 3' : null,
          }),
          onEachFeature: (feature, layer) => {
            const p = feature.properties;
            layer.bindTooltip(
              `<div style="font-family:'Rajdhani',sans-serif;font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#E8EDF4;background:#111827;border:1px solid #1E2D40;padding:4px 8px;">${p.name}</div>`,
              { sticky: true, opacity: 0.95, className: 'bp-tooltip' }
            );
          },
        });

        setupLayerControl();
      })
      .catch(err => console.error('[BorderPulse] Failed to load borders.geojson', err));
  }

  // ── Flashpoint Markers ────────────────────────────────────────
  function loadFlashpoints() {
    fetch('./data/flashpoints.json')
      .then(r => r.json())
      .then(geojson => {
        flashpointData = geojson.features;
        flashpointsLayer = L.layerGroup();

        geojson.features.forEach(feature => {
          const p = feature.properties;
          const [lng, lat] = feature.geometry.coordinates;
          const colour = statusColour(p.status);

          // Custom pulsing SVG icon
          const size = p.status === 'active' ? 14 : 12;
          const pulseSize = size * 2.4;

          const svgIcon = L.divIcon({
            className: '',
            html: `
              <div style="position:relative;width:${pulseSize}px;height:${pulseSize}px;display:flex;align-items:center;justify-content:center;">
                <div style="
                  position:absolute;
                  width:${pulseSize}px;height:${pulseSize}px;
                  border-radius:50%;
                  border:2px solid ${colour};
                  opacity:0;
                  animation:pulse 2.5s ease-out infinite;
                "></div>
                <div style="
                  width:${size}px;height:${size}px;
                  border-radius:50%;
                  background:${colour};
                  border:2px solid rgba(255,255,255,0.3);
                  box-shadow:0 0 ${p.status === 'active' ? '8px' : '4px'} ${colour};
                  position:relative;z-index:1;
                "></div>
              </div>
            `,
            iconSize: [pulseSize, pulseSize],
            iconAnchor: [pulseSize / 2, pulseSize / 2],
            popupAnchor: [0, -pulseSize / 2],
          });

          const marker = L.marker([lat, lng], { icon: svgIcon });

          // Build popup
          const theatreClass = p.theatre.toLowerCase().replace(/[^a-z]/g, '-');
          const popupHtml = `
            <div class="bp-popup">
              <div class="bp-popup-header">
                <div>
                  <div class="bp-popup-name">${p.name}</div>
                  <div class="bp-popup-theatre">${p.theatre}</div>
                </div>
                <span class="status-badge ${p.status}" style="font-size:9px;padding:2px 6px;">${p.status.toUpperCase()}</span>
              </div>
              <div class="bp-popup-body">
                <div class="bp-popup-description">${p.description}</div>
                <div class="bp-popup-meta">
                  <span class="bp-popup-date font-data">Last: ${formatDate(p.last_incident)}</span>
                  <a href="${p.source}" target="_blank" rel="noopener" class="bp-popup-source">More →</a>
                </div>
              </div>
            </div>
          `;

          marker.bindPopup(popupHtml, {
            maxWidth: 280,
            className: 'bp-map-popup',
          });

          flashpointsLayer.addLayer(marker);
        });

        setupLayerControl();
      })
      .catch(err => console.error('[BorderPulse] Failed to load flashpoints.json', err));
  }

  // ── Layer Control ─────────────────────────────────────────────
  // Called after each layer loads; only adds control when both are ready
  let layerControlReady = { borders: false, flashpoints: false };

  function setupLayerControl() {
    if (bordersLayer && !layerControlReady.borders) {
      bordersLayer.addTo(map);
      layerControlReady.borders = true;
    }
    if (flashpointsLayer && !layerControlReady.flashpoints) {
      flashpointsLayer.addTo(map);
      layerControlReady.flashpoints = true;
    }

    if (layerControlReady.borders && layerControlReady.flashpoints && !layerControl) {
      // Assets layer (placeholder for Phase 2)
      assetsLayer = L.layerGroup();

      const overlays = {
        '<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">Border Zones</span>': bordersLayer,
        '<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;">Flashpoints</span>': flashpointsLayer,
        '<span style="font-family:Rajdhani,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.08em;color:#445566;">Military Assets</span>': assetsLayer,
      };

      layerControl = L.control.layers(null, overlays, {
        position: 'topright',
        collapsed: true,
      }).addTo(map);
    }
  }

  // ── Utility ───────────────────────────────────────────────────
  function formatDate(dateStr) {
    if (!dateStr) return 'Unknown';
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
    } catch {
      return dateStr;
    }
  }

  // Update flashpoint marker colour based on live tension scores
  function updateFlashpointStatus(theatreId, score) {
    // Phase 2 enhancement — placeholder for dynamic marker updates
    console.log(`[Map] Theatre ${theatreId} tension: ${score}`);
  }

  function getMap() { return map; }
  function getFlashpointData() { return flashpointData; }

  return { init, updateFlashpointStatus, getMap, getFlashpointData };
})();
