# 🎨 Strategy Preset Catalog

Complete guide to all 12 built-in strategy presets with detailed comparisons.

---

## 📊 Quick Comparison Table

| Preset | Category | Risk Level | Trades/Day | Stop Loss | Take Profit | Best For |
|--------|----------|------------|------------|-----------|-------------|----------|
| 🟢 Conservative | Conservative | ⭐ Low | ~3 | 1.5% | 3% | New traders, capital preservation |
| 🌙 Night Mode | Conservative | ⭐ Ultra Low | ~2 | 1.2% | 2.5% | Overnight, unmonitored |
| 🔵 Balanced | Balanced | ⭐⭐ Medium | ~5 | 2.5% | 4% | Default, most traders |
| 🔴 Aggressive | Aggressive | ⭐⭐⭐⭐ High | ~10 | 4% | 8% | Experienced, high volatility |
| 🟠 Scalping 5m | Scalping | ⭐⭐⭐ Med-High | ~15 | 0.8% | 1.5% | Day trading, constant monitoring |
| ⏰ Day Trading 1h | Day Trading | ⭐⭐ Medium | ~8 | 2% | 5% | Check 2-3x daily |
| 🟣 Swing 4h | Swing | ⭐⭐ Medium | ~3 | 5% | 12% | Part-time, bigger moves |
| 📈 Trend Following | Specialized | ⭐⭐⭐ Medium | ~5 | 3% | 8% | Strong directional markets |
| 📉 Mean Reversion | Specialized | ⭐⭐ Low-Med | ~6 | 1.8% | 3.5% | Ranging/sideways markets |
| 💥 Breakout Hunter | Specialized | ⭐⭐⭐ Medium-High | ~6 | 3.5% | 9% | Momentum/volume spikes |
| 🌊 High Volatility | Market Condition | ⭐⭐⭐ Medium | ~4 | 4.5% | 10% | Wild market swings |
| 😌 Low Volatility | Market Condition | ⭐⭐ Low | ~8 | 1.5% | 3% | Stable, calm markets |
| 🚀 Crypto Bull | Market Condition | ⭐⭐⭐⭐ High | ~6 | 2.8% | 15% | Strong uptrends |

---

## 📖 Detailed Preset Descriptions

### 🟢 Conservative (Low Risk)
**Category:** Conservative  
**Philosophy:** Capital preservation over aggressive gains

**Key Settings:**
- Stop Loss: 1.5% | Take Profit: 3%
- Position Size: 15% (10-20% range)
- Aggregation: **Unanimous** - All strategies must agree
- Confidence: 50% minimum
- Volume Filter: Yes (1.3x average)
- Max Trades: 3 per day

**When to Use:**
- ✅ You're new to the bot
- ✅ Testing in live markets for first time
- ✅ During uncertain/choppy market conditions
- ✅ Protecting capital after recent losses
- ✅ You have low risk tolerance

**Strengths:** Very safe, fewer false signals, protects capital  
**Weaknesses:** Misses some opportunities, lower profits in trending markets

---

### 🌙 Night Mode (Unmonitored)
**Category:** Conservative  
**Philosophy:** Ultra-safe for when you can't watch

**Key Settings:**
- Stop Loss: 1.2% | Take Profit: 2.5%
- Position Size: 12% (8-15% range)
- Aggregation: **Unanimous** - Maximum safety
- Confidence: 60% minimum (very high!)
- Volume Filter: Yes (1.4x average - strict)
- Max Trades: 2 per day

**When to Use:**
- ✅ Going to sleep / overnight trading
- ✅ Away from computer for extended periods
- ✅ Can't monitor the bot
- ✅ Want minimal risk exposure
- ✅ Testing live trading first time

**Strengths:** Extremely conservative, tight risk control  
**Weaknesses:** Very few trades, may miss opportunities

---

### 🔵 Balanced (Default)
**Category:** Balanced  
**Philosophy:** Best all-around configuration

**Key Settings:**
- Stop Loss: 2.5% | Take Profit: 4%
- Position Size: 25% (15-35% range)
- Aggregation: **Weighted Voting** - Balanced approach
- Confidence: 30% minimum
- Volume Filter: Yes (1.1x average)
- Max Trades: 5 per day

**When to Use:**
- ✅ Starting out / learning the bot
- ✅ Normal market conditions
- ✅ Unsure which preset to choose
- ✅ Want a solid baseline
- ✅ General-purpose trading

**Strengths:** Well-tested, good risk/reward, versatile  
**Weaknesses:** Not optimized for specific conditions

---

### 🔴 Aggressive (High Risk)
**Category:** Aggressive  
**Philosophy:** Maximum trades, maximum risk, maximum potential

**Key Settings:**
- Stop Loss: 4% | Take Profit: 8%
- Position Size: 40% (25-50% range)
- Aggregation: **Any** - One strategy can trigger
- Confidence: 20% minimum (very low!)
- Volume Filter: No
- Max Trades: 10 per day

**When to Use:**
- ✅ You're experienced with the bot
- ✅ Comfortable with volatility
- ✅ Strong trending market
- ✅ Want to maximize opportunities
- ✅ Can handle drawdowns

**Strengths:** Maximum signal generation, catches all moves  
**Weaknesses:** High risk, more false signals, larger drawdowns

---

### 🟠 Scalping (5m timeframe)
**Category:** Scalping  
**Philosophy:** Quick in, quick out, high frequency

**Key Settings:**
- Timeframe: **5 minutes** ⚠️ (requires restart)
- Stop Loss: 0.8% | Take Profit: 1.5%
- Position Size: 20% (15-30% range)
- Aggregation: **Best** - Most confident strategy
- Confidence: 40% minimum
- Volume Filter: Yes (1.5x - important for scalping)
- Max Trades: 15 per day

**When to Use:**
- ✅ You can monitor constantly
- ✅ Fast-paced trading style
- ✅ Volatile intraday moves
- ✅ Want frequent small profits
- ✅ Have tight risk management

**Strengths:** Many opportunities, quick profits  
**Weaknesses:** Requires constant monitoring, more stressful

---

### ⏰ Day Trading (1h timeframe)
**Category:** Day Trading  
**Philosophy:** Best of both worlds - active but manageable

**Key Settings:**
- Timeframe: **1 hour** ⚠️ (requires restart)
- Stop Loss: 2% | Take Profit: 5%
- Position Size: 30% (20-40% range)
- Aggregation: **Weighted Voting**
- Confidence: 35% minimum
- Volume Filter: Yes (1.2x average)
- Max Trades: 8 per day

**When to Use:**
- ✅ Check bot 2-3 times per day
- ✅ Want active trading without constant monitoring
- ✅ Prefer medium-term holds (few hours)
- ✅ Balance between scalping and swing
- ✅ Part-time day trader

**Strengths:** Good balance, manageable monitoring  
**Weaknesses:** Not as fast as scalping, not as hands-off as swing

---

### 🟣 Swing Trading (4h timeframe)
**Category:** Swing  
**Philosophy:** Catch larger moves, less frequent

**Key Settings:**
- Timeframe: **4 hours** ⚠️ (requires restart)
- Stop Loss: 5% | Take Profit: 12%
- Position Size: 35% (20-45% range)
- Aggregation: **Weighted Voting**
- Confidence: 35% minimum
- Volume Filter: Yes (1.2x average)
- Max Trades: 3 per day
- EMA: Slower (21/55 instead of 12/26)

**When to Use:**
- ✅ Can't monitor frequently
- ✅ Want to hold positions overnight
- ✅ Prefer larger moves
- ✅ Check once or twice daily
- ✅ More patient trading style

**Strengths:** Low maintenance, catches big moves  
**Weaknesses:** Fewer opportunities, wider stops

---

### 📈 Trend Following (EMA Focus)
**Category:** Specialized  
**Philosophy:** Ride strong trends with EMA strategy

**Key Settings:**
- Stop Loss: 3% | Take Profit: 8%
- Position Size: 30% (20-40% range)
- Aggregation: **Weighted Voting**
- **Strategy Weights:** EMA=2.0x, RSI+BB=0.5x, MACD=1.0x
- Confidence: 40% minimum
- EMA: Longer periods (15/35) for stronger trends
- Min Trend Strength: Higher threshold (0.0001)

**When to Use:**
- ✅ Clear trending market (up or down)
- ✅ Strong directional moves
- ✅ Breaking out of consolidation
- ✅ Want to ride trends longer
- ✅ Avoid choppy/sideways action

**Strengths:** Excellent in trending markets, bigger wins  
**Weaknesses:** Poor in ranging markets, late entries/exits

---

### 📉 Mean Reversion (RSI+BB Focus)
**Category:** Specialized  
**Philosophy:** Buy low, sell high in ranges

**Key Settings:**
- Stop Loss: 1.8% | Take Profit: 3.5%
- Position Size: 25% (15-35% range)
- Aggregation: **Weighted Voting**
- **Strategy Weights:** EMA=0.5x, RSI+BB=2.0x, MACD=0.8x
- Confidence: 40% minimum
- No volume filter (less important for mean reversion)
- RSI: More extreme levels (25/75)

**When to Use:**
- ✅ Sideways/ranging market
- ✅ No clear trend
- ✅ Price oscillating between support/resistance
- ✅ High volatility but no direction
- ✅ Counter-trend trading

**Strengths:** Great in ranges, consistent small wins  
**Weaknesses:** Fights trends, losses when breakout occurs

---

### 💥 Breakout Hunter (MACD+Volume Focus)
**Category:** Specialized  
**Philosophy:** Catch explosive moves with volume

**Key Settings:**
- Stop Loss: 3.5% | Take Profit: 9%
- Position Size: 35% (25-45% range)
- Aggregation: **Weighted Voting**
- **Strategy Weights:** EMA=0.8x, RSI+BB=0.5x, MACD=2.0x
- Volume Filter: Yes (1.5x - critical!)
- MACD: Faster (10/22/8)
- Confidence: 35% minimum

**When to Use:**
- ✅ Expecting big moves/news
- ✅ Consolidation about to break
- ✅ Volume surging
- ✅ Want to catch momentum early
- ✅ Breakout trading style

**Strengths:** Catches big explosive moves, volume-confirmed  
**Weaknesses:** False breakouts, whipsaws in ranging markets

---

### 🌊 High Volatility Market
**Category:** Market Condition  
**Philosophy:** Wider stops for wild swings

**Key Settings:**
- Stop Loss: 4.5% | Take Profit: 10%
- Position Size: 20% (12-28% range) - smaller due to risk
- ATR Multiplier: **3.5x** (very wide)
- Confidence: 45% minimum (stricter)
- Volume Filter: Yes (1.3x)
- Max Trades: 4 per day

**When to Use:**
- ✅ Market is extremely volatile
- ✅ Large intraday swings
- ✅ News events / uncertainty
- ✅ Normal stops getting hit too easily
- ✅ Crypto flash crashes/pumps

**Strengths:** Prevents premature stop-outs, handles swings  
**Weaknesses:** Larger losses when wrong, less capital efficiency

---

### 😌 Low Volatility Market
**Category:** Market Condition  
**Philosophy:** Tight stops for stable conditions

**Key Settings:**
- Stop Loss: 1.5% | Take Profit: 3%
- Position Size: 35% (25-45% range) - larger, lower risk
- ATR Multiplier: **1.8x** (tighter)
- Confidence: 25% minimum (relaxed)
- No volume filter
- Max Trades: 8 per day

**When to Use:**
- ✅ Market is calm/stable
- ✅ Low daily ranges
- ✅ Consolidation periods
- ✅ After big moves settle
- ✅ Boring market conditions

**Strengths:** Capital efficient, more opportunities  
**Weaknesses:** Stops too tight if volatility returns suddenly

---

### 🚀 Crypto Bull Market
**Category:** Market Condition  
**Philosophy:** Ride the bull, let profits run

**Key Settings:**
- Stop Loss: 2.8% | Take Profit: **15%** (huge target!)
- Position Size: 40% (30-50% range) - aggressive
- Trailing Stop: 3.5% (wide to let profits run)
- **Strategy Weights:** EMA=1.5x (trend bias), RSI+BB=0.7x, MACD=1.3x
- Confidence: 30% minimum
- EMA: Faster (9/21) to catch uptrends quickly

**When to Use:**
- ✅ Clear bull market / strong uptrend
- ✅ Bitcoin pumping
- ✅ Market euphoria / FOMO
- ✅ Want to maximize bull run profits
- ✅ Ride trends as long as possible

**Strengths:** Massive profits in bull runs, trend-following  
**Weaknesses:** Large drawdown when trend reverses, not for bears

---

## 🎯 How to Choose the Right Preset

### By Trading Style:
- **Hands-off:** Night Mode, Swing Trading
- **Part-time:** Day Trading 1h, Balanced
- **Active:** Scalping 5m, Day Trading
- **Aggressive:** Aggressive, Crypto Bull, Breakout Hunter

### By Market Condition:
- **Trending Up:** Trend Following, Crypto Bull, Breakout Hunter
- **Trending Down:** Conservative, Night Mode
- **Ranging/Sideways:** Mean Reversion, Balanced
- **Volatile:** High Volatility, Conservative
- **Calm:** Low Volatility, Aggressive

### By Experience Level:
- **Beginner:** Conservative → Balanced → Day Trading
- **Intermediate:** Balanced → Trend Following → Breakout Hunter
- **Advanced:** Aggressive → Specialized presets → Custom

### By Risk Tolerance:
- **Very Low:** Night Mode, Conservative
- **Low:** Conservative, Mean Reversion, Low Volatility
- **Medium:** Balanced, Day Trading, Trend Following
- **High:** Aggressive, Breakout Hunter, High Volatility
- **Very High:** Crypto Bull, Aggressive

---

## 💡 Pro Preset Strategies

### The Rotation Strategy
Rotate presets based on time/conditions:
```
Monday-Friday 9am-5pm: Day Trading 1h
Evenings: Balanced
Overnight: Night Mode
Weekends: Swing Trading 4h
```

### The Market Condition Strategy
Switch based on volatility:
```
VIX/ATR Low: Low Volatility preset
VIX/ATR Normal: Balanced
VIX/ATR High: High Volatility preset
```

### The Specialized Stack
Use specialized presets for market phases:
```
Consolidation: Mean Reversion
Breakout: Breakout Hunter
Trending: Trend Following
Uncertain: Conservative
```

### The Bull/Bear Adapter
```
Bull Market: Crypto Bull → Trend Following
Bear Market: Conservative → Night Mode
Sideways: Mean Reversion → Balanced
```

---

## 📊 Preset Performance Hints

### Expected Characteristics:

**High Win Rate (>60%):**
- Conservative, Night Mode, Mean Reversion

**Moderate Win Rate (45-55%):**
- Balanced, Day Trading, Trend Following

**Lower Win Rate (<45%) but Big Winners:**
- Aggressive, Breakout Hunter, Crypto Bull

**Most Trades:**
- Scalping 5m, Aggressive, Low Volatility

**Fewest Trades:**
- Night Mode, Conservative, Swing 4h

**Best Risk/Reward:**
- Crypto Bull, Breakout Hunter, Trend Following

**Most Consistent:**
- Balanced, Day Trading, Conservative

---

## 🔧 Customization Tips

### Starting from a Preset:
1. Load preset closest to your style
2. Backtest it first
3. Adjust 1-2 parameters
4. Backtest again
5. Save as custom preset

### Common Adjustments:
- **More trades:** Lower min_confidence
- **Safer:** Increase stop_loss_pct slightly
- **Bigger wins:** Increase take_profit_pct
- **Less frequent:** Increase min_confidence

---

## 🎉 Summary

You now have **12 comprehensive presets** covering:
- ✅ 3 Risk Levels (Conservative, Balanced, Aggressive)
- ✅ 4 Timeframes (5m, 1h, 4h, default)
- ✅ 3 Specialized Strategies (Trend, Mean Reversion, Breakout)
- ✅ 3 Market Conditions (High Vol, Low Vol, Bull Market)
- ✅ 1 Safety Mode (Night Mode)

**Plus unlimited custom presets you can create!**

---

*Happy Trading! 📈*
