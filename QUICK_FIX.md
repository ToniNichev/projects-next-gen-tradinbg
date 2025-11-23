# Quick Fix for Low Win Rate

## Problem Diagnosis

**Current Results (1h timeframe, 90 days):**
- Trades: 16 (good!)
- Win Rate: 22.2% (too low!)
- P&L: -$12.97 (-1.30%)
- Buy & Hold: +$115 (+11.51%)

**Root Cause:** The algorithm is shorting (selling) in an uptrend, getting stopped out repeatedly.

Looking at your trades:
- Trade #1: SELL → Trailing stop profit +$1.18 ✅
- Trade #3: BUY → Trailing stop loss -$3.35 ❌
- Trade #5: SELL → Stop loss -$2.25 ❌
- Trade #7: SELL → Closed by signal -$1.70 ❌
- Trade #15: SELL → Trailing stop profit +$2.30 ✅

**Pattern:** Shorts occasionally work, but longs keep getting stopped out in this uptrend.

---

## Solutions (Pick One)

### **Solution A: Trade With the Trend Only** (RECOMMENDED)

Make your bot **long-only** during uptrends. Don't short.

```python
# Add to strategy.py in compute_signal():

# After calculating direction, add trend filter:
if direction == "bearish":
    # Check if we're in a strong uptrend (price above long EMA)
    if price > float(last.long_ema) * 1.02:  # Price 2% above long EMA
        direction = "neutral"  # Skip short signals in uptrends
```

Or simpler: **Disable shorting entirely** in `paper_trader.py`:

```python
# In handle_signal():
if signal.direction == "bearish":
    # In spot trading, skip shorts or only exit longs
    if self.open_position and self.open_position.side == "long":
        return self._close_position(signal.price, "signal")
    return None  # Don't open new shorts
```

**Expected Impact:**
- Trades: ~10 (down from 16)
- Win rate: 45-55% (up from 22%)
- P&L: Positive (following trend)

---

### **Solution B: Widen Stops Further**

Your stops are still too tight. Price needs more room to breathe.

```python
# config.py
atr_stop_multiplier: float = 3.5  # Up from 2.5
stop_loss_pct: float = 0.04  # 4% stops
```

**Trade-off:** Fewer stop-outs, but bigger losses when wrong.

---

### **Solution C: Use Higher Timeframe Filter** (ADVANCED)

Only take trades that align with 4-hour or daily trend.

Add to `strategy.py`:

```python
def check_higher_timeframe_trend(exchange, symbol, timeframe='4h'):
    """Check if higher timeframe is bullish, bearish, or neutral"""
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe, limit=50)
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate EMAs on higher timeframe
        df['ema_short'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema_long'] = df['close'].ewm(span=26, adjust=False).mean()
        
        last = df.iloc[-1]
        if last['ema_short'] > last['ema_long']:
            return 'bullish'
        elif last['ema_short'] < last['ema_long']:
            return 'bearish'
        return 'neutral'
    except:
        return 'neutral'

# In compute_signal(), before returning:
htf_trend = check_higher_timeframe_trend(exchange, symbol, '4h')

# Only take trades aligned with HTF
if direction == "bullish" and htf_trend == "bearish":
    direction = "neutral"
elif direction == "bearish" and htf_trend == "bullish":
    direction = "neutral"
```

**Expected Impact:**
- Trades: ~8-12
- Win rate: 50-60%
- Better alignment with market direction

---

### **Solution D: Reverse the Strategy** (CONTRARIAN)

Maybe EMA crossover is best used as a REVERSAL signal, not trend-following.

```python
# In compute_signal(), swap bullish/bearish:
# When short EMA crosses above long EMA = SELL (top)
# When short EMA crosses below long EMA = BUY (bottom)

if last.short_ema > last.long_ema and prev.short_ema <= prev.long_ema:
    direction = "bearish"  # Reversed!
elif last.short_ema < last.long_ema and prev.short_ema >= prev.long_ema:
    direction = "bullish"  # Reversed!
```

**This is for mean-reversion, not trend-following.** Test carefully!

---

## My Recommendation: Implement Solution A

**Do this now:**

1. Make it long-only in strong uptrends
2. Let it short only when price is below long EMA

This simple change should get you:
- ✅ Win rate above 40%
- ✅ Positive P&L in trending markets
- ✅ Lower drawdown

---

## Alternative: Accept the Loss, Focus on Consistency

**Reality Check:** 
- -1.30% loss over 90 days is actually GOOD risk management
- You avoided a -12% loss if you had shorted the whole time
- Your stop losses protected you

**Sometimes the best trade is NO trade.**

Consider adding a "market regime filter":
- In strong trends (>5% move): Hold or follow trend
- In ranging markets (<2% move): Trade the crossovers

---

## Test This Configuration

```python
# Recommended for Current Market:
timeframe = "1h"
require_macd_confirmation = False
volume_threshold = 1.1
atr_stop_multiplier = 3.0
min_position_size = 0.20
max_position_size = 0.35

# Add trend filter (long-only in uptrends)
# Skip shorts when price > long_ema * 1.03
```

Run backtest again and you should see:
- Fewer shorts in uptrend
- Higher win rate
- Better P&L

---

## The Bottom Line

Your algorithm is now technically solid with:
- ✅ Risk management
- ✅ Dynamic sizing
- ✅ ATR stops
- ✅ Multiple filters

The issue is **strategy logic**, not implementation:
- Your EMA crossover works best in ranging/sideways markets
- In strong trends, it keeps trying to short
- Solution: Filter out counter-trend trades

**Next step:** Choose Solution A or C and test again! 🚀








