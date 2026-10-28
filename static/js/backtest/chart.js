/**
 * Backtest chart: candles, the strategy's trades and the portfolio value.
 *
 * Looks and moves like the Dashboard's price chart: same colours, axes,
 * tooltips and Buy/Sell badges; smooth wheel zoom around the cursor,
 * drag with momentum, Shift+wheel to scroll, keyboard and fullscreen.
 * The price axis always fits the candles in view.
 */

let chart = null;
let showTrades = true;
let showPortfolio = true;

const UP = '#58D68D';
const DOWN = '#ff5e57';
const FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const EXIT_REASONS = {
  signal: 'Strategy signal',
  backtest_end: 'End of test (valued at the last price)',
  stop_loss: 'Stop loss',
  take_profit: 'Take profit',
  trailing_stop: 'Trailing stop',
};
const STRATEGY_NAMES = {
  Aggregated: 'Bot',
  Trend_Hold: 'Trend Hold',
  EMA_Crossover: 'EMA Crossover',
  RSI_BB_MeanReversion: 'RSI + Bollinger',
  MACD_Volume_Momentum: 'MACD + Volume',
};

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
  if (ds) ds.hidden = !showPortfolio;
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

  const candles = data.candles.map(c => ({
    x: new Date(c.timestamp).getTime(), o: c.open, h: c.high, l: c.low, c: c.close,
  }));
  const portfolio = (data.portfolio_values || []).map(p => ({ x: new Date(p.timestamp).getTime(), y: p.value }));
  const step = candleStepMs(candles);

  // Header: pair, candle size, dates, and how the run did
  const daily = step >= 20 * 3600e3;
  const fmt = (t) => new Date(t).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  $('bt-chart-sub').innerHTML =
    `BTC/USD · <b>${daily ? 'daily' : '1h'}</b> candles · ${fmt(candles[0].x)} → ${fmt(candles[candles.length - 1].x)}`;
  $('bt-candle-count').textContent = `${candles.length.toLocaleString()} candles`;
  const pill = $('bt-chart-result');
  const pct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
  pill.textContent = `Strategy ${pct(r.pnl_pct)} · Holding ${pct(r.buy_hold_pct)}`;
  pill.className = `status-pill ${r.pnl_pct >= r.buy_hold_pct ? 'up' : 'down'}`;
  pill.title = 'Strategy return vs. just holding BTC over this test';

  const tradePoint = (t) => ({ ...t, x: new Date(t.timestamp).getTime(), y: t.price });
  const buys = data.trades.filter(t => t.side === 'buy').map(tradePoint);
  const sells = data.trades.filter(t => t.side !== 'buy').map(tradePoint);
  const tradeSet = (label, side, points) => ({
    label, $trade: true, type: 'scatter', data: points, yAxisID: 'y',
    pointStyle: markerImage(side), pointRadius: 10, pointHoverRadius: 10, hitRadius: 20,
    backgroundColor: side === 'buy' ? '#2ecc71' : '#ff5e57',
    showLine: false, clip: false, order: 0, hidden: !showTrades,
  });

  const pad = step * 2;
  const bounds = { min: candles[0].x - pad, max: candles[candles.length - 1].x + pad };

  chart = new Chart($('backtestChart').getContext('2d'), {
    type: 'candlestick',
    data: {
      datasets: [
        {
          label: 'BTC/USD', data: candles, yAxisID: 'y',
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
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300, easing: 'easeOutQuart' },
      interaction: { mode: 'nearest', intersect: true },
      scales: {
        x: {
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
          offset: true,
        },
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
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          mode: 'nearest',
          intersect: true,
          backgroundColor: 'rgba(13, 17, 23, 0.92)',
          titleColor: '#ffffff',
          bodyColor: '#e1e8ff',
          borderColor: 'rgba(255, 255, 255, 0.14)',
          borderWidth: 1,
          cornerRadius: 12,
          padding: 14,
          displayColors: false,
          titleFont: { size: 14, weight: 'bold', family: FONT },
          bodyFont: { size: 13, family: FONT },
          bodySpacing: 6,
          callbacks: {
            title(items) {
              if (!items[0]) return '';
              return new Date(items[0].parsed.x).toLocaleString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit',
              });
            },
            label: tooltipLabel,
          },
        },
        // Pinch zoom on touch screens; wheel, drag and buttons are handled below
        zoom: {
          pan: { enabled: false },
          zoom: { wheel: { enabled: false }, pinch: { enabled: true }, drag: { enabled: false }, mode: 'x',
                  onZoomComplete: () => { fitY(); chart.update('none'); } },
          limits: { x: { min: bounds.min, max: bounds.max, minRange: step * MIN_VISIBLE_CANDLES } },
        },
      },
    },
  });
  chart.$bounds = bounds;
  chart.$minRange = step * MIN_VISIBLE_CANDLES;
  fitY();
  chart.update('none');
}

function tooltipLabel(ctx) {
  const raw = ctx.raw;
  if (raw && raw.o !== undefined) {
    return [`Open:  ${money(raw.o)}`, `High:  ${money(raw.h)}`, `Low:   ${money(raw.l)}`, `Close: ${money(raw.c)}`];
  }
  if (ctx.dataset.$portfolio) return `💼 Portfolio: ${money(ctx.parsed.y)}`;
  if (ctx.dataset.$trade) {
    const buy = raw.side === 'buy';
    const lines = [`${buy ? '🟢 BUY' : '🔴 SELL'}`, '', `💰 Price: ${money(raw.y)}`];
    if (raw.amount) {
      lines.push(`📊 Amount: ${raw.amount.toFixed(6)} BTC`);
      lines.push(`💵 Value: ${money(raw.notional || raw.amount * raw.y)}`);
    }
    if (raw.fee > 0) lines.push(`💸 Fee: ${money(raw.fee, 4)}`);
    if (raw.pnl != null) {
      const pct = raw.notional ? ` (${((raw.pnl / raw.notional) * 100).toFixed(2)}%)` : '';
      lines.push('', `${raw.pnl >= 0 ? '📈' : '📉'} P&L: ${raw.pnl >= 0 ? '+' : '−'}${money(Math.abs(raw.pnl))}${pct}`);
    }
    const reason = raw.exit_reason || raw.reason;
    if (!buy && reason) lines.push(`🎯 Why: ${EXIT_REASONS[reason] || reason.replace(/_/g, ' ')}`);
    if (raw.strategy_name) lines.push(`🤖 ${STRATEGY_NAMES[raw.strategy_name] || raw.strategy_name.replace(/_/g, ' ')}`);
    return lines;
  }
  return ctx.formattedValue;
}

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

// Price range (with padding) of the candles between two times
function priceRange(min, max) {
  let lo = Infinity, hi = -Infinity;
  for (const c of chart.data.datasets[0].data) {
    if (c.x >= min && c.x <= max) { if (c.l < lo) lo = c.l; if (c.h > hi) hi = c.h; }
  }
  if (lo === Infinity) return null;
  const pad = (hi - lo) * 0.05 || hi * 0.02;
  return { min: lo - pad, max: hi + pad };
}

// Portfolio axis follows the same window
function portfolioRange(min, max) {
  let lo = Infinity, hi = -Infinity;
  for (const p of chart.data.datasets[1].data) {
    if (p.x >= min && p.x <= max) { if (p.y < lo) lo = p.y; if (p.y > hi) hi = p.y; }
  }
  if (lo === Infinity) return null;
  const pad = (hi - lo) * 0.08 || hi * 0.02;
  return { min: lo - pad, max: hi + pad };
}

function fitY() {
  if (!chart) return;
  const min = chart.options.scales.x.min, max = chart.options.scales.x.max;
  const y = priceRange(min, max);
  if (y) Object.assign(chart.options.scales.y, y);
  const y1 = portfolioRange(min, max);
  if (y1) Object.assign(chart.options.scales.y1, y1);
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
  for (const [axis, range] of [['y', priceRange], ['y1', portfolioRange]]) {
    const want = range(viewTarget.min, viewTarget.max);
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
