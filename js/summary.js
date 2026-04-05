// summary.js — Claude Haiku API call + summary display + localStorage cache
// Border Pulse v1.0

const SummaryModule = (() => {
  const CACHE_KEY_PREFIX = 'bp_summary_';
  const summaryEls = {};

  // ── Fetch summary for one theatre ────────────────────────────
  async function fetchSummary(theatre) {
    try {
      const r = await fetch(`${CONFIG.API_BASE_URL}/api/summary/${theatre}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();

      // Cache to localStorage
      try {
        localStorage.setItem(CACHE_KEY_PREFIX + theatre, JSON.stringify({
          ...data,
          cachedAt: Date.now(),
        }));
      } catch { /* storage full or unavailable */ }

      renderSummary(theatre, data, false);
    } catch (err) {
      console.warn(`[Summary] Failed to fetch ${theatre}:`, err);
      // Fall back to cache
      renderFromCache(theatre);
    }
  }

  // ── Render from localStorage cache ───────────────────────────
  function renderFromCache(theatre) {
    try {
      const raw = localStorage.getItem(CACHE_KEY_PREFIX + theatre);
      if (!raw) throw new Error('No cache');
      const data = JSON.parse(raw);
      renderSummary(theatre, data, true);
    } catch {
      renderError(theatre);
    }
  }

  // ── Render summary panel ──────────────────────────────────────
  function renderSummary(theatre, data, fromCache) {
    const container = summaryEls[theatre];
    if (!container) return;

    const status = (data.status || 'STABLE').trim().toUpperCase();
    const statusClass = statusToCSSClass(status);
    const text = data.summary || data.text || 'No summary available.';
    const ago = data.generated_at ? relativeTime(data.generated_at) : 'Unknown';

    container.innerHTML = `
      <div class="summary-panel">
        <div class="summary-panel-header">
          <span class="summary-panel-title" style="color:${CONFIG.THEATRE_COLOURS[theatre]};">
            ${CONFIG.THEATRE_SHORT[theatre]}
          </span>
          <span class="status-badge ${statusClass}">${status.replace('-', '\u2011')}</span>
        </div>
        <div class="summary-text">${escapeHtml(text)}</div>
        <div class="summary-footer">
          <span class="summary-timestamp font-data">Updated ${ago}</span>
          ${fromCache ? '<span class="status-badge cached" style="font-size:9px;padding:1px 5px;">CACHED</span>' : ''}
        </div>
      </div>
    `;
  }

  function renderError(theatre) {
    const container = summaryEls[theatre];
    if (!container) return;
    container.innerHTML = `
      <div class="summary-panel">
        <div class="summary-panel-header">
          <span class="summary-panel-title" style="color:${CONFIG.THEATRE_COLOURS[theatre]};">
            ${CONFIG.THEATRE_SHORT[theatre]}
          </span>
        </div>
        <div class="empty-state" style="padding:12px 0;">
          <div class="empty-state-icon">📡</div>
          <div style="font-size:11px;color:var(--text-muted);">Summary unavailable</div>
        </div>
      </div>
    `;
  }

  // ── Build panel containers ────────────────────────────────────
  function buildPanels() {
    const container = document.getElementById('summary-panels');
    if (!container) return;

    container.innerHTML = '';
    CONFIG.THEATRES.forEach(theatre => {
      const wrap = document.createElement('div');
      wrap.dataset.theatre = theatre;
      summaryEls[theatre] = wrap;

      // Show loading spinner initially
      wrap.innerHTML = `
        <div class="summary-panel">
          <div class="summary-panel-header">
            <span class="summary-panel-title" style="color:${CONFIG.THEATRE_COLOURS[theatre]};">
              ${CONFIG.THEATRE_SHORT[theatre]}
            </span>
          </div>
          <div style="display:flex;align-items:center;justify-content:center;padding:16px;">
            <div class="loading-spinner"></div>
          </div>
        </div>
      `;

      container.appendChild(wrap);
    });
  }

  // ── Fetch all theatres ────────────────────────────────────────
  async function fetchAll() {
    // Stagger calls to avoid rate limits (1 second apart)
    for (let i = 0; i < CONFIG.THEATRES.length; i++) {
      if (i > 0) await sleep(1000);
      await fetchSummary(CONFIG.THEATRES[i]);
    }
  }

  // ── Utilities ─────────────────────────────────────────────────
  function statusToCSSClass(status) {
    if (status === 'ESCALATING')    return 'escalating';
    if (status === 'DE-ESCALATING') return 'de-escalating';
    return 'stable';
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function relativeTime(ts) {
    try {
      const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
      const diff = Math.floor((Date.now() - d.getTime()) / 1000);
      if (diff < 60)    return 'just now';
      if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
      return `${Math.floor(diff / 86400)}d ago`;
    } catch {
      return '—';
    }
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  async function init() {
    buildPanels();
    // Show cached data immediately if available
    CONFIG.THEATRES.forEach(theatre => {
      const raw = localStorage.getItem(CACHE_KEY_PREFIX + theatre);
      if (raw) {
        try { renderSummary(theatre, JSON.parse(raw), true); } catch {}
      }
    });
    // Then fetch fresh
    await fetchAll();
  }

  function startAutoRefresh() {
    setInterval(fetchAll, CONFIG.REFRESH_INTERVAL_SUMMARY);
  }

  return { init, startAutoRefresh };
})();
