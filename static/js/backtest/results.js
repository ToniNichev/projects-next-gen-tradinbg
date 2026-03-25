/**
 * Backtest Results Module
 * Handles results display, selection, and comparison with DOM diffing.
 */

let selectedResults = new Set();
let previousResultIds = new Set();
let renderedCards = new Map();

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

function showLoadingSkeleton(container) {
  container.innerHTML = `
    <div class="result-card">
      <div class="skeleton skeleton-line" style="width:40%"></div>
      <div class="skeleton skeleton-line short"></div>
      <div class="result-stats">
        <div class="stat"><div class="skeleton skeleton-line"></div></div>
        <div class="stat"><div class="skeleton skeleton-line"></div></div>
        <div class="stat"><div class="skeleton skeleton-line"></div></div>
        <div class="stat"><div class="skeleton skeleton-line"></div></div>
      </div>
    </div>`;
}

function buildResultCardHtml(result) {
  const r = result.result;
  const pnlClass = r.pnl >= 0 ? 'text-success' : 'text-danger';
  const hasChart = r.chart_data && r.chart_data.candles && r.chart_data.candles.length > 0;

  const presetBadge = result.preset_name
    ? `<span class="badge badge-info" style="margin-left:0.5rem;">🎨 ${escapeHtml(result.preset_name)}</span>`
    : '';

  const chartButton = hasChart
    ? `<button data-action="show-chart" data-backtest-id="${escapeHtml(result.id)}" class="secondary" style="margin-left:1rem;padding:0.25rem 0.75rem;font-size:0.875rem;">📊 View Chart</button>`
    : '';

  const paramsHtml = Object.keys(result.parameters).length > 0
    ? `<details style="margin-top:1rem;">
        <summary style="cursor:pointer;color:var(--text-secondary);">Custom Parameters</summary>
        <table class="params-table">
          ${Object.entries(result.parameters).map(([k, v]) =>
            `<tr><td>${escapeHtml(k.replace(/_/g, ' '))}</td><td>${escapeHtml(typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v)}</td></tr>`
          ).join('')}
        </table>
      </details>`
    : '';

  return `
    <div class="result-header">
      <div>
        <strong>${escapeHtml(new Date(result.timestamp).toLocaleString())}</strong>
        <span class="text-muted"> · ${escapeHtml(result.days_back)} days</span>
        ${presetBadge}
        ${chartButton}
      </div>
      <div>
        <span class="status ${r.pnl >= 0 ? 'success' : 'danger'}">
          ${r.pnl >= 0 ? '+' : ''}${r.pnl_pct.toFixed(2)}%
        </span>
      </div>
    </div>
    <div class="result-stats">
      <div class="stat">
        <div class="stat-label">Final Value</div>
        <div class="stat-value">$${r.final_value.toFixed(2)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Total P&L</div>
        <div class="stat-value ${pnlClass}">${r.pnl >= 0 ? '+' : ''}$${r.pnl.toFixed(2)}</div>
      </div>
      <div class="stat">
        <div class="stat-label">Trades</div>
        <div class="stat-value">${r.trades}</div>
      </div>
      <div class="stat">
        <div class="stat-label">vs Buy & Hold</div>
        <div class="stat-value ${r.pnl_pct > r.buy_hold_pct ? 'text-success' : 'text-danger'}">
          ${(r.pnl_pct - r.buy_hold_pct).toFixed(2)}%
        </div>
      </div>
    </div>
    ${paramsHtml}`;
}

export async function loadResults() {
  const container = document.getElementById('results-container');
  try {
    const response = await fetch('/api/backtest/results');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    const results = (data.data?.results || data.results || [])
      .filter(r => r.status === 'completed' && r.result);

    if (results.length === 0) {
      container.innerHTML = '<p class="text-muted results-empty">No backtests run yet. Start a backtest above to see results.</p>';
      renderedCards.clear();
      return;
    }

    const currentResultIds = new Set(results.map(r => r.id));
    const newResultIds = new Set();
    currentResultIds.forEach(id => {
      if (!previousResultIds.has(id)) newResultIds.add(id);
    });

    const staleIds = new Set(renderedCards.keys());
    results.forEach(r => staleIds.delete(r.id));
    staleIds.forEach(id => {
      const el = renderedCards.get(id);
      if (el && el.parentNode) el.parentNode.removeChild(el);
      renderedCards.delete(id);
    });

    results.forEach((result, index) => {
      const hasChart = result.result.chart_data?.candles?.length > 0;
      let card = renderedCards.get(result.id);

      if (!card) {
        card = document.createElement('div');
        card.className = 'result-card';
        card.dataset.resultId = result.id;
        card.innerHTML = buildResultCardHtml(result);
        renderedCards.set(result.id, card);

        if (newResultIds.has(result.id)) {
          card.classList.add('new-result');
          setTimeout(() => card.classList.remove('new-result'), 2000);
        }
      }

      card.classList.toggle('selected', selectedResults.has(result.id));
      card.classList.toggle('has-chart', hasChart);

      const ref = container.children[index];
      if (ref !== card) {
        container.insertBefore(card, ref || null);
      }
    });

    // Remove any leftover text nodes / old empty messages
    while (container.children.length > results.length) {
      container.removeChild(container.lastChild);
    }

    previousResultIds = currentResultIds;

    if (newResultIds.size > 0) {
      setTimeout(() => {
        const firstNew = container.querySelector('.result-card.new-result');
        if (firstNew) firstNew.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 100);
    }
  } catch (error) {
    console.error('Error loading results:', error);
  }
}

export function toggleSelection(id) {
  if (selectedResults.has(id)) {
    selectedResults.delete(id);
  } else {
    selectedResults.add(id);
  }

  document.getElementById('selected-count').textContent = selectedResults.size;
  document.getElementById('compare-btn').disabled = selectedResults.size < 2;

  const card = renderedCards.get(id);
  if (card) card.classList.toggle('selected', selectedResults.has(id));
}

export async function compareSelected() {
  if (selectedResults.size < 2) return;

  const response = await fetch('/api/backtest/results');
  const data = await response.json();
  const allResults = data.data?.results || data.results || [];
  const results = allResults.filter(r => selectedResults.has(r.id) && r.status === 'completed');

  if (results.length < 2) return;

  // Find best values for highlighting
  const pnls = results.map(r => r.result.pnl);
  const bestPnl = Math.max(...pnls);
  const worstPnl = Math.min(...pnls);

  const comparison = document.getElementById('comparison-content');
  comparison.innerHTML = `
    <div class="comparison-grid">
      ${results.map(result => {
        const r = result.result;
        const pnlRank = r.pnl === bestPnl ? 'metric-best' : (r.pnl === worstPnl && results.length > 2 ? 'metric-worst' : '');
        const vsHold = r.pnl_pct - r.buy_hold_pct;
        const vsHoldClass = vsHold >= 0 ? 'text-success' : 'text-danger';

        return `
          <div class="comparison-card">
            <h3>${escapeHtml(new Date(result.timestamp).toLocaleString())}</h3>
            <p class="text-muted">${escapeHtml(result.days_back)} days backtest</p>
            <table class="params-table">
              <tr><td>P&L</td><td class="${pnlRank || (r.pnl >= 0 ? 'text-success' : 'text-danger')}">${r.pnl >= 0 ? '+' : ''}$${r.pnl.toFixed(2)}</td></tr>
              <tr><td>P&L %</td><td class="${r.pnl_pct >= 0 ? 'text-success' : 'text-danger'}">${r.pnl_pct.toFixed(2)}%</td></tr>
              <tr><td>Trades</td><td>${r.trades}</td></tr>
              <tr><td>Final Value</td><td>$${r.final_value.toFixed(2)}</td></tr>
              <tr><td>vs Buy & Hold</td><td class="${vsHoldClass}">${vsHold >= 0 ? '+' : ''}${vsHold.toFixed(2)}%</td></tr>
            </table>
            ${Object.keys(result.parameters).length > 0 ? `
              <h4 style="margin-top:1rem;">Parameters</h4>
              <table class="params-table">
                ${Object.entries(result.parameters).map(([k, v]) =>
                  `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(typeof v === 'boolean' ? (v ? 'Yes' : 'No') : v)}</td></tr>`
                ).join('')}
              </table>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;

  document.getElementById('comparison-modal').style.display = 'block';
}

export function closeComparison() {
  document.getElementById('comparison-modal').style.display = 'none';
}

export async function clearResults() {
  if (!confirm('Are you sure you want to clear all backtest results?')) return;

  try {
    const response = await fetch('/api/backtest/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!response.ok) throw new Error('Failed to clear results');

    const data = await response.json();
    selectedResults.clear();
    renderedCards.clear();
    previousResultIds.clear();
    document.getElementById('selected-count').textContent = '0';
    document.getElementById('compare-btn').disabled = true;

    const status = document.getElementById('backtest-status');
    status.innerHTML = `<p class="text-success">✓ ${escapeHtml(data.message)}</p>`;
    setTimeout(() => { status.innerHTML = ''; }, 3000);

    loadResults();
  } catch (error) {
    console.error('Error clearing results:', error);
    alert('Failed to clear results. Please try again.');
  }
}

// Event delegation for result card clicks
document.addEventListener('click', (e) => {
  const showChartBtn = e.target.closest('[data-action="show-chart"]');
  if (showChartBtn) {
    e.stopPropagation();
    const backtestId = showChartBtn.dataset.backtestId;
    if (window.BacktestChart && window.BacktestChart.showChart) {
      window.BacktestChart.showChart(backtestId);
    }
    return;
  }

  const card = e.target.closest('.result-card[data-result-id]');
  if (card) {
    toggleSelection(card.dataset.resultId);
  }
});
