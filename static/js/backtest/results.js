/**
 * Backtest Results Module
 * Shows finished backtests as cards, lets you pick some to compare.
 */

let selectedResults = new Set();
let previousResultIds = new Set();
let renderedCards = new Map();
let firstLoad = true;

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

const money = (v) => `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const signed = (v, digits = 2) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(digits)}`;
const tone = (v) => (v >= 0 ? 'pos' : 'neg');

function periodLabel(days) {
  const d = Number(days);
  if (d === 365) return '1 year';
  if (d === 180) return '6 months';
  return `${d} days`;
}

function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
}

function windowText(result) {
  const r = result.result;
  const start = r.window_start || result.parameters?.window_start;
  const end = r.window_end || result.parameters?.window_end;
  return start && end ? `${fmtDate(start)} → ${fmtDate(end)}` : '';
}

/** Win rate over closed round trips (sells), not over every fill. */
function winRate(r) {
  const closed = (r.winning_trades || 0) + (r.losing_trades || 0);
  return closed > 0 ? (r.winning_trades / closed) * 100 : null;
}

/** A bar from the middle: right for gains, left for losses. */
function barHtml(pct, scale) {
  const w = Math.min(Math.abs(pct) / scale, 1) * 50;
  const side = pct >= 0 ? `left:50%` : `right:50%`;
  return `<div class="rc-bar"><i class="${tone(pct)}" style="${side};width:${w.toFixed(1)}%"></i></div>`;
}

function buildResultCardHtml(result) {
  const r = result.result;
  const edge = r.pnl_pct - r.buy_hold_pct;
  const hasChart = r.chart_data?.candles?.length > 0;
  const scale = Math.max(Math.abs(r.pnl_pct), Math.abs(r.buy_hold_pct), 1);
  const startValue = r.final_value - r.pnl;
  const wr = winRate(r);
  const strategies = (r.strategies_used || []).map(s => `<span>${escapeHtml(s)}</span>`).join('');
  const selected = selectedResults.has(result.id);

  const params = Object.entries(result.parameters || {})
    .filter(([k]) => k !== 'window_start' && k !== 'window_end');
  const paramsHtml = params.length
    ? `<details class="rc-params">
        <summary>Settings changed for this run</summary>
        <table class="params-table">
          ${params.map(([k, v]) =>
            `<tr><td>${escapeHtml(k.replace(/^strategy_/, '').replace(/_/g, ' '))}</td><td>${escapeHtml(typeof v === 'boolean' ? (v ? 'On' : 'Off') : v)}</td></tr>`
          ).join('')}
        </table>
      </details>`
    : '';

  return `
    <div class="rc-top">
      <div class="rc-title">
        <strong>${escapeHtml(periodLabel(result.days_back))}</strong>
        <span class="rc-dates">${escapeHtml(windowText(result))}</span>
        <div class="rc-strats">${strategies}</div>
      </div>
      <span class="rc-verdict">${edge >= 0 ? 'Beat' : 'Trailed'} holding by ${Math.abs(edge).toFixed(1)} pts</span>
    </div>
    <div class="rc-compare">
      <div class="rc-big">
        <span>Strategy</span>
        <b class="${tone(r.pnl_pct)}">${signed(r.pnl_pct)}%</b>
        ${barHtml(r.pnl_pct, scale)}
      </div>
      <div class="rc-big">
        <span>Just holding BTC</span>
        <b class="${tone(r.buy_hold_pct)}">${signed(r.buy_hold_pct)}%</b>
        ${barHtml(r.buy_hold_pct, scale)}
      </div>
    </div>
    <div class="rc-stats">
      <div><span>Ending value</span><b>${money(r.final_value)}</b></div>
      <div><span>Profit / loss</span><b class="${tone(r.pnl)}">${r.pnl >= 0 ? '+' : '−'}${money(Math.abs(r.pnl))}</b></div>
      <div><span>Trades</span><b>${r.trades}</b></div>
      <div><span>Win rate</span><b>${wr === null ? '—' : `${wr.toFixed(0)}%`}</b></div>
      <div title="Largest fall from a high point during the run"><span>Worst drop</span><b>${r.max_drawdown_pct == null ? '—' : `−${Number(r.max_drawdown_pct).toFixed(1)}%`}</b></div>
    </div>
    <div class="rc-foot">
      ${hasChart ? `<button type="button" class="bt-btn sm" data-action="show-chart" data-backtest-id="${escapeHtml(result.id)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 6-6"/></svg>
        View chart</button>` : ''}
      <button type="button" class="bt-btn sm ${selected ? 'on' : ''}" data-action="select-result" data-result-id="${escapeHtml(result.id)}" aria-pressed="${selected}">
        ${selected ? 'Selected' : 'Select'}
      </button>
      <span class="rc-when">Started with ${money(startValue)} · run ${escapeHtml(new Date(result.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }))}</span>
    </div>
    ${paramsHtml}`;
}

function emptyHtml() {
  return `<div class="results-empty"><strong>No backtests yet</strong><span>Pick a period above and press Run backtest.</span></div>`;
}

export async function loadResults() {
  const container = document.getElementById('results-container');
  try {
    const response = await fetch('/api/backtest/results');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    const results = (data.data?.results || data.results || [])
      .filter(r => r.status === 'completed' && r.result)
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    if (results.length === 0) {
      container.innerHTML = emptyHtml();
      renderedCards.clear();
      previousResultIds = new Set();
      firstLoad = false;
      return;
    }

    const currentIds = new Set(results.map(r => r.id));
    const newIds = firstLoad ? new Set() : new Set([...currentIds].filter(id => !previousResultIds.has(id)));

    // Drop cards that no longer exist and the empty message
    for (const [id, el] of renderedCards) {
      if (!currentIds.has(id)) { el.remove(); renderedCards.delete(id); selectedResults.delete(id); }
    }
    container.querySelectorAll('.results-empty').forEach(el => el.remove());

    results.forEach((result, index) => {
      let card = renderedCards.get(result.id);
      if (!card) {
        card = document.createElement('div');
        card.className = 'result-card';
        card.dataset.resultId = result.id;
        card.innerHTML = buildResultCardHtml(result);
        const edge = result.result.pnl_pct - result.result.buy_hold_pct;
        card.classList.add(edge >= 0 ? 'beat' : 'trail');
        renderedCards.set(result.id, card);
        if (newIds.has(result.id)) card.classList.add('new-result');
      }
      card.classList.toggle('selected', selectedResults.has(result.id));
      const ref = container.children[index];
      if (ref !== card) container.insertBefore(card, ref || null);
    });

    previousResultIds = currentIds;
    firstLoad = false;
    updateCompareButton();

    if (newIds.size > 0) {
      const first = container.querySelector('.result-card.new-result');
      if (first) setTimeout(() => first.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
    }
  } catch (error) {
    console.error('Error loading results:', error);
  }
}

function updateCompareButton() {
  document.getElementById('selected-count').textContent = selectedResults.size;
  document.getElementById('compare-btn').disabled = selectedResults.size < 2;
}

export function toggleSelection(id) {
  if (selectedResults.has(id)) selectedResults.delete(id);
  else selectedResults.add(id);
  updateCompareButton();

  const card = renderedCards.get(id);
  if (!card) return;
  const on = selectedResults.has(id);
  card.classList.toggle('selected', on);
  const btn = card.querySelector('[data-action="select-result"]');
  if (btn) {
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-pressed', String(on));
    btn.textContent = on ? 'Selected' : 'Select';
  }
}

export async function compareSelected() {
  if (selectedResults.size < 2) return;

  const response = await fetch('/api/backtest/results');
  const data = await response.json();
  const allResults = data.data?.results || data.results || [];
  const results = allResults.filter(r => selectedResults.has(r.id) && r.status === 'completed');
  if (results.length < 2) return;

  const best = (key, pickMax = true) => {
    const vals = results.map(r => r.result[key]).filter(v => v != null);
    return pickMax ? Math.max(...vals) : Math.min(...vals);
  };
  const bestPct = best('pnl_pct');
  const bestDd = best('max_drawdown_pct', false);
  const mark = (cond) => (cond ? 'metric-best' : '');

  document.getElementById('comparison-content').innerHTML = `
    <div class="comparison-grid">
      ${results.map(result => {
        const r = result.result;
        const edge = r.pnl_pct - r.buy_hold_pct;
        const wr = winRate(r);
        return `
          <div class="comparison-card">
            <h3>${escapeHtml(periodLabel(result.days_back))}</h3>
            <p class="cmp-dates">${escapeHtml(windowText(result))} · ${escapeHtml((r.strategies_used || []).join(', '))}</p>
            <table class="params-table">
              <tr><td>Strategy</td><td class="${mark(r.pnl_pct === bestPct)} ${tone(r.pnl_pct)}">${signed(r.pnl_pct)}%</td></tr>
              <tr><td>Just holding</td><td class="${tone(r.buy_hold_pct)}">${signed(r.buy_hold_pct)}%</td></tr>
              <tr><td>Difference</td><td class="${tone(edge)}">${signed(edge, 1)} pts</td></tr>
              <tr><td>Ending value</td><td>${money(r.final_value)}</td></tr>
              <tr><td>Trades</td><td>${r.trades}</td></tr>
              <tr><td>Win rate</td><td>${wr === null ? '—' : `${wr.toFixed(0)}%`}</td></tr>
              <tr><td>Worst drop</td><td class="${mark(r.max_drawdown_pct === bestDd)}">${r.max_drawdown_pct == null ? '—' : `−${Number(r.max_drawdown_pct).toFixed(1)}%`}</td></tr>
            </table>
          </div>`;
      }).join('')}
    </div>`;

  document.getElementById('comparison-modal').style.display = 'block';
}

export function closeComparison() {
  document.getElementById('comparison-modal').style.display = 'none';
}

export async function clearResults() {
  if (!confirm('Clear all backtest results?')) return;

  const status = document.getElementById('backtest-status');
  try {
    const response = await fetch('/api/backtest/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) throw new Error('Failed to clear results');

    const data = await response.json();
    selectedResults.clear();
    renderedCards.clear();
    previousResultIds.clear();
    updateCompareButton();

    status.innerHTML = `<p class="bt-msg ok">${escapeHtml(data.message || 'Results cleared')}</p>`;
    setTimeout(() => { status.innerHTML = ''; }, 3000);
    loadResults();
  } catch (error) {
    console.error('Error clearing results:', error);
    status.innerHTML = '<p class="bt-msg err">Could not clear results. Please try again.</p>';
  }
}

// Card buttons
document.addEventListener('click', (e) => {
  const chartBtn = e.target.closest('[data-action="show-chart"]');
  if (chartBtn) {
    window.BacktestChart?.showChart?.(chartBtn.dataset.backtestId);
    return;
  }
  const pick = e.target.closest('[data-action="select-result"]');
  if (pick) toggleSelection(pick.dataset.resultId);
});

// Close the compare view with Escape or a click on the backdrop
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeComparison();
});
document.getElementById('comparison-modal')?.addEventListener('click', (e) => {
  if (e.target.id === 'comparison-modal') closeComparison();
});
