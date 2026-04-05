// news.js — GDELT fetch, dedup, card rendering
// Border Pulse v1.0

const NewsModule = (() => {
  let allArticles = [];
  let activeFilter = 'all';
  let sourcesData = null;

  // ── Load sources config ───────────────────────────────────────
  async function loadSources() {
    if (sourcesData) return sourcesData;
    try {
      const r = await fetch('./data/sources.json');
      sourcesData = await r.json();
    } catch {
      sourcesData = { state_media_domains: CONFIG.STATE_MEDIA_DOMAINS, sources: [] };
    }
    return sourcesData;
  }

  // ── Fetch news from backend ───────────────────────────────────
  async function fetchAllTheatres() {
    const results = await Promise.allSettled(
      CONFIG.THEATRES.map(theatre =>
        fetch(`${CONFIG.API_BASE_URL}/api/news/${theatre}`)
          .then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
          })
          .then(data => ({ theatre, articles: data.articles || [] }))
      )
    );

    const fresh = [];
    results.forEach(result => {
      if (result.status === 'fulfilled') {
        const { theatre, articles } = result.value;
        articles.forEach(a => fresh.push({ ...a, theatre }));
      }
    });

    // Merge with existing, deduplicate, sort by date
    allArticles = deduplicateArticles([...fresh]);
    allArticles.sort((a, b) => new Date(b.seendate || b.published) - new Date(a.seendate || a.published));
    allArticles = allArticles.slice(0, CONFIG.NEWS_MAX_ARTICLES);

    render();
    updateTicker();
    updateLastUpdated();
  }

  // ── Deduplication ─────────────────────────────────────────────
  function deduplicateArticles(articles) {
    const byUrl = new Map();
    const byTitle = new Map();

    articles.forEach(article => {
      const url = article.url || article.sourceurl;
      if (!url) return;

      if (byUrl.has(url)) {
        // Increment source count on existing
        byUrl.get(url)._sourceCount = (byUrl.get(url)._sourceCount || 1) + 1;
        return;
      }

      // Fuzzy title dedup (first 60 chars)
      const titleKey = (article.title || '').substring(0, 60).toLowerCase().trim();
      if (titleKey && byTitle.has(titleKey)) {
        byTitle.get(titleKey)._sourceCount = (byTitle.get(titleKey)._sourceCount || 1) + 1;
        return;
      }

      article._sourceCount = 1;
      byUrl.set(url, article);
      if (titleKey) byTitle.set(titleKey, article);
    });

    return Array.from(byUrl.values());
  }

  // ── Render ────────────────────────────────────────────────────
  function render() {
    const list = document.getElementById('news-list');
    if (!list) return;

    const filtered = activeFilter === 'all'
      ? allArticles
      : allArticles.filter(a => a.theatre === activeFilter);

    if (filtered.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📡</div>
          <div>No articles found for this theatre.</div>
        </div>`;
      return;
    }

    list.innerHTML = '';
    filtered.forEach(article => {
      const card = buildCard(article);
      list.appendChild(card);
    });
  }

  function buildCard(article) {
    const a = document.createElement('a');
    a.className = `news-card theatre-${article.theatre}`;
    a.href = article.url || article.sourceurl || '#';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';

    const domain = extractDomain(article.url || article.sourceurl || '');
    const isStateMedia = isStateDomain(domain);
    const isUnconfirmed = (article._sourceCount || 1) < 2 && !isStateMedia;
    const tone = parseTone(article.tone || article.avgtone);
    const theatreShort = CONFIG.THEATRE_SHORT[article.theatre] || article.theatre;
    const headline = (article.title || 'No headline').substring(0, 100);
    const sourceFlag = getSourceFlag(domain);

    a.innerHTML = `
      <div class="news-card-header">
        <span class="news-card-source">
          ${sourceFlag ? `<span>${sourceFlag}</span>` : ''}
          ${domain}
        </span>
        ${isStateMedia ? '<span class="badge-state-media">⚠️ State Media</span>' : ''}
        ${article._sourceCount >= CONFIG.NEWS_DEDUPE_THRESHOLD
          ? `<span class="badge-sources">${article._sourceCount} sources</span>`
          : ''}
      </div>
      <div class="news-card-headline">${escapeHtml(headline)}</div>
      <div class="news-card-footer">
        <span class="tone-dot ${tone.cls}" title="Tone: ${tone.label}"></span>
        <span class="theatre-badge ${article.theatre}">${theatreShort}</span>
        ${isUnconfirmed ? '<span class="badge-unconfirmed">UNCONFIRMED</span>' : ''}
        <span class="news-card-time">${relativeTime(article.seendate || article.published)}</span>
      </div>
    `;

    return a;
  }

  // ── Filter buttons ────────────────────────────────────────────
  function setupFilters() {
    const bar = document.getElementById('news-filter-bar');
    if (!bar) return;

    const filters = [
      { id: 'all', label: 'ALL' },
      { id: 'loc', label: 'LoC' },
      { id: 'lac', label: 'LAC' },
      { id: 'bangladesh', label: 'Bangladesh' },
      { id: 'naval', label: 'Naval' },
    ];

    bar.innerHTML = '';
    filters.forEach(f => {
      const btn = document.createElement('button');
      btn.className = `filter-btn ${f.id === activeFilter ? 'active' : ''}`;
      btn.textContent = f.label;
      btn.dataset.filter = f.id;
      btn.addEventListener('click', () => {
        activeFilter = f.id;
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        render();
      });
      bar.appendChild(btn);
    });
  }

  // ── Ticker update ─────────────────────────────────────────────
  function updateTicker() {
    TickerModule && TickerModule.update(allArticles.slice(0, 15));
  }

  // ── Utilities ─────────────────────────────────────────────────
  function extractDomain(url) {
    try {
      return new URL(url).hostname.replace('www.', '');
    } catch {
      return url || 'unknown';
    }
  }

  function isStateDomain(domain) {
    const stateDomains = (sourcesData && sourcesData.state_media_domains) || CONFIG.STATE_MEDIA_DOMAINS;
    return stateDomains.some(d => domain.includes(d));
  }

  function getSourceFlag(domain) {
    if (!sourcesData) return '';
    const src = sourcesData.sources.find(s => domain.includes(s.domain));
    return src ? src.flag : '';
  }

  function parseTone(tone) {
    const v = parseFloat(tone);
    if (isNaN(v)) return { cls: 'neutral', label: 'Neutral' };
    if (v < -1.5) return { cls: 'negative', label: `Negative (${v.toFixed(1)})` };
    if (v > 1.5)  return { cls: 'positive', label: `Positive (${v.toFixed(1)})` };
    return { cls: 'neutral', label: `Neutral (${v.toFixed(1)})` };
  }

  function relativeTime(dateStr) {
    if (!dateStr) return '—';
    try {
      // GDELT format: YYYYMMDDTHHMMSSZ
      let d;
      if (/^\d{14}Z?$/.test(dateStr) || /^\d{8}T\d{6}Z?$/.test(dateStr)) {
        const s = dateStr.replace('T', '').replace('Z', '');
        d = new Date(
          s.substring(0,4), s.substring(4,6)-1, s.substring(6,8),
          s.substring(8,10)||0, s.substring(10,12)||0, s.substring(12,14)||0
        );
      } else {
        d = new Date(dateStr);
      }
      const diff = Math.floor((Date.now() - d.getTime()) / 1000);
      if (diff < 60)   return 'just now';
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
      return `${Math.floor(diff / 86400)}d ago`;
    } catch {
      return '—';
    }
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function updateLastUpdated() {
    const el = document.getElementById('last-updated');
    if (el) {
      const now = new Date();
      el.textContent = `UPDATED ${now.toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit' })} AEST`;
    }
  }

  function getAllArticles() { return allArticles; }
  function getArticlesByTheatre(theatre) {
    return allArticles.filter(a => a.theatre === theatre);
  }

  async function init() {
    await loadSources();
    setupFilters();
    await fetchAllTheatres();
  }

  function startAutoRefresh() {
    setInterval(fetchAllTheatres, CONFIG.REFRESH_INTERVAL_NEWS);
  }

  return { init, startAutoRefresh, getAllArticles, getArticlesByTheatre };
})();
