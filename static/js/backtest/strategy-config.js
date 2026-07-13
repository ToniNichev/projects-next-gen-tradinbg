/**
 * Strategy Configuration Module
 * Loads and displays strategy configuration using HTML template elements.
 */

export function navigateToStrategy(url) {
  window.location.href = url;
}

/**
 * Fetch the dashboard's currently-configured enabled/disabled state for
 * each strategy, keyed by the short names used by the backtest override
 * checkboxes. Used to seed those checkboxes with real current state
 * instead of an arbitrary default when "Override strategies" is toggled on.
 */
export async function getCurrentStrategyEnabledMap() {
  const map = { ema: true, rsi_bb: false, macd: false };
  try {
    const response = await fetch('/api/strategies');
    if (!response.ok) return map;
    const data = await response.json();
    for (const s of data.strategies || []) {
      if (s.name === 'EMA_Crossover') map.ema = !!s.enabled;
      else if (s.name === 'RSI_BB_MeanReversion') map.rsi_bb = !!s.enabled;
      else if (s.name === 'MACD_Volume_Momentum') map.macd = !!s.enabled;
    }
  } catch (error) {
    console.error('Error loading strategy enabled map:', error);
  }
  return map;
}

export async function loadCurrentStrategyConfig() {
  try {
    const response = await fetch('/api/strategies');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    if (!data.multi_strategy_enabled) {
      document.getElementById('multi-strategy-badge').textContent = 'Disabled';
      document.getElementById('multi-strategy-badge').className = 'badge badge-disabled';
      document.getElementById('aggregation-mode').textContent = 'N/A';
      document.getElementById('min-confidence').textContent = 'N/A';
      document.getElementById('active-strategies-list').innerHTML =
        '<div class="text-muted">Multi-strategy system is disabled. Using legacy single strategy.</div>';
      return;
    }

    document.getElementById('multi-strategy-badge').textContent = 'Enabled';
    document.getElementById('multi-strategy-badge').className = 'badge badge-enabled';

    const modeDisplay = data.aggregation_mode
      .replace(/_/g, ' ')
      .split(' ')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
    document.getElementById('aggregation-mode').textContent = modeDisplay;
    document.getElementById('min-confidence').textContent = (data.min_confidence * 100).toFixed(0) + '%';

    const strategyAnchors = {
      'EMA_Crossover': 'strategy-ema-settings',
      'RSI_BB_MeanReversion': 'strategy-rsi-bb-settings',
      'MACD_Volume_Momentum': 'strategy-macd-settings',
    };

    const enabled = data.strategies.filter(s => s.enabled);
    const disabled = data.strategies.filter(s => !s.enabled);

    const strategiesHtml = data.strategies.map(strategy => {
      let icon = '🌊';
      if (strategy.name.includes('EMA')) icon = '📈';
      else if (strategy.name.includes('MACD')) icon = '📊';

      const statusClass = strategy.enabled ? 'strategy-enabled' : 'strategy-disabled';
      const statusBadge = strategy.enabled
        ? '<span class="badge badge-enabled" style="font-size:0.65rem;margin-left:0.5rem;">✓ Active</span>'
        : '<span class="badge badge-disabled" style="font-size:0.65rem;margin-left:0.5rem;">✗ Disabled</span>';
      const weight = strategy.enabled
        ? `<span class="text-muted" style="font-size:0.875rem;"> · Weight: ${strategy.weight.toFixed(1)}</span>`
        : '<span style="color:#e74c3c;font-size:0.8rem;"> · Will NOT be used in backtest</span>';

      const anchor = strategyAnchors[strategy.name] || 'strategySettings';
      const configUrl = `/strategy-config#${anchor}`;

      return `
        <div class="strategy-card ${statusClass}" data-action="navigate" data-url="${configUrl}" title="Click to configure ${strategy.name}">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span>
              <span class="strategy-icon">${icon}</span>
              <strong class="strategy-name">${strategy.name}</strong>${statusBadge}
              <span class="config-hint">⚙️ Click to configure</span>
            </span>
            ${weight}
          </div>
        </div>`;
    }).join('');

    let warningHtml = '';
    if (disabled.length > 0) {
      const names = disabled.map(s => s.name).join(', ');
      warningHtml = `
        <div class="strategy-warning">
          ⚠️ <strong>${disabled.length} strategy disabled:</strong> ${names}<br>
          <span style="opacity:0.9;font-size:0.75rem;">Enable in <a href="/strategy-config" style="color:#e74c3c;">Strategy Configuration</a> to include in backtest</span>
        </div>`;
    }

    document.getElementById('active-strategies-list').innerHTML = strategiesHtml + warningHtml;

    const runBtn = document.getElementById('run-current-text');
    if (disabled.length > 0) {
      runBtn.innerHTML = `🚀 Run Backtest (${enabled.length}/${data.strategies.length} Strategies Active)`;
    } else {
      runBtn.textContent = `🚀 Run Backtest (All ${data.strategies.length} Strategies)`;
    }
  } catch (error) {
    console.error('Error loading strategy config:', error);
    document.getElementById('active-strategies-list').innerHTML =
      '<div style="color:var(--accent-red);">⚠️ Could not load strategy configuration</div>';
  }
}

// Event delegation for strategy card navigation
document.addEventListener('click', (e) => {
  const navTrigger = e.target.closest('[data-action="navigate"]');
  if (navTrigger?.dataset.url) {
    window.location.href = navTrigger.dataset.url;
  }
});

export async function loadCurrentPresetInfo() {
  const status = document.getElementById('backtest-status');

  try {
    const response = await fetch('/api/config/debug');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    if (!data.success) {
      status.innerHTML = '<p class="text-danger">Failed to load configuration</p>';
      return;
    }

    const config = data.config_summary;
    const source = data.has_database && data.database_configs_count > 0
      ? `Database (${data.database_configs_count} parameters)`
      : 'Environment (.env file)';

    const template = document.getElementById('config-info-template');
    const clone = template.content.cloneNode(true);

    clone.querySelector('[data-field="source"]').textContent = source;
    clone.querySelector('[data-field="stop_loss"]').textContent = (config.stop_loss_pct * 100).toFixed(1) + '%';
    clone.querySelector('[data-field="take_profit"]').textContent = (config.take_profit_pct * 100).toFixed(1) + '%';
    clone.querySelector('[data-field="position_size"]').textContent = (config.order_pct * 100).toFixed(0) + '%';
    clone.querySelector('[data-field="aggregation"]').textContent = config.strategy_aggregation_mode;
    clone.querySelector('[data-field="confidence"]').textContent = (config.min_signal_confidence * 100).toFixed(0) + '%';

    const pills = clone.querySelector('[data-field="strategy-pills"]');
    const strategies = [
      { label: 'EMA', enabled: config.strategy_ema_enabled, weight: config.strategy_ema_weight },
      { label: 'RSI+BB', enabled: config.strategy_rsi_bb_enabled, weight: config.strategy_rsi_bb_weight },
      { label: 'MACD', enabled: config.strategy_macd_enabled, weight: config.strategy_macd_weight },
    ];

    for (const s of strategies) {
      const pill = document.createElement('span');
      pill.className = `config-strategy-pill ${s.enabled ? 'enabled' : 'disabled'}`;
      pill.textContent = `${s.label}: ${s.enabled ? '✓ Enabled' : '✗ Disabled'} (${s.weight}x)`;
      pills.appendChild(pill);
    }

    status.innerHTML = '';
    status.appendChild(clone);
    status.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    status.innerHTML = `<p class="text-danger">Error loading configuration: ${error.message}</p>`;
  }
}

export async function populateProgressInfo(daysBack, endDate) {
  try {
    const [configResponse, stratResponse] = await Promise.all([
      fetch('/api/config/debug'),
      fetch('/api/strategies'),
    ]);

    const configData = await configResponse.json();
    const stratData = await stratResponse.json();

    if (configData.success) {
      const config = configData.config_summary;
      document.getElementById('progress-symbol').textContent = config.symbol || 'BTC/USDT';
      document.getElementById('progress-timeframe').textContent = config.timeframe || '1h';
    }

    if (endDate) {
      const end = new Date(`${endDate}T00:00:00Z`);
      const start = new Date(end.getTime() - daysBack * 86400000);
      const fmt = (d) => d.toISOString().slice(0, 10);
      document.getElementById('progress-period').textContent = `${fmt(start)} → ${fmt(end)}`;
    } else {
      document.getElementById('progress-period').textContent = `${daysBack} days`;
    }

    if (stratData.strategies) {
      const enabled = stratData.strategies.filter(s => s.enabled);
      const names = enabled.map(s => {
        if (s.name.includes('EMA')) return 'EMA';
        if (s.name.includes('RSI')) return 'RSI+BB';
        if (s.name.includes('MACD')) return 'MACD';
        if (s.name.includes('LLM')) return 'LLM';
        return s.name;
      });

      const el = document.getElementById('progress-strategies');
      el.textContent = enabled.length > 0 ? names.join(', ') : 'None';
      el.style.color = enabled.length > 0 ? 'var(--accent-green)' : 'var(--accent-red)';
    }
  } catch (error) {
    console.error('Error populating progress info:', error);
    document.getElementById('progress-symbol').textContent = 'BTC/USDT';
    document.getElementById('progress-timeframe').textContent = '1h';
    document.getElementById('progress-period').textContent = `${daysBack} days`;
    document.getElementById('progress-strategies').textContent = 'Loading...';
  }
}
