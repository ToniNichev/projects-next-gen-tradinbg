/**
 * Backtest chart, two views:
 *  - "Strategy vs. holding" (default): two lines that both start at 0%,
 *    so anyone can see which did better and when.
 *  - "Price & trades": candles, the strategy's trades and the portfolio value.
 *
 * Looks and moves like the Dashboard's price chart: same colours, axes,
 * tooltips and Buy/Sell badges; smooth wheel zoom around the cursor,
 * drag with momentum, Shift+wheel to scroll, keyboard and fullscreen.
 * The vertical axis always fits what's in view.
 */

let chart = null;
let currentResult = null;
let showTrades = true;
let showPortfolio = true;
const MODE_KEY = 'backtest_chart_mode';
let mode = readMode();

const STRATEGY_LINE = '#FFD700';
const HOLD_LINE = '#539bf5';

function readMode() {
  try { return localStorage.getItem(MODE_KEY) === 'price' ? 'price' : 'compare'; } catch { return 'compare'; }
}

const UP = '#58D68D';
const DOWN = '#ff5e57';
const FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

// Motion tuning, same as the Dashboard chart
const WHEEL_EASE_MS = 80;
const BUTTON_EASE_MS = 115;
const WHEEL_ZOOM_SENS = 0.0009;
const WHEEL_PAN_SENS = 1 / 1100;
const KEY_PAN_STEP = 0.045;
const MOMENTUM_DECAY_MS = 325;
const MAX_FLING_PX_PER_MS = 3.5;
const MIN_VISIBLE_CANDLES = 12;

const $ = (id) => document.getElementById(id);
const money = (v, d = 2) => '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

// ---------- Trade badges (same drawing as the Dashboard) ----------

const MARKER_W = 26, MARKER_H = 56;   // CSS px; the tip sits at the centre, on the price
const markerCache = {};

function markerImage(side) {
  if (markerCache[side]) return markerCache[side];
  const dpr = Math.max(2, window.devicePixelRatio || 1);
  const cv = document.createElement('canvas');
  cv.width = MARKER_W * dpr;
  cv.height = MARKER_H * dpr;
  const g = cv.getContext('2d');
  g.scale(dpr, dpr);

  const buy = side === 'buy';
  const cx = MARKER_W / 2, tipY = MARKER_H / 2, r = 10;
  const cy = buy ? tipY + 6 + r : tipY - 6 - r;
  const base = buy ? '#2ecc71' : '#ff5e57';
  const dark = buy ? '#1e8f4e' : '#c0392b';

  g.beginPath();                                   // pointer to the price
  g.moveTo(cx, tipY);
  g.lineTo(cx - 5, buy ? tipY + 8 : tipY - 8);
  g.lineTo(cx + 5, buy ? tipY + 8 : tipY - 8);
  g.closePath();
  g.fillStyle = base;
  g.fill();

  g.save();                                        // badge with a soft glow
  g.shadowColor = buy ? 'rgba(46, 204, 113, 0.55)' : 'rgba(255, 94, 87, 0.55)';
  g.shadowBlur = 8;
  const grad = g.createLinearGradient(0, cy - r, 0, cy + r);
  grad.addColorStop(0, base);
  grad.addColorStop(1, dark);
  g.beginPath();
  g.arc(cx, cy, r, 0, Math.PI * 2);
  g.fillStyle = grad;
  g.fill();
  g.restore();

  g.beginPath();                                   // highlight ring
  g.arc(cx, cy, r - 0.75, 0, Math.PI * 2);
  g.lineWidth = 1.5;
  g.strokeStyle = 'rgba(255, 255, 255, 0.55)';
  g.stroke();

  g.beginPath();                                   // chevron
  const d = buy ? -1 : 1;
  g.moveTo(cx - 4.5, cy - d * 2);
  g.lineTo(cx, cy + d * 2.5);
  g.lineTo(cx + 4.5, cy - d * 2);
  g.lineWidth = 2.2;
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.strokeStyle = '#ffffff';
  g.stroke();

  const img = new Image(MARKER_W, MARKER_H);
  img.onload = () => chart?.update('none');
  img.src = cv.toDataURL();
  markerCache[side] = img;
  return img;
}

// ---------- Public API ----------

export async function showChart(backtestId) {
  try {
    const data = await fetch('/api/backtest/results').then(r => r.json());
    const results = data.data?.results || data.results || [];
    const result = results.find(r => r.id === backtestId);
    if (!result?.result?.chart_data?.candles?.length) {
      showMessage('Chart data is not available for this backtest.');
      return;
    }
    const section = $('chart-section');
    section.classList.add('open');
    currentResult = result;
    render(result);
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    console.error('Error loading chart:', error);
    showMessage('Could not load the chart.');
  }
}

export function closeChart() {
  if (isFullscreen()) exitFullscreen();
  stopMotion();
  $('chart-section').classList.remove('open');
  chart?.destroy();
  chart = null;
  currentResult = null;
}

export function setModeCompare() { setMode('compare'); }
export function setModePrice() { setMode('price'); }

function setMode(next) {
  mode = next;
  try { localStorage.setItem(MODE_KEY, mode); } catch { /* private window */ }
  if (currentResult) render(currentResult);
  else syncModeUi();
}

function syncModeUi() {
  $('chart-section').dataset.mode = mode;
  document.querySelectorAll('#bt-chart-mode button').forEach((b) => {
    const on = b.dataset.action === (mode === 'compare' ? 'chart-mode-compare' : 'chart-mode-price');
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', String(on));
  });
}

export function resetZoomChart() {
  if (!chart) return;
  const { min, max } = chart.$bounds;
  animateViewTo(min, max, BUTTON_EASE_MS);
}
export function zoomInChart() { zoomViewBy(0.8, null, BUTTON_EASE_MS); }
export function zoomOutChart() { zoomViewBy(1.25, null, BUTTON_EASE_MS); }
export function panLeftChart() { panViewBy(-0.15, BUTTON_EASE_MS); }
export function panRightChart() { panViewBy(0.15, BUTTON_EASE_MS); }

export function toggleTrades() {
  showTrades = !showTrades;
  setToggle('bt-toggle-trades', showTrades, 'Trades', 'Trades off');
  if (!chart) return;
  chart.data.datasets.forEach(ds => { if (ds.$trade) ds.hidden = !showTrades; });
  chart.update('none');
}

export function togglePortfolio() {
  showPortfolio = !showPortfolio;
  setToggle('bt-toggle-portfolio', showPortfolio, 'Portfolio', 'Portfolio off');
  if (!chart) return;
  const ds = chart.data.datasets.find(d => d.$portfolio);
  if (!ds) return;   // only the "Price & trades" view has this line
  ds.hidden = !showPortfolio;
  chart.options.scales.y1.display = showPortfolio;
  chart.update('none');
}

export function toggleFullscreen() {
  if (isFullscreen()) exitFullscreen();
  else {
    const el = $('chart-section');
    (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el);
  }
}

// ---------- Render ----------

function render(result) {
  const r = result.result;
  const data = r.chart_data;
  stopMotion();
  chart?.destroy();
  syncModeUi();

  const candles = data.candles.map(c => ({
    x: new Date(c.timestamp).getTime(), o: c.open, h: c.high, l: c.low, c: c.close,
  }));
  const portfolio = (data.portfolio_values || []).map(p => ({ x: new Date(p.timestamp).getTime(), y: p.value }));
  const step = candleStepMs(candles);
  // Oldest first, each sale linked to the purchase it closes
  const trades = window.TradeWords.pairTrades(data.trades.map(t => ({ ...t, x: new Date(t.timestamp).getTime() })));

  // Header: pair, candle size, dates, and how the run did
  const daily = step >= 20 * 3600e3;
  const fmt = (t) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  $('bt-chart-sub').innerHTML =
    `BTC/USD · <b>${daily ? 'daily' : '1h'}</b> candles · ${fmt(candles[0].x)} → ${fmt(candles[candles.length - 1].x)}`;
  $('bt-candle-count').textContent = `${candles.length.toLocaleString()} candles`;
  const pill = $('bt-chart-result');
  pill.textContent = `Strategy ${signedPct(r.pnl_pct)} · Holding ${signedPct(r.buy_hold_pct)}`;
  pill.className = `status-pill ${r.pnl_pct >= r.buy_hold_pct ? 'up' : 'down'}`;
  pill.title = 'Strategy return vs. just holding BTC over this test';

  const pad = step * 2;
  const bounds = { min: candles[0].x - pad, max: candles[candles.length - 1].x + pad };
  const ctx2d = $('backtestChart').getContext('2d');
  const built = mode === 'compare'
    ? compareConfig(r, candles, portfolio, trades, step, daily)
    : priceConfig(candles, portfolio, trades);

  built.options.scales.x = {
    type: 'time',
    min: bounds.min,
    max: bounds.max,
    adapters: { date: { zone: Intl.DateTimeFormat().resolvedOptions().timeZone } },
    time: {
      displayFormats: { hour: 'MMM dd HH:mm', day: 'MMM dd', week: 'MMM dd', month: 'MMM yyyy' },
      tooltipFormat: 'MMM dd, yyyy HH:mm',
    },
    ticks: { color: '#8b949e', autoSkip: true, maxRotation: 0, font: { size: 11 } },
    grid: { color: 'rgba(255,255,255,0.045)' },
    border: { display: false },
    offset: mode === 'price',
  };
  built.options.responsive = true;
  built.options.maintainAspectRatio = false;
  built.options.animation = { duration: 300, easing: 'easeOutQuart' };
  built.options.plugins.legend = { display: false };
  // Pinch zoom on touch screens; wheel, drag and buttons are handled below
  built.options.plugins.zoom = {
    pan: { enabled: false },
    zoom: { wheel: { enabled: false }, pinch: { enabled: true }, drag: { enabled: false }, mode: 'x',
            onZoomComplete: () => { fitY(); chart.update('none'); } },
    limits: { x: { min: bounds.min, max: bounds.max, minRange: step * MIN_VISIBLE_CANDLES } },
  };

  chart = new Chart(ctx2d, built);
  chart.$bounds = bounds;
  chart.$minRange = step * MIN_VISIBLE_CANDLES;
  chart.$step = step;
  chart.$daily = daily;
  chart.$trades = trades;
  const used = r.strategies_used || [];
  chart.$trendOnly = used.length === 1 && /trend/i.test(used[0]);
  fitY();
  chart.update('none');
}

const signedPct = (v) => window.TradeWords.signedPct(v);

const baseTooltip = () => ({
  enabled: true,
  backgroundColor: 'rgba(13, 17, 23, 0.92)',
  titleColor: '#ffffff',
  bodyColor: '#e1e8ff',
  borderColor: 'rgba(255, 255, 255, 0.14)',
  borderWidth: 1,
  cornerRadius: 12,
  padding: 14,
  titleFont: { size: 14, weight: 'bold', family: FONT },
  bodyFont: { size: 13, family: FONT },
  bodySpacing: 6,
});

function tradeSet(label, side, points) {
  return {
    label, $trade: true, type: 'scatter', data: points, yAxisID: 'y',
    pointStyle: markerImage(side), pointRadius: 10, pointHoverRadius: 10, hitRadius: 20,
    backgroundColor: side === 'buy' ? '#2ecc71' : '#ff5e57',
    showLine: false, clip: false, order: 0, hidden: !showTrades,
  };
}

// ---- "Price & trades": candles, badges at the trade price, portfolio line

function priceConfig(candles, portfolio, trades) {
  const point = (t) => ({ ...t, y: t.price });
  const buys = trades.filter(t => t.side === 'buy').map(point);
  const sells = trades.filter(t => t.side !== 'buy').map(point);
  const tooltip = baseTooltip();
  Object.assign(tooltip, {
    mode: 'nearest',
    intersect: true,
    displayColors: false,
    callbacks: {
      title(items) {
        if (!items[0]) return '';
        return new Date(items[0].parsed.x).toLocaleString('en-US', {
          month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
        });
      },
      label: tooltipLabel,
    },
  });
  return {
    type: 'candlestick',
    data: {
      datasets: [
        {
          label: 'BTC/USD', $candles: true, data: candles, yAxisID: 'y',
          color: { up: UP, down: DOWN, unchanged: '#999' },
          borderColor: { up: UP, down: DOWN, unchanged: '#999' },
          borderWidth: 1.5, barPercentage: 0.7, categoryPercentage: 0.8, order: 10,
        },
        {
          label: 'Portfolio value', $portfolio: true, type: 'line', data: portfolio, yAxisID: 'y1',
          borderColor: 'rgba(255, 215, 0, 0.85)', borderWidth: 1.6, pointRadius: 0, pointHoverRadius: 4,
          pointHitRadius: 6, tension: 0.15, fill: false, order: 5, hidden: !showPortfolio,
        },
        ...(buys.length ? [tradeSet('Buy', 'buy', buys)] : []),
        ...(sells.length ? [tradeSet('Sell', 'sell', sells)] : []),
      ],
    },
    options: {
      interaction: { mode: 'nearest', intersect: true },
      scales: {
        y: {
          type: 'linear', position: 'right', beginAtZero: false,
          ticks: { color: '#8b949e', font: { size: 11 }, callback: (v) => v.toLocaleString('en-US', { maximumFractionDigits: 0 }) },
          grid: { color: 'rgba(255,255,255,0.045)' },
          border: { display: false },
        },
        y1: {
          type: 'linear', position: 'left', beginAtZero: false, display: showPortfolio,
          ticks: { color: 'rgba(255, 215, 0, 0.75)', font: { size: 11 }, callback: (v) => '$' + Math.round(v) },
          grid: { drawOnChartArea: false },
          border: { display: false },
        },
      },
      plugins: { tooltip },
    },
  };
}

// Hover picks the date under the cursor and shows both lines there,
// even when the cursor is on a Buy/Sell badge
Chart.Interaction.modes.btLines = (chart, e) => {
  const lines = chart.data.datasets.map((d, i) => [d, i]).filter(([d]) => d.$line);
  if (!lines.length || !chart.chartArea) return [];
  let x = chart.scales.x.getValueForPixel(e.x);
  // On a Buy/Sell badge, use that trade's day (badges sit up to ~26px from their point)
  chart.data.datasets.forEach((d, i) => {
    if (!d.$trade || d.hidden) return;
    chart.getDatasetMeta(i).data.forEach((el, j) => {
      if (Math.abs(el.x - e.x) <= 12 && Math.abs(el.y - e.y) <= 30) x = d.data[j].x;
    });
  });
  const data = lines[0][0].data;
  let lo = 0, hi = data.length - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (data[mid].x <= x) lo = mid; else hi = mid; }
  const idx = Math.abs(data[lo].x - x) <= Math.abs(data[hi].x - x) ? lo : hi;
  return lines
    .filter(([d]) => d.data[idx])
    .map(([, i]) => ({ element: chart.getDatasetMeta(i).data[idx], datasetIndex: i, index: idx }))
    .filter((it) => it.element);
};

// ---- "Strategy vs. holding": both lines in % from the start of the test

function compareConfig(r, candles, portfolio, trades, step, daily) {
  // Anchor both lines to the result card: the strategy starts at the money
  // the test began with, holding starts at the BTC price it bought at.
  const startValue = r.final_value - r.pnl;
  const lastClose = candles[candles.length - 1].c;
  const holdStart = lastClose / (1 + r.buy_hold_pct / 100);

  const t0 = candles[0].x - step;   // a "day 0" point where both are exactly 0%
  const hold = [{ x: t0, y: 0, price: holdStart }]
    .concat(candles.map(c => ({ x: c.x, y: (c.c / holdStart - 1) * 100, price: c.c })));
  const strat = [{ x: t0, y: 0, value: startValue }]
    .concat(portfolio.map(p => ({ x: p.x, y: (p.y / startValue - 1) * 100, value: p.y })));
  // The last point is the final result after closing costs, same as the card
  if (strat.length > 1) {
    const last = strat[strat.length - 1];
    strat[strat.length - 1] = { ...last, y: r.pnl_pct, value: r.final_value };
  }

  // Buy/Sell badges sit on the strategy line, on the point covering the trade
  const onLine = (t) => {
    let p = strat[0];
    for (const s of strat) { if (s.x <= t.x) p = s; else break; }
    return { ...t, x: p.x, y: p.y };
  };
  const buys = trades.filter(t => t.side === 'buy').map(onLine);
  const sells = trades.filter(t => t.side !== 'buy').map(onLine);

  const line = (label, color, points, extra = {}) => ({
    label, $line: true, type: 'line', data: points, yAxisID: 'y',
    borderColor: color, backgroundColor: color, borderWidth: 2.4,
    pointRadius: 0, pointHoverRadius: 5, pointHoverBorderWidth: 2, pointHoverBorderColor: '#0d1117',
    tension: 0.15, fill: false, order: 5, ...extra,
  });

  const tooltip = baseTooltip();
  Object.assign(tooltip, {
    mode: 'btLines',
    intersect: false,
    displayColors: true,
    boxPadding: 4,
    filter: (item) => item.dataset.$line,
    itemSort: (a, b) => b.parsed.y - a.parsed.y,
    callbacks: {
      title(items) {
        if (!items[0]) return '';
        if (items[0].raw.x === t0) return 'Start of the test';
        // Daily points are stamped at midnight UTC: show that calendar day
        const opts = daily
          ? { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }
          : { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' };
        return new Date(items[0].parsed.x).toLocaleString('en-US', opts);
      },
      label(item) {
        const p = item.raw;
        if (item.dataset.$strategy) return ` Your strategy: ${signedPct(p.y)}  (${money(p.value)})`;
        return ` Just holding BTC: ${signedPct(p.y)}  (BTC ${money(p.price, 0)})`;
      },
      labelColor(item) {
        const c = item.dataset.borderColor;
        return { borderColor: c, backgroundColor: c, borderRadius: 3 };
      },
      afterBody(items) {
        if (!items[0] || items[0].raw.x === t0) return '';
        const x = items[0].parsed.x;
        const lines = [''];
        // What the strategy was doing, and any trade in this candle
        let holding = false;
        const here = [];
        for (const t of chart.$trades) {
          if (t.x < x + chart.$step) holding = t.side === 'buy';
          if (t.x >= x && t.x < x + chart.$step) here.push(t);
        }
        here.forEach((t, n) => { if (n) lines.push(''); lines.push(...describeTrade(t)); });
        if (!here.length) lines.push(holding ? 'Strategy was holding BTC' : 'Strategy was in cash (not affected by BTC moves)');
        return lines;
      },
    },
  });

  return {
    type: 'line',
    data: {
      datasets: [
        line('Your strategy', STRATEGY_LINE, strat, { $strategy: true, order: 4 }),
        line('Just holding BTC', HOLD_LINE, hold, { borderWidth: 2, borderDash: [], order: 6 }),
        ...(buys.length ? [tradeSet('Buy', 'buy', buys)] : []),
        ...(sells.length ? [tradeSet('Sell', 'sell', sells)] : []),
      ],
    },
    options: {
      interaction: { mode: 'btLines', intersect: false },
      scales: {
        y: {
          type: 'linear', position: 'right',
          ticks: {
            color: '#8b949e',
            font: { size: 11 },
            callback(v, i, ticks) {
              // Hide the odd edge values (e.g. +21.31%) the fitted range adds
              const gap = ticks.length > 2 ? ticks[2].value - ticks[1].value : 0;
              if ((i === 0 || i === ticks.length - 1) && gap && Math.abs(v / gap - Math.round(v / gap)) > 1e-6) return '';
              const n = Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 1 });
              return (v > 0 ? '+' : v < 0 ? '−' : '') + n + '%';
            },
          },
          // The 0% line ("where you started") stands out
          grid: {
            color: (c) => (c.tick?.value === 0 ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.045)'),
            lineWidth: (c) => (c.tick?.value === 0 ? 1.5 : 1),
          },
          border: { display: false },
        },
      },
      plugins: { tooltip },
    },
  };
}

function tooltipLabel(ctx) {
  const raw = ctx.raw;
  if (raw && raw.o !== undefined) {
    return [`Open:  ${money(raw.o)}`, `High:  ${money(raw.h)}`, `Low:   ${money(raw.l)}`, `Close: ${money(raw.c)}`];
  }
  if (ctx.dataset.$portfolio) return `💼 Portfolio: ${money(ctx.parsed.y)}`;
  if (ctx.dataset.$trade) return describeTrade(raw);
  return ctx.formattedValue;
}

// Plain-words trade text is shared with the Dashboard chart (static/js/trade-words.js)
const describeTrade = (t) => window.TradeWords.describe(t, { trendOnly: chart?.$trendOnly });

// ---------- Helpers ----------

function candleStepMs(candles) {
  if (candles.length < 2) return 3600e3;
  const gaps = [];
  for (let i = 1; i < Math.min(candles.length, 50); i++) gaps.push(candles[i].x - candles[i - 1].x);
  gaps.sort((a, b) => a - b);
  return gaps[Math.floor(gaps.length / 2)] || 3600e3;
}

function setToggle(id, on, onLabel, offLabel) {
  const btn = $(id);
  btn.classList.toggle('active', on);
  btn.setAttribute('aria-pressed', String(on));
  btn.querySelector('.btn-label').textContent = on ? onLabel : offLabel;
}

function showMessage(text) {
  const status = $('backtest-status');
  if (status) status.innerHTML = `<p class="bt-msg err">${text}</p>`;
}

function isFullscreen() { return !!(document.fullscreenElement || document.webkitFullscreenElement); }
function exitFullscreen() { (document.exitFullscreen || document.webkitExitFullscreen)?.call(document); }

function onFullscreenChange() {
  const btn = $('bt-fullscreen-btn');
  if (!btn) return;
  const on = isFullscreen() && (document.fullscreenElement || document.webkitFullscreenElement) === $('chart-section');
  btn.classList.toggle('active', on);
  btn.querySelector('.btn-label').textContent = on ? 'Exit' : 'Fullscreen';
  setTimeout(() => { if (chart) { chart.resize(); fitY(); chart.update('none'); } }, 100);
}
document.addEventListener('fullscreenchange', onFullscreenChange);
document.addEventListener('webkitfullscreenchange', onFullscreenChange);

// What each vertical axis should show for the times between min and max
function axisRanges(min, max) {
  const out = {};
  const fit = (lo, hi, padShare) => {
    if (lo === Infinity) return null;
    const pad = (hi - lo) * padShare || Math.abs(hi) * 0.02 || 1;
    return { min: lo - pad, max: hi + pad };
  };
  if (chart.config.type === 'candlestick') {
    let lo = Infinity, hi = -Infinity;
    for (const c of chart.data.datasets.find(d => d.$candles).data) {
      if (c.x >= min && c.x <= max) { if (c.l < lo) lo = c.l; if (c.h > hi) hi = c.h; }
    }
    out.y = fit(lo, hi, 0.05);
    lo = Infinity; hi = -Infinity;
    for (const p of chart.data.datasets.find(d => d.$portfolio).data) {
      if (p.x >= min && p.x <= max) { if (p.y < lo) lo = p.y; if (p.y > hi) hi = p.y; }
    }
    out.y1 = fit(lo, hi, 0.08);
  } else {
    // Both % lines; leave room above for the Sell badges
    let lo = Infinity, hi = -Infinity;
    for (const ds of chart.data.datasets.filter(d => d.$line)) {
      for (const p of ds.data) {
        if (p.x >= min && p.x <= max) { if (p.y < lo) lo = p.y; if (p.y > hi) hi = p.y; }
      }
    }
    out.y = fit(lo, hi, 0.1);
  }
  return out;
}

function fitY() {
  if (!chart) return;
  const ranges = axisRanges(chart.options.scales.x.min, chart.options.scales.x.max);
  for (const [axis, r] of Object.entries(ranges)) if (r) Object.assign(chart.options.scales[axis], r);
}

// ---------- Smooth view motion ----------

let viewAnim = null, viewTarget = null, viewEaseMs = WHEEL_EASE_MS, viewLastT = 0;
let momentum = null, velocityX = 0;

function stopMomentum() { if (momentum) cancelAnimationFrame(momentum); momentum = null; velocityX = 0; }
function stopViewAnimation() { if (viewAnim) cancelAnimationFrame(viewAnim); viewAnim = null; viewTarget = null; }
function stopMotion() { stopMomentum(); stopViewAnimation(); }

function clampView(min, max) {
  const { min: lo, max: hi } = chart.$bounds;
  if (max - min < chart.$minRange) {
    const mid = (min + max) / 2;
    min = mid - chart.$minRange / 2;
    max = mid + chart.$minRange / 2;
  }
  const span = Math.min(max - min, hi - lo);
  if (min < lo) { min = lo; max = min + span; }
  if (max > hi) { max = hi; min = max - span; }
  return { min, max };
}

function baseView() {
  return viewTarget ? { ...viewTarget } : { min: chart.scales.x.min, max: chart.scales.x.max };
}

function animateViewTo(min, max, easeMs = WHEEL_EASE_MS) {
  if (!chart) return;
  stopMomentum();
  viewTarget = clampView(min, max);
  viewEaseMs = easeMs;
  if (!viewAnim) {
    viewLastT = performance.now();
    viewAnim = requestAnimationFrame(stepView);
  }
}

function stepView(t) {
  if (!chart || !viewTarget) { viewAnim = null; return; }
  const dt = Math.min(64, Math.max(0, t - viewLastT));
  viewLastT = t;
  const a = 1 - Math.exp(-dt / viewEaseMs);
  const x = chart.scales.x;
  let min = x.min + (viewTarget.min - x.min) * a;
  let max = x.max + (viewTarget.max - x.max) * a;
  const span = viewTarget.max - viewTarget.min;
  const done = Math.abs(viewTarget.min - min) + Math.abs(viewTarget.max - max) < span * 0.0005;
  if (done) { min = viewTarget.min; max = viewTarget.max; }
  chart.options.scales.x.min = min;
  chart.options.scales.x.max = max;

  // Ease the price axes toward what the target view will need
  for (const [axis, want] of Object.entries(axisRanges(viewTarget.min, viewTarget.max))) {
    if (!want) continue;
    const s = chart.scales[axis];
    chart.options.scales[axis].min = done ? want.min : s.min + (want.min - s.min) * a;
    chart.options.scales[axis].max = done ? want.max : s.max + (want.max - s.max) * a;
  }
  chart.update('none');

  if (done) { viewAnim = null; viewTarget = null; return; }
  viewAnim = requestAnimationFrame(stepView);
}

function panViewBy(fraction, easeMs = WHEEL_EASE_MS) {
  if (!chart) return;
  const v = baseView();
  const shift = (v.max - v.min) * fraction;
  animateViewTo(v.min + shift, v.max + shift, easeMs);
}

// factor < 1 zooms in; anchor = time under the cursor (null = centre)
function zoomViewBy(factor, anchor = null, easeMs = WHEEL_EASE_MS) {
  if (!chart) return;
  const v = baseView();
  const at = anchor ?? (v.min + v.max) / 2;
  animateViewTo(at - (at - v.min) * factor, at + (v.max - at) * factor, easeMs);
}

// ---------- Mouse, wheel and keyboard ----------

const canvas = $('backtestChart');
let dragging = false, dragStartX = 0, dragStartMin = 0, dragStartMax = 0;
let lastDragTime = 0, lastDragPos = 0;
const velocities = [];

canvas.addEventListener('mousedown', (e) => {
  if (!chart) return;
  stopMotion();
  dragging = true;
  dragStartX = e.clientX;
  dragStartMin = chart.scales.x.min;
  dragStartMax = chart.scales.x.max;
  lastDragTime = Date.now();
  lastDragPos = e.clientX;
  velocities.length = 0;
  canvas.style.cursor = 'grabbing';
});

canvas.addEventListener('mousemove', (e) => {
  if (!dragging || !chart) return;
  e.preventDefault();
  const now = Date.now();
  if (now > lastDragTime) {
    velocities.push((e.clientX - lastDragPos) / (now - lastDragTime));
    if (velocities.length > 5) velocities.shift();
    velocityX = velocities.reduce((s, v) => s + v, 0) / velocities.length;
  }
  lastDragTime = now;
  lastDragPos = e.clientX;

  const area = chart.chartArea;
  const perPx = (dragStartMax - dragStartMin) / (area.right - area.left);
  const shift = (e.clientX - dragStartX) * perPx;
  const v = clampView(dragStartMin - shift, dragStartMax - shift);
  chart.options.scales.x.min = v.min;
  chart.options.scales.x.max = v.max;
  fitY();
  chart.update('none');
});

function stopDragging() {
  if (!dragging) return;
  dragging = false;
  canvas.style.cursor = 'grab';
  glide();
}
canvas.addEventListener('mouseup', stopDragging);
canvas.addEventListener('mouseleave', stopDragging);

// Keep gliding after a quick drag, slowing down smoothly
function glide() {
  velocityX = Math.max(-MAX_FLING_PX_PER_MS, Math.min(MAX_FLING_PX_PER_MS, velocityX));
  if (Math.abs(velocityX) < 0.5) { velocityX = 0; return; }
  let lastT = performance.now();
  const step = (t) => {
    if (!chart || Math.abs(velocityX) < 0.03) { momentum = null; velocityX = 0; return; }
    const dt = Math.min(64, Math.max(0, t - lastT));
    lastT = t;
    const x = chart.scales.x;
    const area = chart.chartArea;
    const shift = velocityX * dt * (x.max - x.min) / (area.right - area.left);
    const { min: lo, max: hi } = chart.$bounds;
    if (x.min - shift < lo || x.max - shift > hi) { momentum = null; velocityX = 0; return; }
    chart.options.scales.x.min = x.min - shift;
    chart.options.scales.x.max = x.max - shift;
    fitY();
    chart.update('none');
    velocityX *= Math.exp(-dt / MOMENTUM_DECAY_MS);
    momentum = requestAnimationFrame(step);
  };
  momentum = requestAnimationFrame(step);
}

// Wheel: up/down zooms around the cursor; sideways or Shift+wheel scrolls
canvas.addEventListener('wheel', (e) => {
  if (!chart) return;
  e.preventDefault();
  const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
  const dx = e.deltaX * unit, dy = e.deltaY * unit;
  if (e.shiftKey || Math.abs(dx) > Math.abs(dy)) {
    const d = dx || (e.shiftKey ? dy : 0);
    panViewBy(Math.max(-120, Math.min(120, d)) * WHEEL_PAN_SENS);
    return;
  }
  const sens = e.ctrlKey ? WHEEL_ZOOM_SENS * 4 : WHEEL_ZOOM_SENS;   // trackpad pinch
  const rect = canvas.getBoundingClientRect();
  const anchor = chart.scales.x.getValueForPixel(e.clientX - rect.left);
  zoomViewBy(Math.exp(Math.max(-120, Math.min(120, dy)) * sens), anchor);
}, { passive: false });

// Keyboard works while the chart is open and you're not typing in a field
let keyRepeat = null;
document.addEventListener('keydown', (e) => {
  if (!chart || e.metaKey || e.ctrlKey || e.altKey) return;
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable) return;
  if (document.querySelector('dialog[open]')) return;
  const keys = {
    ArrowLeft: () => panViewBy(-KEY_PAN_STEP),
    ArrowRight: () => panViewBy(KEY_PAN_STEP),
    '+': zoomInChart, '=': zoomInChart,
    '-': zoomOutChart, _: zoomOutChart,
    0: resetZoomChart,
    f: toggleFullscreen, F: toggleFullscreen,
  };
  const action = keys[e.key];
  if (!action) return;
  e.preventDefault();
  if (e.repeat) return;
  action();
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    clearInterval(keyRepeat);
    keyRepeat = setInterval(action, 50);
  }
});
document.addEventListener('keyup', (e) => {
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { clearInterval(keyRepeat); keyRepeat = null; }
});
window.addEventListener('blur', () => { clearInterval(keyRepeat); keyRepeat = null; });
