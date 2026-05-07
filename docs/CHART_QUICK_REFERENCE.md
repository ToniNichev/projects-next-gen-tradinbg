# Backtest Chart - Quick Visual Reference

## 🎯 Chart Elements at a Glance

### 📊 Price Action

```
         ═══ HOD (Red dashed) ═══  ← High of Day (Resistance)
    
    ▲ Green candle (price up)
    ▼ Red candle (price down)
    
         ═══ LOD (Teal dashed) ═══  ← Low of Day (Support)
```

---

## 🔺 Trade Markers

### Size Indicates Confidence:

```
🔺 Small (8-11px)     = Low confidence (30-50%)
▲  Medium (11-14px)   = Medium confidence (50-70%)  
🔼 Large (14-16px)    = High confidence (70-100%)

⚪️ Thick white border = Very high confidence (>70%)
```

### Orientation:
- **Triangle pointing UP (0°)** = BUY order
- **Triangle pointing DOWN (180°)** = SELL order

### Colors by Strategy:
- 🔵 **Cyan** (#00D9FF) = EMA Crossover
- 🔴 **Pink** (#FF6B9D) = RSI + Bollinger Bands
- 🟡 **Gold** (#FFD700) = MACD + Volume
- 🟣 **Purple** (#9D4EDD) = LLM Pattern Analysis
- ⚪️ **White** (#FFFFFF) = Multi-Strategy Aggregated

---

## 📈 Legend Components

### Strategy Cards Show:
```
┌─────────────────────────────────┐
│ 🔵 EMA Crossover                │  ← Strategy name + color
│    24 trades                     │  ← Total buy + sell
│    · 62% win                     │  ← Win rate (green if >50%)
│    · Avg conf: 75% ████████░░   │  ← Confidence with bar
└─────────────────────────────────┘
```

### Support/Resistance Legend:
```
━━━ HOD (High of Day)    Red dashed line
━━━ LOD (Low of Day)     Teal dashed line
💡 Marker size = Signal confidence
```

---

## 🖱️ Interactive Features

### Hover Over Elements:

**Candlestick:**
```
📅 Feb 27, 2026 14:30:00
Open:  $67,477.30
High:  $67,890.45
Low:   $67,123.67
Close: $67,555.22
```

**Trade Marker (Buy):**
```
🟢 EMA Crossover BUY
$67,477.30 × 0.0022 BTC
🔥 85% confidence
```

**Trade Marker (Sell):**
```
🔴 EMA Crossover SELL
$67,890.00 × 0.0022 BTC
📈 +$1.38 profit
Exit: take profit
✅ 75% confidence
```

**HOD Line:**
```
📈 High: $68,500.00 (Feb 27)
```

**LOD Line:**
```
📉 Low: $66,200.00 (Feb 27)
```

---

## 🎨 Color Coding Reference

### Chart Elements:
| Element | Color | Meaning |
|---------|-------|---------|
| Green Candle | #58D68D | Price increased |
| Red Candle | #ff5e57 | Price decreased |
| Gold Line | #FFD700 | Portfolio value |
| Red Dashed | rgba(255,99,132,0.6) | HOD resistance |
| Teal Dashed | rgba(75,192,192,0.6) | LOD support |

### Strategy Colors:
| Strategy | Color | Hex |
|----------|-------|-----|
| EMA Crossover | Cyan | #00D9FF |
| RSI + BB | Pink | #FF6B9D |
| MACD + Volume | Gold | #FFD700 |
| LLM Pattern | Purple | #9D4EDD |
| Multi-Strategy | White | #FFFFFF |

### Win Rate Colors:
| Win Rate | Color | Status |
|----------|-------|--------|
| ≥50% | Green | Profitable |
| <50% | Red | Unprofitable |

---

## 🔍 Reading the Chart

### 1. Identify Support & Resistance
- Look for **red dashed lines (HOD)** above price
- Look for **teal dashed lines (LOD)** below price
- Check if trades happen near these levels

### 2. Assess Signal Quality
- **Larger markers** = Higher confidence signals
- **Thick white borders** = Premium signals (>70%)
- Check if winning trades have higher confidence

### 3. Compare Strategies
- Look at **legend cards** for win rates
- Identify which **color** (strategy) performs best
- Check **confidence bars** for signal consistency

### 4. Spot Patterns
- Breakouts: Trades above HOD or below LOD
- Reversals: Trades near support/resistance
- Momentum: Series of high-confidence trades

---

## ⚡ Quick Actions

### Navigation:
- **Mouse wheel** = Zoom in/out on X-axis
- **Click + Drag** = Pan left/right
- **Left/Right buttons** = Jump by 15% of visible range
- **Reset button** = Zoom to fit all data

### Legend Interactions:
- **Click strategy name** = Toggle visibility
- **Hover legend card** = Highlight and scale
- **Hover marker size hint** = See explanation

---

## 📊 Performance Indicators

### Win Rate Guide:
```
🔥 >70%  = Excellent strategy
✅ 50-70% = Good strategy
⚠️ 40-50% = Fair strategy (needs tuning)
❌ <40%   = Poor strategy (reconsider)
```

### Confidence Guide:
```
🔥 80-100% = Excellent signal quality
✅ 60-79%  = Good signal quality
⚠️ 40-59%  = Fair signal quality
⚡ 0-39%   = Low signal quality
```

### Trade Count Guide:
```
📈 >50 trades  = Statistically significant
📊 20-50 trades = Moderate confidence
📉 <20 trades  = Small sample (be cautious)
```

---

## 🎓 Trading Analysis Examples

### Example 1: Breakout Trade
```
Price action:
  ═══ HOD $68,500 ═══
       ▲ (Large marker, 85% conf)  ← BUY above resistance
      📈 Price continues up
       ▼ (Medium marker, 65% conf) ← SELL at profit

Analysis: High-confidence breakout trade above HOD. Good!
```

### Example 2: Failed Support Test
```
Price action:
      📉 Price dropping
  ═══ LOD $66,200 ═══
       ▲ (Small marker, 40% conf)  ← BUY at support
      📉 Price breaks below LOD
       ▼ (Stop loss triggered)      ← SELL at loss

Analysis: Low-confidence buy at support, failed. Avoid low-conf signals.
```

### Example 3: Range Trading
```
Price action:
  ═══ HOD $68,500 ═══
       ▼ (Sell near resistance)  ← Good timing
      📉 Price pulls back
  ═══ LOD $66,200 ═══
       ▲ (Buy near support)      ← Good timing
      📈 Price bounces up

Analysis: Range-bound trading respecting HOD/LOD. Effective!
```

---

## 💡 Pro Tips

### 1. Filter Noise
- Focus on **large markers** (high confidence) first
- Ignore **very small markers** (<10px) during initial analysis
- Check if strategy has **>50% win rate** before following

### 2. Confirm Breakouts
- Look for **large marker above HOD** = Strong breakout signal
- Multiple small markers near resistance = Weak conviction
- High confidence + volume spike = Best setup

### 3. Use Context
- **Morning HOD break** often leads to trending day
- **Late-day LOD break** might signal reversal
- **Multiple HOD tests** create strong resistance

### 4. Compare Strategies
- Which **color** appears most in winning trades?
- Does one strategy have **consistently higher confidence**?
- Are **multi-strategy signals** (white) better performers?

---

## 🔧 Troubleshooting

### Issue: No HOD/LOD lines visible
- **Cause**: Single-day backtest
- **Fix**: Run backtest with ≥2 days of data

### Issue: All markers same size
- **Cause**: No confidence data in trades
- **Fix**: Ensure strategies populate `confidence` field (0-1)

### Issue: Legend shows no statistics
- **Cause**: No completed trade pairs (buy→sell)
- **Fix**: Ensure backtest ran long enough to close positions

### Issue: Chart looks cluttered
- **Cause**: Many strategies + many trades
- **Fix**: Click legend items to hide specific strategies

---

## 📱 Mobile/Tablet View

Chart is responsive but best viewed on desktop for detailed analysis.

**Recommended minimum screen width:** 1024px

**Touch gestures:**
- Pinch = Zoom
- Swipe = Pan
- Tap marker = See tooltip
- Tap legend = Toggle visibility

---

## 🎯 Quick Decision Framework

When analyzing a backtest chart:

1. **Check overall profitability** (green/red in legend)
2. **Identify best strategy** (highest win rate)
3. **Assess signal quality** (avg confidence bars)
4. **Look for patterns** (HOD/LOD interactions)
5. **Verify sample size** (trade count)
6. **Spot outliers** (very small/large markers)
7. **Compare to portfolio line** (drawdowns vs trades)

**Good backtest indicators:**
- ✅ Win rate >55%
- ✅ Average confidence >60%
- ✅ Trades respect HOD/LOD
- ✅ Large markers correlate with wins
- ✅ Portfolio line trending up

**Warning signs:**
- ⚠️ Win rate <45%
- ⚠️ Average confidence <40%
- ⚠️ Random entries (no HOD/LOD respect)
- ⚠️ Small markers have better results
- ⚠️ Portfolio line trending down

---

## 📚 Related Documentation

- `BACKTEST_CHART_IMPROVEMENTS.md` - Detailed technical documentation
- `BACKTEST_UI_SIMPLIFICATION.md` - UI design principles
- `BACKTEST_MULTI_STRATEGY_GUIDE.md` - Strategy system overview

---

**Last Updated:** March 1, 2026  
**Version:** 2.0 (with HOD/LOD and confidence features)
