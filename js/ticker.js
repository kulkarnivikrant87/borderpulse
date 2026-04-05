// ticker.js — Breaking news bottom scrolling ticker
// Border Pulse v1.0

const TickerModule = (() => {
  let tickerInner = null;
  let currentItems = [];

  function init() {
    tickerInner = document.querySelector('.ticker-inner');
    // Populate with loading placeholder
    if (tickerInner) {
      tickerInner.innerHTML = `
        <span class="ticker-item">
          <span class="theatre-badge loc">LoC</span>
          LOADING INTELLIGENCE FEEDS — STAND BY
        </span>
        <span class="ticker-item">
          <span class="theatre-badge lac">LAC</span>
          INITIALISING BORDER PULSE OSINT AGGREGATOR
        </span>
        <span class="ticker-item">
          <span class="theatre-badge naval">Naval</span>
          SOUTH ASIA GEOPOLITICAL INTELLIGENCE DASHBOARD v1.0
        </span>
      `;
      // Duplicate for seamless loop
      duplicateForLoop();
    }
  }

  function update(articles) {
    if (!tickerInner || !articles || articles.length === 0) return;
    currentItems = articles;

    const items = articles.slice(0, 20).map(a => {
      const theatre = a.theatre || 'loc';
      const short = CONFIG.THEATRE_SHORT[theatre] || theatre.toUpperCase();
      const headline = (a.title || '').substring(0, 80);
      return `
        <span class="ticker-item">
          <span class="theatre-badge ${theatre}">${short}</span>
          ${escapeHtml(headline)}
        </span>
      `;
    }).join('');

    tickerInner.innerHTML = items;
    duplicateForLoop();

    // Adjust animation duration based on content length
    const totalChars = articles.reduce((sum, a) => sum + (a.title || '').length, 0);
    const duration = Math.max(40, Math.min(120, totalChars / 8));
    tickerInner.style.animationDuration = `${duration}s`;
  }

  function duplicateForLoop() {
    if (!tickerInner) return;
    // Remove previous duplicate
    const existing = tickerInner.querySelectorAll('.ticker-duplicate');
    existing.forEach(el => el.remove());
    // Clone all items and append for seamless loop
    const items = Array.from(tickerInner.children);
    items.forEach(item => {
      const clone = item.cloneNode(true);
      clone.classList.add('ticker-duplicate');
      tickerInner.appendChild(clone);
    });
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  return { init, update };
})();
