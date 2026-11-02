/**
 * Names and colors shared by every page (window.UI).
 *
 * Strategy colors never reuse the pot colors (Trend Hold pot gold #FFD700,
 * Intraday pot pink #FF6B9D, Manual pot cyan #00D9FF), the buy/sell green
 * and red, or the "just holding BTC" blue. The same colors are CSS variables
 * (--strat-*) in base.html; keep the two in step.
 */
(function () {
  const STRATEGIES = {
    Trend_Hold:           { name: 'Trend Hold',            color: '#1abc9c' },
    RSI_BB_MeanReversion: { name: 'RSI + Bollinger Bands', color: '#a371f7' },
    MACD_Volume_Momentum: { name: 'MACD + Volume',         color: '#f39c12' },
    EMA_Crossover:        { name: 'EMA Crossover',         color: '#b5e853' },
    llm_pattern:          { name: 'LLM Pattern',           color: '#7d8cff' },
    Aggregated:           { name: 'Combined signal',       color: '#c9d1d9' },
    Manual:               { name: 'Manual',                color: '#00D9FF' },
  };
  const UNKNOWN = '#808080';

  const find = (key) => {
    if (!key) return null;
    if (STRATEGIES[key]) return STRATEGIES[key];
    if (/llm/i.test(key)) return STRATEGIES.llm_pattern;
    return null;
  };

  function strategyName(key) {
    const s = find(key);
    return s ? s.name : (key || 'Unknown');
  }

  function strategyColor(key) {
    const s = find(key);
    return s ? s.color : UNKNOWN;
  }

  // {key: name} and {key: color}, for code that wants a plain map
  const strategyNames = () => Object.fromEntries(Object.entries(STRATEGIES).map(([k, v]) => [k, v.name]));
  const strategyColors = () => ({
    ...Object.fromEntries(Object.entries(STRATEGIES).map(([k, v]) => [k, v.color])),
    LLM_Pattern: STRATEGIES.llm_pattern.color,
    Unknown: UNKNOWN,
  });

  // Text made safe to put inside HTML
  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // A panel's "updated 18:42" stamp. When a refresh fails the old numbers stay
  // on screen, so say so instead of failing quietly.
  const lastGood = {};
  function stamp(id, ok) {
    const el = document.getElementById(id);
    if (!el) return;
    const hhmm = (d) => d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (ok) {
      lastGood[id] = new Date();
      el.textContent = `updated ${hhmm(lastGood[id])}`;
      el.classList.remove('stale');
      el.title = '';
    } else {
      el.textContent = lastGood[id] ? `couldn't refresh · numbers from ${hhmm(lastGood[id])}` : "couldn't load";
      el.classList.add('stale');
      el.title = 'The last refresh failed. It tries again automatically.';
    }
  }

  window.UI = { STRATEGIES, strategyName, strategyColor, strategyNames, strategyColors, esc, stamp };
})();
