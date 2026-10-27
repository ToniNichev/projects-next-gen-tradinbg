/**
 * Strategy Configuration Module
 * Shows which strategies a backtest will use and the settings behind it.
 */

const NAMES = {
  Trend_Hold: 'Trend Hold',
  EMA_Crossover: 'EMA Crossover',
  RSI_BB_MeanReversion: 'RSI + Bollinger',
  MACD_Volume_Momentum: 'MACD + Volume',
  LLM_Pattern_Analysis: 'AI Pattern',
};

const displayName = (name) => NAMES[name] || name.replace(/_/g, ' ');

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

export function navigateToStrategy(url) {
  window.location.href = url;
}

/**
 * Which strategies are on right now, keyed by the override checkbox names.
 * Seeds the "Try others for this run" chips with the real current state.
 */
export async function getCurrentStrategyEnabledMap() {
  const map = { trend: false, ema: false, rsi_bb: false, macd: false };
  try {
    const response = await fetch('/api/strategies');
    if (!response.ok) return map;
    const data = await response.json();
    if (!(data.strategies || []).length) {
      const c = (await fetch('/api/config/debug').then(r => r.json())).config_summary || {};
      return { trend: !!c.strategy_trend_enabled, ema: !!c.strategy_ema_enabled,
               rsi_bb: !!c.strategy_rsi_bb_enabled, macd: !!c.strategy_macd_enabled };
    }
    for (const s of data.strategies || []) {
      if (s.name === 'Trend_Hold') map.trend = !!s.enabled;
      else if (s.name === 'EMA_Crossover') map.ema = !!s.enabled;
      else if (s.name === 'RSI_BB_MeanReversion') map.rsi_bb = !!s.enabled;
      else if (s.name === 'MACD_Volume_Momentum') map.macd = !!s.enabled;
    }
  } catch (error) {
    console.error('Error loading strategy enabled map:', error);
  }
  return map;
}

export async function loadCurrentStrategyConfig() {
  const list = document.getElementById('active-strategies-list');
  try {
    const response = await fetch('/api/strategies');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    let names = (data.strategies || []).filter(s => s.enabled).map(s => displayName(s.name));
    if (!(data.strategies || []).length) {
      // Strategy engine not running: fall back to the saved settings
      const cfg = await fetch('/api/config/debug').then(r => r.json()).catch(() => null);
      const c = cfg?.config_summary || {};
      names = [
        [c.strategy_trend_enabled, 'Trend Hold'], [c.strategy_ema_enabled, 'EMA Crossover'],
        [c.strategy_rsi_bb_enabled, 'RSI + Bollinger'], [c.strategy_macd_enabled, 'MACD + Volume'],
      ].filter(([on]) => on).map(([, n]) => n);
    }
    const chips = names.map(n => `<span class="bt-chip on">${escapeHtml(n)}</span>`);
    if (!names.length) chips.push('<span class="bt-chip warn">No strategy is on</span>');
    chips.push('<a class="bt-chip link" href="/strategy-config">Change on Strategies page</a>');
    list.innerHTML = chips.join('');
  } catch (error) {
    console.error('Error loading strategy config:', error);
    list.innerHTML = '<span class="bt-chip warn">Could not load strategies</span>';
  }
}

export async function loadCurrentPresetInfo() {
  const status = document.getElementById('backtest-status');

  // Second click hides the panel again
  if (status.querySelector('.config-info-panel')) {
    status.innerHTML = '';
    return;
  }

  try {
    const response = await fetch('/api/config/debug');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    if (!data.success) {
      status.innerHTML = '<p class="bt-msg err">Could not load the settings.</p>';
      return;
    }

    const config = data.config_summary;
    const source = data.has_database && data.database_configs_count > 0
      ? 'saved dashboard settings'
      : 'the .env file';
    const modes = { weighted_voting: 'Weighted vote', voting: 'Majority vote', unanimous: 'All must agree', any: 'Any one', best: 'Most confident' };

    const clone = document.getElementById('config-info-template').content.cloneNode(true);
    clone.querySelector('[data-field="source"]').textContent = source;
    clone.querySelector('[data-field="stop_loss"]').textContent = `${(config.stop_loss_pct * 100).toFixed(1)}%`;
    clone.querySelector('[data-field="take_profit"]').textContent = `${(config.take_profit_pct * 100).toFixed(1)}%`;
    clone.querySelector('[data-field="position_size"]').textContent = `${(config.order_pct * 100).toFixed(0)}%`;
    clone.querySelector('[data-field="aggregation"]').textContent =
      modes[config.strategy_aggregation_mode] || String(config.strategy_aggregation_mode).replace(/_/g, ' ');
    clone.querySelector('[data-field="confidence"]').textContent = `${(config.min_signal_confidence * 100).toFixed(0)}%`;

    const pills = clone.querySelector('[data-field="strategy-pills"]');
    const strategies = [
      { label: 'Trend Hold', enabled: config.strategy_trend_enabled },
      { label: 'EMA Crossover', enabled: config.strategy_ema_enabled },
      { label: 'RSI + Bollinger', enabled: config.strategy_rsi_bb_enabled },
      { label: 'MACD + Volume', enabled: config.strategy_macd_enabled },
    ];
    for (const s of strategies) {
      const pill = document.createElement('span');
      pill.className = `bt-chip ${s.enabled ? 'on' : 'off'}`;
      pill.textContent = `${s.label}${s.enabled ? '' : ' · off'}`;
      pills.appendChild(pill);
    }

    status.innerHTML = '';
    status.appendChild(clone);
    status.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    status.innerHTML = `<p class="bt-msg err">Could not load the settings: ${escapeHtml(error.message)}</p>`;
  }
}

/** Fill the progress panel. `overrides` is the per-run strategy choice, if any. */
export async function populateProgressInfo(daysBack, endDate, overrides = null) {
  const set = (id, text) => { document.getElementById(id).textContent = text; };

  const end = endDate ? new Date(`${endDate}T00:00:00Z`) : new Date();
  const start = new Date(end.getTime() - daysBack * 86400000);
  const fmt = (d) => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
  set('progress-period', `${fmt(start)} → ${fmt(end)}`);

  try {
    const [configResponse, stratResponse] = await Promise.all([
      fetch('/api/config/debug'),
      fetch('/api/strategies'),
    ]);
    const configData = await configResponse.json();
    const stratData = await stratResponse.json();

    if (configData.success) {
      set('progress-symbol', configData.config_summary.symbol || '-');
      set('progress-timeframe', configData.config_summary.timeframe || '-');
    }

    let names;
    if (overrides) {
      const keys = { strategy_trend_enabled: 'Trend Hold', strategy_ema_enabled: 'EMA', strategy_rsi_bb_enabled: 'RSI + BB', strategy_macd_enabled: 'MACD' };
      names = Object.entries(keys).filter(([k]) => overrides[k]).map(([, v]) => v);
    } else {
      names = (stratData.strategies || []).filter(s => s.enabled).map(s => displayName(s.name));
    }
    const el = document.getElementById('progress-strategies');
    el.textContent = names.length ? names.join(', ') : 'None';
    el.style.color = names.length ? '' : 'var(--accent-red)';
  } catch (error) {
    console.error('Error populating progress info:', error);
  }
}
