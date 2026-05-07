# Multi-Strategy System - Quick Reference

## ⚡ Quick Setup

```bash
# 1. Update .env file
cp env.example .env
nano .env

# 2. Enable multi-strategy
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
BOT_MIN_SIGNAL_CONFIDENCE=0.3

# 3. Enable strategies
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0

# 4. Restart bot
./restart.sh
```

## 📊 Strategies at a Glance

| Strategy | Type | Best For | Stop Loss | Take Profit |
|----------|------|----------|-----------|-------------|
| **EMA Crossover** | Trend Following | Trending markets | 2.5% / 2.5x ATR | 4% |
| **RSI + Bollinger Bands** | Mean Reversion | Ranging markets | 2% / 2x ATR | 3% |

## 🔄 Aggregation Modes

| Mode | Description | Best For | Trade Frequency |
|------|-------------|----------|-----------------|
| **weighted_voting** ⭐ | Weighted by confidence | Balanced | Medium |
| **voting** | Simple majority | Equal strategies | Medium |
| **unanimous** | All must agree | High confidence | Low |
| **any** | Any can trigger | Max opportunities | High |
| **best** | Most confident | Dynamic selection | Medium |

⭐ = Recommended

## 🎯 Recommended Presets

### Conservative (Fewer, Better Trades)
```bash
BOT_STRATEGY_AGGREGATION_MODE=unanimous
BOT_MIN_SIGNAL_CONFIDENCE=0.5
```

### Balanced (Recommended)
```bash
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
BOT_MIN_SIGNAL_CONFIDENCE=0.3
BOT_STRATEGY_EMA_WEIGHT=1.2
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

### Aggressive (More Trades)
```bash
BOT_STRATEGY_AGGREGATION_MODE=any
BOT_MIN_SIGNAL_CONFIDENCE=0.25
```

### Trending Market
```bash
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.5
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=0.7
```

### Ranging Market
```bash
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=0.7
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.5
```

## 📈 Monitoring

### Check Strategy Status
```bash
curl -u admin:password http://localhost:8000/api/strategies
```

### View Strategy Performance
```bash
curl -u admin:password http://localhost:8000/api/strategies/stats
```

### View Logs
```bash
tail -f logs/bot.log | grep "Signal="
```

## 🎓 Signal Examples

### Example 1: Both Agree (Weighted Voting)
```
EMA Strategy: BULLISH (confidence: 0.8)
RSI+BB Strategy: BULLISH (confidence: 0.6)
---
Result: BULLISH (aggregated confidence: 0.7)
```

### Example 2: Disagree (Weighted Voting)
```
EMA Strategy: BULLISH (confidence: 0.7)
RSI+BB Strategy: BEARISH (confidence: 0.5)
---
Result: NEUTRAL (no clear majority)
```

### Example 3: One Confident (Any Mode)
```
EMA Strategy: NEUTRAL (confidence: 0.2)
RSI+BB Strategy: BULLISH (confidence: 0.8)
---
Result: BULLISH (from RSI+BB)
```

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| No signals | Lower `BOT_MIN_SIGNAL_CONFIDENCE` to 0.2 |
| Too many signals | Use `unanimous` mode or raise confidence to 0.5 |
| Only one strategy used | Check strategy weights, adjust imbalance |
| Conflicts | Use `best` or `any` mode |

## 📊 Performance Metrics

**Good Indicators:**
- ✅ Win rate >50%
- ✅ Acceptance rate 40-70%
- ✅ Both strategies contributing
- ✅ Avg confidence >0.4

**Warning Signs:**
- ⚠️ Acceptance rate <30%
- ⚠️ Only one strategy used
- ⚠️ Win rate <40%
- ⚠️ Avg confidence <0.3

## 📚 Full Documentation

- **[MULTI_STRATEGY_GUIDE.md](MULTI_STRATEGY_GUIDE.md)** - Complete guide
- **[README.md](README.md)** - Main documentation
- **[QUICKSTART.md](QUICKSTART.md)** - Setup guide

## 💡 Pro Tips

1. **Start conservative** (unanimous mode) then relax
2. **Monitor for 1 week** before going live
3. **Adjust weights** based on market conditions
4. **Backtest first** with `python backtest.py 30`
5. **Check logs daily** for strategy conflicts

---

**Need help?** Check `MULTI_STRATEGY_GUIDE.md` for detailed explanations.
