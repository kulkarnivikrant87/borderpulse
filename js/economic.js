// economic.js — Currency display + economic signals
// Border Pulse v1.0
// Phase 1: displays economic data from backend proxy
// Phase 2: adds live charting (Yahoo Finance)

const EconomicModule = (() => {
  let lastData = null;

  // ── Fetch from backend ────────────────────────────────────────
  async function fetchEconomicData() {
    try {
      const r = await fetch(`${CONFIG.API_BASE_URL}/api/economic`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      lastData = await r.json();
      render(lastData);
    } catch (err) {
      console.warn('[Economic] Fetch failed:', err);
      renderFallback();
    }
  }

  // ── Render ────────────────────────────────────────────────────
  function render(data) {
    const grid = document.getElementById('economic-grid');
    if (!grid) return;

    const cells = CONFIG.ECONOMIC_PAIRS.map(pair => {
      const item = data[pair.id] || {};
      const value = item.value != null ? item.value.toFixed(pair.id === 'BRENT' ? 2 : 4) : '—';
      const change = item.change_pct != null ? item.change_pct : null;
      const changeClass = change == null ? 'flat' : change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
      const changeStr = change == null ? '' : `${change > 0 ? '+' : ''}${change.toFixed(2)}%`;

      return `
        <div class="economic-cell">
          <div class="economic-label">${pair.flag} ${pair.label}</div>
          <div class="economic-value font-data">${value}</div>
          ${change != null ? `<div class="economic-change ${changeClass} font-data">${changeStr}</div>` : ''}
        </div>
      `;
    });

    grid.innerHTML = cells.join('');
  }

  function renderFallback() {
    const grid = document.getElementById('economic-grid');
    if (!grid) return;
    grid.innerHTML = CONFIG.ECONOMIC_PAIRS.map(pair => `
      <div class="economic-cell">
        <div class="economic-label">${pair.flag} ${pair.label}</div>
        <div class="economic-value font-data" style="color:var(--text-muted);">—</div>
      </div>
    `).join('');
  }

  async function init() {
    renderFallback(); // show placeholders immediately
    await fetchEconomicData();
  }

  function startAutoRefresh() {
    setInterval(fetchEconomicData, CONFIG.REFRESH_INTERVAL_ECONOMIC);
  }

  return { init, startAutoRefresh };
})();
