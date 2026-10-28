/**
 * Trades described in plain words, for chart hovers.
 * Shared by the Dashboard chart and the Backtest chart (window.TradeWords).
 *
 * A trade is { side, price, amount, notional, fee, pnl, exit_reason|reason,
 * strategy_name, x (ms) or timestamp }. pairTrades() links each sale to the
 * purchase it closes, so a sale can report the whole trade's result.
 */
(function () {
  const DAY_MS = 864e5;

  function money(v, digits = 2) {
    return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function signedPct(v) {
    return `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}%`;
  }

  function timeOf(t) {
    return t.x ?? new Date(t.timestamp).getTime();
  }

  function shortDate(ms) {
    return new Date(ms).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }

  /** Oldest first. Sets t.$buy on each sale and t.$sold on the purchase it closed. */
  function pairTrades(trades) {
    const sorted = trades.slice().sort((a, b) => timeOf(a) - timeOf(b));
    let open = null;
    for (const t of sorted) {
      if (t.side === 'buy') { open = t; t.$sold = null; }
      else { t.$buy = open; if (open) open.$sold = t; open = null; }
    }
    return sorted;
  }

  function whyLines(t, trendOnly) {
    const reason = t.exit_reason || t.reason;
    const trend = trendOnly || t.strategy_name === 'Trend_Hold';
    if (t.strategy_name === 'Manual' || reason === 'manual') {
      return ['Why: placed by hand (Manual Trading)'];
    }
    if (t.side === 'buy') {
      return trend
        ? ["Why: BTC's trend turned up", '(its daily price rose above its long-term average)']
        : ['Why: the strategy turned bullish', '(it expected the price to rise)'];
    }
    switch (reason) {
      case 'backtest_end':
        return ['Not a real sale: the test ended here,', 'so the BTC is counted at this price'];
      case 'stop_loss':
        return ['Why: the price fell to the stop-loss level', '(a safety exit that limits the loss)'];
      case 'take_profit':
        return ['Why: the price reached the profit target'];
      case 'trailing_stop':
        return ['Why: the price fell back from its recent high', '(the trailing stop closed the trade)'];
      default:
        return trend
          ? ["Why: BTC's trend turned down", '(its daily price fell below its long-term average)']
          : ['Why: the strategy turned bearish', '(it expected the price to fall)'];
    }
  }

  /**
   * Lines for a tooltip.
   * opts.trendOnly: the run used only Trend Hold (its trades are labelled 'Aggregated')
   * opts.nowPrice:  current BTC price, to value a purchase that's still open
   */
  function describe(t, opts = {}) {
    const price = money(t.price ?? t.y, 0);
    const lines = [];

    if (t.side === 'buy') {
      lines.push(`🟢 Bought BTC at ${price}`);
      if (t.notional) {
        const fee = t.fee || 0;
        lines.push(`Spent ${money(t.notional + fee)}${fee > 0 ? ` (including a ${money(fee)} fee)` : ''}`);
      }
      // Still holding: what it's worth now
      if (t.$sold === null && opts.nowPrice && t.amount && t.notional) {
        const cost = t.notional + (t.fee || 0);
        const worth = t.amount * opts.nowPrice;
        lines.push(`Still holding: worth ${money(worth)} now (${signedPct((worth / cost - 1) * 100)})`);
      }
      lines.push(...whyLines(t, opts.trendOnly));
      return lines;
    }

    const ended = (t.exit_reason || t.reason) === 'backtest_end';
    lines.push(ended ? `🏁 End of test — BTC at ${price}` : `🔴 Sold BTC at ${price}`);
    const received = t.notional ? t.notional - (t.fee || 0) : null;
    if (received != null) lines.push(`${ended ? 'Worth' : 'Got back'} ${money(received)} after fees`);

    // Result of the whole trade, after the buying and selling fees
    const b = t.$buy;
    if (b && b.notional && received != null) {
      const cost = b.notional + (b.fee || 0);
      const net = received - cost;
      lines.push(`${net >= 0 ? '✅ Made' : '❌ Lost'} ${money(Math.abs(net))} (${signedPct((net / cost) * 100)}) on this trade`);
      const days = (timeOf(t) - timeOf(b)) / DAY_MS;
      const held = days < 1
        ? `${Math.max(1, Math.round(days * 24))} hour${Math.round(days * 24) === 1 ? '' : 's'}`
        : `${Math.round(days)} day${Math.round(days) === 1 ? '' : 's'}`;
      lines.push(`Held ${held}, bought ${shortDate(timeOf(b))} at ${money(b.price, 0)}`);
    } else if (t.pnl != null) {
      lines.push(`${t.pnl >= 0 ? '✅ Made' : '❌ Lost'} ${money(Math.abs(t.pnl))} on this trade`);
    }
    lines.push(...whyLines(t, opts.trendOnly));
    return lines;
  }

  window.TradeWords = { describe, pairTrades, money, signedPct };
})();
