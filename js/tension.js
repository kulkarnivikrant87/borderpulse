// tension.js — Tension score calculation + SVG gauge render + sparklines
// Border Pulse v1.0

const TensionModule = (() => {
  // Stores last 7 days of scores per theatre (in-memory)
  const history = {
    loc: [], lac: [], bangladesh: [], naval: [],
  };
  const currentScores = {
    loc: 0, lac: 0, bangladesh: 0, naval: 0,
  };

  // ── Fetch tension scores from backend ─────────────────────────
  async function fetchAllScores() {
    const results = await Promise.allSettled(
      CONFIG.THEATRES.map(theatre =>
        fetch(`${CONFIG.API_BASE_URL}/api/tension/${theatre}`)
          .then(r => r.ok ? r.json() : Promise.reject(r.status))
          .then(data => ({ theatre, score: data.score, breakdown: data.breakdown }))
      )
    );

    let anyAlert = false;

    results.forEach(result => {
      if (result.status === 'fulfilled') {
        const { theatre, score } = result.value;
        const clamped = Math.min(100, Math.max(0, Math.round(score)));
        currentScores[theatre] = clamped;

        // Push to history (keep 7 * 96 = 672 data points max, sampled every 15 min)
        history[theatre].push({ score: clamped, timestamp: Date.now() });
        if (history[theatre].length > 672) history[theatre].shift();

        if (clamped >= CONFIG.TENSION_ALERT_THRESHOLD) anyAlert = true;

        updateGauge(theatre, clamped);
        updateSidebarBar(theatre, clamped);
        MapModule && MapModule.updateFlashpointStatus(theatre, clamped);
      }
    });

    // Alert banner
    const banner = document.getElementById('alert-banner');
    if (banner) {
      const highTheatres = CONFIG.THEATRES
        .filter(t => currentScores[t] >= CONFIG.TENSION_ALERT_THRESHOLD)
        .map(t => CONFIG.THEATRE_SHORT[t]);

      if (highTheatres.length > 0) {
        banner.textContent = `⚠ HIGH TENSION DETECTED — ${highTheatres.join(' / ')} — SCORES ABOVE ${CONFIG.TENSION_ALERT_THRESHOLD}`;
        banner.classList.add('visible');
      } else {
        banner.classList.remove('visible');
      }
    }

    // Alert count badge
    updateAlertBadge();
  }

  // ── SVG Gauge ─────────────────────────────────────────────────
  function buildGauge(containerId, theatre) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const R = 44;          // arc radius
    const CX = 60, CY = 60;
    const strokeWidth = 8;
    const startAngle = -220; // degrees (bottom-left to bottom-right, 220° arc)
    const endAngle = 40;

    // Convert angle to SVG arc coordinates
    function polarToXY(cx, cy, r, angleDeg) {
      const rad = (angleDeg - 90) * (Math.PI / 180);
      return {
        x: cx + r * Math.cos(rad),
        y: cy + r * Math.sin(rad),
      };
    }

    function describeArc(cx, cy, r, startDeg, endDeg) {
      const s = polarToXY(cx, cy, r, startDeg);
      const e = polarToXY(cx, cy, r, endDeg);
      const large = (endDeg - startDeg + 360) % 360 > 180 ? 1 : 0;
      return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`;
    }

    const totalAngle = (endAngle - startAngle + 360) % 360; // 260 degrees

    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 120 120');
    svg.setAttribute('width', '110');
    svg.setAttribute('height', '110');
    svg.classList.add('tension-gauge-svg');
    svg.setAttribute('data-theatre', theatre);

    // Track (background arc)
    const track = document.createElementNS(svgNS, 'path');
    track.setAttribute('d', describeArc(CX, CY, R, startAngle, endAngle));
    track.setAttribute('fill', 'none');
    track.setAttribute('stroke', '#1E2D40');
    track.setAttribute('stroke-width', strokeWidth);
    track.setAttribute('stroke-linecap', 'round');
    svg.appendChild(track);

    // Filled arc (score indicator)
    const fill = document.createElementNS(svgNS, 'path');
    fill.setAttribute('fill', 'none');
    fill.setAttribute('stroke-width', strokeWidth);
    fill.setAttribute('stroke-linecap', 'round');
    fill.setAttribute('class', 'gauge-fill');
    fill.setAttribute('data-theatre', theatre);
    fill.setAttribute('data-start', startAngle);
    fill.setAttribute('data-totalangle', totalAngle);
    fill.setAttribute('data-cx', CX);
    fill.setAttribute('data-cy', CY);
    fill.setAttribute('data-r', R);
    svg.appendChild(fill);

    // Score text (centre)
    const scoreGroup = document.createElementNS(svgNS, 'g');

    const scoreText = document.createElementNS(svgNS, 'text');
    scoreText.setAttribute('x', CX);
    scoreText.setAttribute('y', CY + 6);
    scoreText.setAttribute('text-anchor', 'middle');
    scoreText.setAttribute('font-family', 'JetBrains Mono, monospace');
    scoreText.setAttribute('font-size', '20');
    scoreText.setAttribute('font-weight', '500');
    scoreText.setAttribute('fill', '#E8EDF4');
    scoreText.setAttribute('class', 'gauge-score-text');
    scoreText.setAttribute('data-theatre', theatre);
    scoreText.textContent = '0';
    scoreGroup.appendChild(scoreText);

    const unitText = document.createElementNS(svgNS, 'text');
    unitText.setAttribute('x', CX);
    unitText.setAttribute('y', CY + 18);
    unitText.setAttribute('text-anchor', 'middle');
    unitText.setAttribute('font-family', 'Rajdhani, sans-serif');
    unitText.setAttribute('font-size', '8');
    unitText.setAttribute('fill', '#445566');
    unitText.setAttribute('letter-spacing', '1');
    unitText.textContent = '/100';
    scoreGroup.appendChild(unitText);

    svg.appendChild(scoreGroup);
    return svg;
  }

  function updateGauge(theatre, score) {
    const colour = scoreColour(score);

    // Update all SVG fills for this theatre
    document.querySelectorAll(`.gauge-fill[data-theatre="${theatre}"]`).forEach(fill => {
      const startAngle = parseFloat(fill.dataset.start);
      const totalAngle = parseFloat(fill.dataset.totalangle);
      const CX = parseFloat(fill.dataset.cx);
      const CY = parseFloat(fill.dataset.cy);
      const R = parseFloat(fill.dataset.r);

      const endAngle = startAngle + (score / 100) * totalAngle;

      function polarToXY(cx, cy, r, angleDeg) {
        const rad = (angleDeg - 90) * (Math.PI / 180);
        return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
      }

      if (score <= 0) {
        fill.setAttribute('d', '');
        fill.setAttribute('stroke', colour);
        return;
      }

      const s = polarToXY(CX, CY, R, startAngle);
      const e = polarToXY(CX, CY, R, endAngle);
      const large = (endAngle - startAngle) > 180 ? 1 : 0;
      const d = `M ${s.x} ${s.y} A ${R} ${R} 0 ${large} 1 ${e.x} ${e.y}`;

      fill.setAttribute('d', d);
      fill.setAttribute('stroke', colour);

      if (score >= 81) {
        fill.classList.add('tension-critical-flash');
      } else {
        fill.classList.remove('tension-critical-flash');
      }
    });

    // Update score text
    document.querySelectorAll(`.gauge-score-text[data-theatre="${theatre}"]`).forEach(el => {
      el.textContent = score;
      el.setAttribute('fill', colour);
    });

    // Update sparkline
    renderSparkline(theatre);
  }

  // ── Sparkline ─────────────────────────────────────────────────
  function renderSparkline(theatre) {
    const container = document.querySelector(`.sparkline-wrap[data-theatre="${theatre}"]`);
    if (!container) return;

    const hist = history[theatre];
    if (hist.length < 2) return;

    const W = container.clientWidth || 200;
    const H = 28;
    const pts = hist.slice(-48); // last 48 readings = 12 hours

    const minS = 0, maxS = 100;
    const toX = (i) => (i / (pts.length - 1)) * W;
    const toY = (v) => H - ((v - minS) / (maxS - minS)) * H;

    const pathD = pts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(p.score).toFixed(1)}`).join(' ');
    const areaD = `${pathD} L ${W} ${H} L 0 ${H} Z`;

    const colour = scoreColour(pts[pts.length - 1].score);

    container.innerHTML = `
      <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" class="sparkline-svg" preserveAspectRatio="none">
        <path d="${areaD}" fill="${colour}" class="sparkline-area" opacity="0.15"/>
        <path d="${pathD}" stroke="${colour}" class="sparkline-path" fill="none" stroke-width="1.5" opacity="0.8"/>
      </svg>`;
  }

  // ── Sidebar mini-bars ─────────────────────────────────────────
  function updateSidebarBar(theatre, score) {
    const row = document.querySelector(`.sidebar-tension-row[data-theatre="${theatre}"]`);
    if (!row) return;

    const bar = row.querySelector('.sidebar-tension-bar');
    const scoreEl = row.querySelector('.sidebar-tension-score');
    const colour = scoreColour(score);

    if (bar) {
      bar.style.width = `${score}%`;
      bar.style.background = colour;
    }
    if (scoreEl) {
      scoreEl.textContent = score;
      scoreEl.style.color = colour;
    }

    // Also update the theatre-btn score in sidebar
    const btn = document.querySelector(`.theatre-btn[data-theatre="${theatre}"] .theatre-btn-score`);
    if (btn) {
      btn.textContent = score;
      btn.style.color = colour;
    }
  }

  // ── Alert badge ───────────────────────────────────────────────
  function updateAlertBadge() {
    const count = CONFIG.THEATRES.filter(t => currentScores[t] >= CONFIG.TENSION_ALERT_THRESHOLD).length;
    const badge = document.getElementById('alert-count-badge');
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count;
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  }

  // ── Colour helper ─────────────────────────────────────────────
  function scoreColour(score) {
    if (score <= 30) return '#2EC4B6';
    if (score <= 60) return '#F4A261';
    return '#E63946';
  }

  // ── Build main gauge panels (right panel) ─────────────────────
  function buildGaugePanels() {
    const container = document.getElementById('tension-gauges');
    if (!container) return;

    container.innerHTML = '';

    CONFIG.THEATRES.forEach(theatre => {
      const wrap = document.createElement('div');
      wrap.className = 'tension-gauge-container';
      wrap.dataset.theatre = theatre;

      const title = document.createElement('div');
      title.className = 'tension-gauge-title';
      title.style.color = CONFIG.THEATRE_COLOURS[theatre];
      title.textContent = CONFIG.THEATRE_SHORT[theatre];
      wrap.appendChild(title);

      const svgWrap = document.createElement('div');
      svgWrap.className = 'tension-gauge-svg-wrap';
      const svg = buildGauge(`gauge-${theatre}`, theatre);
      if (svg) svgWrap.appendChild(svg);
      wrap.appendChild(svgWrap);

      // Sparkline
      const sparkWrap = document.createElement('div');
      sparkWrap.className = 'sparkline-wrap tension-sparkline';
      sparkWrap.dataset.theatre = theatre;
      wrap.appendChild(sparkWrap);

      container.appendChild(wrap);
    });
  }

  // ── Build sidebar mini tension rows ──────────────────────────
  function buildSidebarRows() {
    const container = document.getElementById('tension-sidebar');
    if (!container) return;

    container.innerHTML = '';
    CONFIG.THEATRES.forEach(theatre => {
      const row = document.createElement('div');
      row.className = 'sidebar-tension-row';
      row.dataset.theatre = theatre;
      row.title = CONFIG.THEATRE_LABELS[theatre];
      row.innerHTML = `
        <span class="theatre-dot ${theatre}" style="background:${CONFIG.THEATRE_COLOURS[theatre]};width:8px;height:8px;border-radius:50%;flex-shrink:0;"></span>
        <span class="sidebar-tension-label">${CONFIG.THEATRE_SHORT[theatre]}</span>
        <div class="sidebar-tension-bar-wrap">
          <div class="sidebar-tension-bar" style="width:0%;background:${CONFIG.THEATRE_COLOURS[theatre]};"></div>
        </div>
        <span class="sidebar-tension-score font-data">—</span>
      `;
      container.appendChild(row);
    });
  }

  function getCurrentScores() { return { ...currentScores }; }

  async function init() {
    buildGaugePanels();
    buildSidebarRows();
    await fetchAllScores();
  }

  function startAutoRefresh() {
    setInterval(fetchAllScores, CONFIG.REFRESH_INTERVAL_TENSION);
  }

  return { init, startAutoRefresh, getCurrentScores, scoreColour };
})();
