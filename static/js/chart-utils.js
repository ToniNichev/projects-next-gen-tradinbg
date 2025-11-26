/**
 * Shared Chart Utilities for Trading Dashboard
 * 
 * Common functionality for candlestick charts used in both
 * the live trading UI and backtest analysis pages.
 */

const ChartUtils = {
  /**
   * Common color scheme for charts
   */
  colors: {
    candleUp: '#58D68D',
    candleDown: '#ff5e57',
    candleUnchanged: '#999',
    signalBullish: '#33ff8a',
    signalBearish: '#ff5e57',
    buyMarker: '#00ff00',
    sellMarker: '#ff4444',
    portfolioLine: '#FFD700',
    textPrimary: '#e1e8ff',
    textSecondary: 'rgba(225, 232, 255, 0.6)',
    gridColor: 'rgba(255,255,255,0.1)',
    borderWhite: '#ffffff',
  },

  /**
   * Get common candlestick dataset configuration
   */
  getCandlestickConfig(label = 'BTC/USDT') {
    return {
      label: label,
      data: [],
      type: 'candlestick',
      color: {
        up: this.colors.candleUp,
        down: this.colors.candleDown,
        unchanged: this.colors.candleUnchanged,
      },
      borderColor: {
        up: this.colors.candleUp,
        down: this.colors.candleDown,
        unchanged: this.colors.candleUnchanged,
      },
      borderWidth: 1.5,
      barPercentage: 0.7,
      categoryPercentage: 0.8,
      order: 3, // Draw first (background)
    };
  },

  /**
   * Get common chart scale configuration
   */
  getScaleConfig(includeSecondaryY = false) {
    const scales = {
      x: {
        type: 'time',
        adapters: {
          date: {
            zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          }
        },
        time: {
          unit: 'hour',
          displayFormats: {
            minute: 'MMM dd HH:mm',
            hour: 'MMM dd HH:mm',
          },
          tooltipFormat: 'MMM dd, yyyy HH:mm:ss',
        },
        ticks: {
          color: this.colors.textPrimary,
          source: 'auto',
          autoSkip: true,
          maxRotation: 0,
        },
        grid: {
          color: this.colors.gridColor,
        },
        offset: true,
      },
      y: {
        beginAtZero: false,
        type: 'linear',
        position: 'left',
        title: {
          display: includeSecondaryY,
          text: 'Price (USD)',
          color: this.colors.textPrimary,
        },
        ticks: {
          color: this.colors.textPrimary,
        },
        grid: {
          color: this.colors.gridColor,
        },
      },
    };

    // Add secondary Y-axis for portfolio value (backtest charts)
    if (includeSecondaryY) {
      scales.y1 = {
        type: 'linear',
        position: 'right',
        beginAtZero: false,
        title: {
          display: true,
          text: 'Portfolio Value (USD)',
          color: this.colors.portfolioLine,
        },
        ticks: {
          color: this.colors.portfolioLine,
          callback: function(value) {
            return '$' + value.toFixed(0);
          },
        },
        grid: {
          drawOnChartArea: false,
        },
      };
    }

    return scales;
  },

  /**
   * Get common tooltip configuration
   */
  getTooltipConfig() {
    return {
      mode: 'index',
      intersect: false,
      backgroundColor: 'rgba(0, 0, 0, 0.9)',
      titleColor: '#ffffff',
      bodyColor: '#ffffff',
      borderColor: '#ffffff',
      borderWidth: 1,
      cornerRadius: 6,
      displayColors: true,
      callbacks: {
        title: function(context) {
          if (context[0]) {
            const date = new Date(context[0].parsed.x);
            return date.toLocaleString();
          }
          return '';
        },
        label: function(context) {
          // Candlestick data (OHLC)
          if (context.raw && typeof context.raw.o !== 'undefined') {
            const data = context.raw;
            return [
              `Open:  $${data.o.toFixed(2)}`,
              `High:  $${data.h.toFixed(2)}`,
              `Low:   $${data.l.toFixed(2)}`,
              `Close: $${data.c.toFixed(2)}`
            ];
          }
          // Signal markers
          if (context.dataset.label === 'Signals') {
            return `Price: $${context.parsed.y.toFixed(2)}`;
          }
          // Portfolio value
          if (context.dataset.label === 'Portfolio Value') {
            return `Portfolio: $${context.parsed.y.toFixed(2)}`;
          }
          // Default formatting
          return `${context.dataset.label}: $${context.parsed.y.toFixed(2)}`;
        }
      }
    };
  },

  /**
   * Get zoom plugin configuration
   */
  getZoomConfig(enablePan = false) {
    return {
      pan: {
        enabled: enablePan,
        mode: 'x',
      },
      zoom: {
        wheel: {
          enabled: true,
          speed: 0.05,
        },
        pinch: {
          enabled: true,
        },
        mode: 'x',
        drag: {
          enabled: false,
        },
      },
      limits: {
        x: {
          minRange: 60 * 1000, // 1 minute minimum
        },
      },
    };
  },

  /**
   * Setup drag-to-pan functionality
   */
  setupDragPan(chart, canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
      console.error(`Canvas ${canvasId} not found`);
      return;
    }

    let isDragging = false;
    let dragStartX = 0;
    let dragStartMin = 0;
    let dragStartMax = 0;

    canvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      dragStartX = e.clientX;
      const xScale = chart.scales.x;
      dragStartMin = xScale.min;
      dragStartMax = xScale.max;
      canvas.style.cursor = 'grabbing';
    });

    canvas.addEventListener('mousemove', (e) => {
      if (!isDragging) return;

      e.preventDefault();
      const xScale = chart.scales.x;
      const chartArea = chart.chartArea;

      const deltaX = e.clientX - dragStartX;
      const chartWidth = chartArea.right - chartArea.left;
      const timeRange = dragStartMax - dragStartMin;
      const timePerPixel = timeRange / chartWidth;
      const timeDelta = deltaX * timePerPixel;

      chart.options.scales.x.min = dragStartMin - timeDelta;
      chart.options.scales.x.max = dragStartMax - timeDelta;
      chart.update('none');
    });

    const stopDragging = () => {
      if (isDragging) {
        isDragging = false;
        canvas.style.cursor = 'grab';
      }
    };

    canvas.addEventListener('mouseup', stopDragging);
    canvas.addEventListener('mouseleave', stopDragging);

    // Add horizontal mouse wheel scrolling support
    canvas.addEventListener('wheel', (e) => {
      // Check if it's a horizontal scroll (shift + wheel or trackpad horizontal)
      if (e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();

        const xScale = chart.scales.x;
        const range = xScale.max - xScale.min;

        // Determine scroll direction and amount
        const deltaX = e.deltaX || (e.shiftKey ? e.deltaY : 0);
        const scrollAmount = (deltaX / 1000) * range; // Adjust sensitivity

        // Apply smooth horizontal scroll
        chart.zoomScale('x', {
          min: xScale.min + scrollAmount,
          max: xScale.max + scrollAmount
        }, 'none');
      }
    }, { passive: false });
  },

  /**
   * Navigation functions for charts
   */
  navigation: {
    resetZoom(chart) {
      chart.options.scales.x.min = undefined;
      chart.options.scales.x.max = undefined;
      chart.update('default');
    },

    zoomIn(chart) {
      chart.zoom(1.2);
    },

    zoomOut(chart) {
      chart.zoom(0.8);
    },

    panLeft(chart, percentage = 0.15) {
      const xScale = chart.scales.x;
      const range = xScale.max - xScale.min;
      const panAmount = range * percentage;

      chart.zoomScale('x', {
        min: xScale.min - panAmount,
        max: xScale.max - panAmount
      }, 'default');
    },

    panRight(chart, percentage = 0.15) {
      const xScale = chart.scales.x;
      const range = xScale.max - xScale.min;
      const panAmount = range * percentage;

      chart.zoomScale('x', {
        min: xScale.min + panAmount,
        max: xScale.max + panAmount
      }, 'default');
    },
  },

  /**
   * Setup keyboard navigation
   */
  setupKeyboardNavigation(chart, allowInInputs = false) {
    let keyRepeatInterval = null;

    document.addEventListener('keydown', (e) => {
      // Skip if typing in input field (unless explicitly allowed)
      if (!allowInInputs && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
        return;
      }

      const handleKey = () => {
        const xScale = chart.scales.x;
        const range = xScale.max - xScale.min;
        const panAmount = range * 0.05; // 5% increments for smooth scrolling

        switch(e.key) {
          case 'ArrowLeft':
            e.preventDefault();
            chart.zoomScale('x', {
              min: xScale.min - panAmount,
              max: xScale.max - panAmount
            }, 'none'); // No animation for smooth continuous scrolling
            break;
          case 'ArrowRight':
            e.preventDefault();
            chart.zoomScale('x', {
              min: xScale.min + panAmount,
              max: xScale.max + panAmount
            }, 'none');
            break;
          case '+':
          case '=':
            e.preventDefault();
            chart.zoom(1.1);
            break;
          case '-':
          case '_':
            e.preventDefault();
            chart.zoom(0.9);
            break;
          case '0':
            e.preventDefault();
            this.navigation.resetZoom(chart);
            break;
        }
      };

      handleKey();
    });

    document.addEventListener('keyup', (e) => {
      if (keyRepeatInterval) {
        clearInterval(keyRepeatInterval);
        keyRepeatInterval = null;
      }
    });
  },

  /**
   * Format candle data from API response
   */
  formatCandleData(candles) {
    return candles.map(candle => ({
      x: new Date(candle.timestamp).getTime(),
      o: candle.open,
      h: candle.high,
      l: candle.low,
      c: candle.close,
    }));
  },

  /**
   * Create buy/sell trade markers for both live and backtest charts
   * Handles different data formats from /api/trades and backtest results
   */
  createTradeMarkers(trades, side = 'buy') {
    const isBuy = side === 'buy';
    return {
      label: isBuy ? 'Buy' : 'Sell',
      type: 'scatter',
      data: trades
        .filter(t => t.side === side)
        .map(t => ({
          x: new Date(t.timestamp).getTime(),
          y: t.price,
          // Support both 'reason' (backtest) and 'exit_reason' (live API)
          reason: t.reason || t.exit_reason,
          exit_reason: t.exit_reason || t.reason,
          pnl: t.pnl,
          side: t.side,
          amount: t.amount
        })),
      yAxisID: 'y',
      pointStyle: 'triangle',
      pointRadius: 10,
      pointRotation: isBuy ? 0 : 180,
      backgroundColor: isBuy ? this.colors.buyMarker : this.colors.sellMarker,
      borderColor: this.colors.borderWhite,
      borderWidth: 2,
      pointHoverRadius: 16,
      pointHoverBorderWidth: 4,
      shadowOffsetX: 1,
      shadowOffsetY: 1,
      shadowBlur: 4,
      shadowColor: 'rgba(0, 0, 0, 0.6)',
      hoverBorderColor: this.colors.borderWhite,
      hoverBorderWidth: 3,
      showLine: false,
      order: 0, // Draw last (on top/in front of everything)
    };
  },

  /**
   * Create portfolio value line for backtest charts
   */
  createPortfolioLine(portfolioValues) {
    return {
      label: 'Portfolio Value',
      type: 'line',
      data: portfolioValues.map(pv => ({
        x: new Date(pv.timestamp).getTime(),
        y: pv.value,
      })),
      yAxisID: 'y1',
      borderColor: this.colors.portfolioLine,
      backgroundColor: 'rgba(255, 215, 0, 0.1)',
      borderWidth: 2,
      fill: false,
      tension: 0.1,
      pointRadius: 0,
      pointHoverRadius: 4,
      order: 2, // Draw after candlesticks but before markers
    };
  },

  /**
   * Update time unit based on timeframe
   */
  updateTimeUnit(chart, timeframe) {
    const timeUnitMap = {
      '1m': 'minute',
      '5m': 'minute',
      '15m': 'minute',
      '30m': 'minute',
      '1h': 'hour',
      '4h': 'hour',
      '1d': 'day',
      '1w': 'day'
    };
    chart.options.scales.x.time.unit = timeUnitMap[timeframe] || 'hour';
  },

  /**
   * Common tooltip formatter for trade markers
   * Handles both buy and sell trades with P&L, amount, and exit reason
   */
  formatTradeTooltip(context) {
    const trade = context.raw;
    const side = context.dataset.label;
    let label = `${side} @ $${trade.y.toFixed(2)}`;
    
    // Add exit reason if available
    if (trade.exit_reason || trade.reason) {
      const reasonText = (trade.exit_reason || trade.reason).replace('_', ' ').toUpperCase();
      label += ` (${reasonText})`;
    }
    
    return label;
  },

  /**
   * Common tooltip afterLabel for trade markers (shows amount and P&L)
   */
  formatTradeTooltipDetails(context) {
    const trade = context.raw;
    const lines = [];
    
    // Add amount
    if (trade.amount !== null && trade.amount !== undefined) {
      lines.push(`Amount: ${trade.amount.toFixed(6)} BTC`);
    }
    
    // Add P&L for sell trades (or any trade with pnl)
    if (trade.pnl !== null && trade.pnl !== undefined && trade.pnl !== 'None') {
      const pnl = parseFloat(trade.pnl);
      if (!isNaN(pnl)) {
        const pnlText = pnl >= 0 ? `+$${pnl.toFixed(2)}` : `$${pnl.toFixed(2)}`;
        lines.push(`P&L: ${pnlText}`);
      }
    }
    
    return lines;
  },
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ChartUtils;
}

