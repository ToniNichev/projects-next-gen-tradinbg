/**
 * Backtest Chart Module
 * Renders candlestick charts with trade markers, HOD/LOD levels, and portfolio overlay.
 *
 * HOD/LOD levels are drawn via a lightweight Chart.js plugin instead of
 * creating 2 datasets per day, which previously caused performance issues
 * on longer backtests (60+ datasets for 30 days).
 */

let backtestChart = null;
let currentChartData = null;

const STRATEGY_COLORS = {
  'EMA_Crossover': '#00D9FF',
  'RSI_BB_MeanReversion': '#FF6B9D',
  'MACD_Volume_Momentum': '#FFD700',
  'llm_pattern': '#9D4EDD',
  'LLM_Pattern': '#9D4EDD',
  'Aggregated': '#FFFFFF',
  'Unknown': '#808080',
};

const STRATEGY_DISPLAY_NAMES = {
  'Aggregated': 'Multi-Strategy',
  'EMA_Crossover': 'EMA Crossover',
  'RSI_BB_MeanReversion': 'RSI+BB',
  'MACD_Volume_Momentum': 'MACD+Vol',
};

function getStrategyColor(name) {
  if (!name) return STRATEGY_COLORS.Unknown;
  return STRATEGY_COLORS[name] || STRATEGY_COLORS.Unknown;
}

function getStrategyDisplayName(name) {
  if (!name) return 'Unknown';
  if (name.includes('llm') || name.includes('LLM')) return 'LLM Pattern';
  return STRATEGY_DISPLAY_NAMES[name] || name;
}

// ---------- HOD/LOD Plugin ----------

function calculateDailyLevels(candles) {
  const levels = new Map();
  for (const candle of candles) {
    const t = new Date(candle.timestamp).getTime();
    const dateKey = new Date(candle.timestamp).toISOString().split('T')[0];
    const existing = levels.get(dateKey);
    if (!existing) {
      levels.set(dateKey, { high: candle.high, low: candle.low, start: t, end: t });
    } else {
      existing.high = Math.max(existing.high, candle.high);
      existing.low = Math.min(existing.low, candle.low);
      existing.end = t;
    }
  }
  return Array.from(levels.values());
}

const hodLodPlugin = {
  id: 'hodLod',
  _levels: [],

  afterDraw(chart) {
    const levels = this._levels;
    if (!levels.length) return;

    const { ctx, chartArea, scales: { x: xScale, y: yScale } } = chart;
    if (!xScale || !yScale) return;

    ctx.save();
    ctx.setLineDash([5, 5]);
    ctx.lineWidth = 1.5;

    for (const level of levels) {
      const x1 = xScale.getPixelForValue(level.start);
      const x2 = xScale.getPixelForValue(level.end);
      if (x2 < chartArea.left || x1 > chartArea.right) continue;

      const clampedX1 = Math.max(x1, chartArea.left);
      const clampedX2 = Math.min(x2, chartArea.right);

      const yHigh = yScale.getPixelForValue(level.high);
      ctx.strokeStyle = 'rgba(255, 99, 132, 0.6)';
      ctx.beginPath();
      ctx.moveTo(clampedX1, yHigh);
      ctx.lineTo(clampedX2, yHigh);
      ctx.stroke();

      const yLow = yScale.getPixelForValue(level.low);
      ctx.strokeStyle = 'rgba(75, 192, 192, 0.6)';
      ctx.beginPath();
      ctx.moveTo(clampedX1, yLow);
      ctx.lineTo(clampedX2, yLow);
      ctx.stroke();
    }

    ctx.restore();
  },
};

// ---------- Trade Grouping ----------

function groupTradesByStrategy(trades) {
  const grouped = {};
  for (const t of trades) {
    const name = t.strategy_name || 'Unknown';
    if (!grouped[name]) grouped[name] = { buy: [], sell: [] };

    const point = {
      x: new Date(t.timestamp).getTime(),
      y: t.price,
      reason: t.reason,
      pnl: t.pnl,
      side: t.side,
      amount: t.amount,
      strategy_name: t.strategy_name,
      confidence: t.confidence,
    };

    grouped[name][t.side === 'buy' ? 'buy' : 'sell'].push(point);
  }
  return grouped;
}

function calculateStrategyStats(tradesByStrategy) {
  const stats = {};
  for (const [name, trades] of Object.entries(tradesByStrategy)) {
    const all = [...trades.buy, ...trades.sell];
    const exits = trades.sell.filter(t => t.pnl != null);
    const wins = exits.filter(t => t.pnl > 0).length;
    const losses = exits.filter(t => t.pnl < 0).length;
    const total = wins + losses;
    const withConf = all.filter(t => t.confidence);
    const avgConf = withConf.length > 0
      ? withConf.reduce((s, t) => s + t.confidence, 0) / withConf.length
      : 0;

    stats[name] = {
      totalTrades: all.length,
      buyTrades: trades.buy.length,
      sellTrades: trades.sell.length,
      winningTrades: wins,
      losingTrades: losses,
      winRate: total > 0 ? (wins / total * 100) : 0,
      avgConfidence: avgConf,
    };
  }
  return stats;
}

// ---------- Public API ----------

export function showChart(backtestId) {
  fetch('/api/backtest/results')
    .then(res => res.json())
    .then(data => {
      const results = data.data?.results || data.results || [];
      const result = results.find(r => r.id === backtestId);
      if (!result?.result?.chart_data) {
        alert('Chart data not available for this backtest');
        return;
      }

      currentChartData = result.result.chart_data;
      const section = document.getElementById('chart-section');
      section.style.display = 'block';
      section.scrollIntoView({ behavior: 'smooth' });
      renderPriceChart(currentChartData);
    })
    .catch(error => {
      console.error('Error loading chart:', error);
      alert('Failed to load chart data');
    });
}

export function closeChart() {
  document.getElementById('chart-section').style.display = 'none';
  currentChartData = null;
  if (backtestChart) {
    backtestChart.destroy();
    backtestChart = null;
  }
}

// ---------- Render ----------

function renderPriceChart(chartData) {
  const ctx = document.getElementById('backtestChart').getContext('2d');
  if (backtestChart) backtestChart.destroy();

  const candleData = chartData.candles.map(c => ({
    x: new Date(c.timestamp).getTime(),
    o: c.open, h: c.high, l: c.low, c: c.close,
  }));

  const portfolioData = chartData.portfolio_values.map(pv => ({
    x: new Date(pv.timestamp).getTime(),
    y: pv.value,
  }));

  hodLodPlugin._levels = calculateDailyLevels(chartData.candles);
  const tradesByStrategy = groupTradesByStrategy(chartData.trades);
  const strategyStats = calculateStrategyStats(tradesByStrategy);

  const datasets = [
    {
      label: 'BTC/USDT',
      data: candleData,
      yAxisID: 'y',
      color: { up: '#58D68D', down: '#ff5e57', unchanged: '#999' },
      borderColor: { up: '#58D68D', down: '#ff5e57', unchanged: '#999' },
      borderWidth: 1.5,
      barPercentage: 0.7,
      categoryPercentage: 0.8,
      order: 10,
    },
    {
      label: 'Portfolio Value',
      type: 'line',
      data: portfolioData,
      yAxisID: 'y1',
      borderColor: '#FFD700',
      backgroundColor: 'rgba(255, 215, 0, 0.1)',
      borderWidth: 2,
      fill: false,
      tension: 0.1,
      pointRadius: 0,
      pointHoverRadius: 4,
      order: 5,
    },
  ];

  for (const [strategyName, trades] of Object.entries(tradesByStrategy)) {
    const color = getStrategyColor(strategyName);
    const displayName = getStrategyDisplayName(strategyName);

    if (trades.buy.length > 0) {
      datasets.push({
        label: `🟢 ${displayName}`,
        type: 'scatter',
        data: trades.buy,
        yAxisID: 'y',
        pointStyle: 'triangle',
        pointRadius: 14,
        pointRotation: 0,
        backgroundColor: color,
        borderColor: '#ffffff',
        borderWidth: 3,
        pointHoverRadius: 25,
        pointHoverBorderWidth: 4,
        pointHoverBackgroundColor: color,
        pointHoverBorderColor: '#ffffff',
        showLine: false,
        order: 0,
      });
    }

    if (trades.sell.length > 0) {
      datasets.push({
        label: `🔴 ${displayName}`,
        type: 'scatter',
        data: trades.sell,
        yAxisID: 'y',
        pointStyle: 'triangle',
        pointRadius: 14,
        pointRotation: 180,
        backgroundColor: color,
        borderColor: '#ffffff',
        borderWidth: 3,
        pointHoverRadius: 25,
        pointHoverBorderWidth: 4,
        pointHoverBackgroundColor: color,
        pointHoverBorderColor: '#ffffff',
        showLine: false,
        order: 0,
      });
    }
  }

  const timestamps = candleData.map(c => c.x);
  const minTime = Math.min(...timestamps);
  const maxTime = Math.max(...timestamps);

  backtestChart = new Chart(ctx, {
    type: 'candlestick',
    data: { datasets },
    plugins: [hodLodPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 800,
        easing: 'easeOutQuart',
      },
      plugins: {
        tooltip: {
          enabled: true,
          mode: 'point',
          intersect: true,
          position: 'nearest',
          backgroundColor: 'rgba(0, 0, 0, 0.9)',
          titleColor: '#ffffff',
          bodyColor: '#ffffff',
          borderColor: 'rgba(255, 255, 255, 0.2)',
          borderWidth: 1,
          padding: 10,
          displayColors: false,
          caretSize: 6,
          caretPadding: 8,
          cornerRadius: 6,
          titleFont: { size: 12, weight: 'bold' },
          bodyFont: { size: 12 },
          callbacks: {
            title() { return ''; },
            label(context) {
              const label = context.dataset.label || '';
              const raw = context.raw;

              if (label.includes('🟢') || label.includes('🔴')) {
                const lines = [label];
                if (raw.strategy_name) lines.push(`Strategy: ${getStrategyDisplayName(raw.strategy_name)}`);
                lines.push(`Price: $${raw.y.toFixed(2)}`);
                if (raw.confidence) lines.push(`Confidence: ${(raw.confidence * 100).toFixed(0)}%`);
                if (raw.pnl != null) {
                  const sign = raw.pnl >= 0 ? '+' : '';
                  lines.push(`P&L: ${sign}$${raw.pnl.toFixed(2)}`);
                }
                if (raw.reason) lines.push(`Reason: ${raw.reason}`);
                return lines;
              }

              if (label === 'Portfolio Value') {
                return `💰 $${context.parsed.y.toFixed(0)}`;
              }

              if (raw && typeof raw.o !== 'undefined') {
                return [
                  `O: $${raw.o.toFixed(0)}`,
                  `H: $${raw.h.toFixed(0)}`,
                  `L: $${raw.l.toFixed(0)}`,
                  `C: $${raw.c.toFixed(0)}`,
                ];
              }

              return label;
            },
          },
        },
        legend: {
          display: true,
          position: 'top',
          labels: {
            color: '#e1e8ff',
            filter(item) {
              return true;
            },
          },
        },
        zoom: {
          zoom: {
            wheel: { enabled: true, speed: 0.05 },
            pinch: { enabled: true },
            mode: 'x',
          },
          pan: { enabled: true, mode: 'x' },
        },
      },
      interaction: {
        mode: 'nearest',
        axis: 'xy',
        intersect: true,
      },
      scales: {
        x: {
          type: 'time',
          min: minTime,
          max: maxTime,
          time: {
            unit: 'hour',
            displayFormats: { hour: 'MMM dd HH:mm' },
            tooltipFormat: 'MMM dd, yyyy HH:mm',
          },
          ticks: { color: '#e1e8ff', autoSkip: true, maxRotation: 0 },
          grid: { color: 'rgba(255,255,255,0.1)' },
        },
        y: {
          type: 'linear',
          position: 'left',
          beginAtZero: false,
          title: { display: true, text: 'Price (USD)', color: '#e1e8ff' },
          ticks: { color: '#e1e8ff' },
          grid: { color: 'rgba(255,255,255,0.1)' },
        },
        y1: {
          type: 'linear',
          position: 'right',
          beginAtZero: false,
          title: { display: true, text: 'Portfolio Value (USD)', color: '#FFD700' },
          ticks: {
            color: '#FFD700',
            callback(value) { return '$' + value.toFixed(0); },
          },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });

  updateStrategyLegend(Object.keys(tradesByStrategy), strategyStats);
  setupDragPan(backtestChart, 'backtestChart');
}

// ---------- Legend ----------

function updateStrategyLegend(strategies, stats) {
  const container = document.getElementById('strategy-legend');
  const items = document.getElementById('legend-items');

  if (!strategies.length) {
    container.style.display = 'none';
    return;
  }

  container.style.display = 'flex';
  items.innerHTML = strategies.map(name => {
    const color = getStrategyColor(name);
    const display = getStrategyDisplayName(name);
    const s = stats[name] || {};
    const winRate = s.winRate || 0;
    const winColor = winRate >= 50 ? 'var(--accent-green)' : 'var(--accent-red)';
    const avgConf = s.avgConfidence || 0;

    const confBar = avgConf > 0
      ? `<span class="legend-conf-track"><span class="legend-conf-fill" style="width:${avgConf * 100}%;background:${color}"></span></span>`
      : '';

    return `
      <div class="legend-item" style="flex-direction:column;align-items:flex-start;padding:0.5rem;background:rgba(255,255,255,0.05);border-radius:0.375rem;">
        <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;">
          <div class="legend-marker" style="background-color:${color};"></div>
          <strong>${display}</strong>
        </div>
        <div style="font-size:0.75rem;color:var(--text-secondary);margin-left:1.5rem;">
          <span title="Total trades">${s.totalTrades || 0} trades</span>
          ${s.winningTrades !== undefined ? ` · <span style="color:${winColor}" title="Win rate">${winRate.toFixed(0)}% win</span>` : ''}
          ${avgConf > 0 ? ` · <span title="Avg confidence">${(avgConf * 100).toFixed(0)}%</span> ${confBar}` : ''}
        </div>
      </div>`;
  }).join('');
}

// ---------- Drag Pan ----------

function setupDragPan(chart, canvasId) {
  const canvas = document.getElementById(canvasId);
  let isDragging = false;
  let dragStartX = 0;
  let dragStartMin = 0;
  let dragStartMax = 0;

  canvas.addEventListener('mousedown', (e) => {
    isDragging = true;
    dragStartX = e.clientX;
    dragStartMin = chart.scales.x.min;
    dragStartMax = chart.scales.x.max;
    canvas.style.cursor = 'grabbing';
  });

  canvas.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    e.preventDefault();
    const area = chart.chartArea;
    const dx = e.clientX - dragStartX;
    const timePerPx = (dragStartMax - dragStartMin) / (area.right - area.left);
    chart.options.scales.x.min = dragStartMin - dx * timePerPx;
    chart.options.scales.x.max = dragStartMax - dx * timePerPx;
    chart.update('none');
  });

  const stop = () => {
    if (isDragging) {
      isDragging = false;
      canvas.style.cursor = 'grab';
    }
  };
  canvas.addEventListener('mouseup', stop);
  canvas.addEventListener('mouseleave', stop);
}

// ---------- Navigation Exports ----------

export function resetZoomChart() { backtestChart?.resetZoom(); }
export function zoomInChart() { backtestChart?.zoom(1.2); }
export function zoomOutChart() { backtestChart?.zoom(0.8); }

export function panLeftChart() {
  if (!backtestChart) return;
  const { min, max } = backtestChart.scales.x;
  const pan = (max - min) * 0.15;
  backtestChart.zoomScale('x', { min: min - pan, max: max - pan }, 'default');
}

export function panRightChart() {
  if (!backtestChart) return;
  const { min, max } = backtestChart.scales.x;
  const pan = (max - min) * 0.15;
  backtestChart.zoomScale('x', { min: min + pan, max: max + pan }, 'default');
}
