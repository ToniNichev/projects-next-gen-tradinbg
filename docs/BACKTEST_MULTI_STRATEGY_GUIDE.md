# Multi-Strategy Backtesting Guide

## 🎯 Overview

The backtest runner now supports **full multi-strategy backtesting**! You can test:
- ✅ Both strategies together
- ✅ Individual strategies alone
- ✅ Different aggregation modes
- ✅ Various configuration combinations

Results will match your live trading setup exactly.

---

## 🚀 Quick Start

### **Test Current Configuration**

```bash
# Run 30-day backtest with your current .env settings
python backtest.py 30
```

This will automatically use:
- ✅ Your enabled strategies (from `.env`)
- ✅ Your aggregation mode
- ✅ Your confidence threshold
- ✅ All your strategy weights

---

## 📊 Backtest Scenarios

### **Scenario 1: Test Both Strategies (Default)**

**Configuration (`.env`):**
```bash
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_RSI_BB_ENABLED=true
```

**Run:**
```bash
python backtest.py 60
```

**Output Example:**
```
================================================================================
MULTI-STRATEGY BACKTEST MODE
================================================================================
✓ Enabled: EMA_Crossover (weight: 1.0)
✓ Enabled: RSI_BB_MeanReversion (weight: 1.0)
Aggregation mode: weighted_voting
Min confidence: 30.0%
================================================================================

... backtest runs ...

================================================================================
BACKTEST RESULTS - MULTI-STRATEGY WITH RISK MANAGEMENT
================================================================================
Period: 60 days | Candles processed: 1440
Strategies: EMA_Crossover, RSI_BB_MeanReversion
Aggregation: weighted_voting
--------------------------------------------------------------------------------
PERFORMANCE METRICS
--------------------------------------------------------------------------------
Total trades: 45
Winning trades: 28
Losing trades: 17
Win rate: 62.2%
Average P&L per trade: $12.50
--------------------------------------------------------------------------------
STRATEGY PERFORMANCE
--------------------------------------------------------------------------------
Strategy: EMA_Crossover
  Signals Generated: 80
  Signals Used: 30
  Avg Confidence: 65.00%
  Acceptance Rate: 37.5%

Strategy: RSI_BB_MeanReversion
  Signals Generated: 70
  Signals Used: 15
  Avg Confidence: 58.00%
  Acceptance Rate: 21.4%
--------------------------------------------------------------------------------
```

---

### **Scenario 2: Test EMA Strategy Alone**

**Configuration (`.env`):**
```bash
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_RSI_BB_ENABLED=false   # ← Disabled
```

**Run:**
```bash
python backtest.py 60
```

**Result:** Only EMA signals will be used (trend-following only)

---

### **Scenario 3: Test RSI+BB Strategy Alone**

**Configuration (`.env`):**
```bash
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_EMA_ENABLED=false   # ← Disabled
BOT_STRATEGY_RSI_BB_ENABLED=true
```

**Run:**
```bash
python backtest.py 60
```

**Result:** Only RSI+BB signals will be used (mean reversion only)

---

### **Scenario 4: Compare Aggregation Modes**

Test all 5 aggregation modes to find the best one:

#### **A. Weighted Voting (Balanced)**
```bash
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
python backtest.py 60
```

#### **B. Unanimous (Conservative)**
```bash
BOT_STRATEGY_AGGREGATION_MODE=unanimous
python backtest.py 60
```

#### **C. Any (Aggressive)**
```bash
BOT_STRATEGY_AGGREGATION_MODE=any
python backtest.py 60
```

#### **D. Best (Most Confident)**
```bash
BOT_STRATEGY_AGGREGATION_MODE=best
python backtest.py 60
```

#### **E. Simple Voting (Democratic)**
```bash
BOT_STRATEGY_AGGREGATION_MODE=voting
python backtest.py 60
```

**Compare results and pick the winner!**

---

### **Scenario 5: Test Different Weights**

See if favoring one strategy improves results:

#### **Favor Trend-Following:**
```bash
BOT_STRATEGY_EMA_WEIGHT=1.5
BOT_STRATEGY_RSI_BB_WEIGHT=0.8
python backtest.py 60
```

#### **Favor Mean Reversion:**
```bash
BOT_STRATEGY_EMA_WEIGHT=0.8
BOT_STRATEGY_RSI_BB_WEIGHT=1.5
python backtest.py 60
```

#### **Equal Weights:**
```bash
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
python backtest.py 60
```

---

### **Scenario 6: Test Confidence Thresholds**

Find the optimal confidence level:

#### **Low (More Trades):**
```bash
BOT_MIN_SIGNAL_CONFIDENCE=0.2
python backtest.py 60
```

#### **Medium (Balanced):**
```bash
BOT_MIN_SIGNAL_CONFIDENCE=0.3
python backtest.py 60
```

#### **High (Fewer, Better Trades):**
```bash
BOT_MIN_SIGNAL_CONFIDENCE=0.5
python backtest.py 60
```

---

## 📈 Comparison Testing

### **A/B Test: Single vs Multi-Strategy**

#### **Test 1: EMA Only (Legacy)**
```bash
# .env
BOT_USE_MULTI_STRATEGY=false

# Run
python backtest.py 60 > results_ema_only.txt
```

#### **Test 2: Multi-Strategy**
```bash
# .env
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_RSI_BB_ENABLED=true

# Run
python backtest.py 60 > results_multi_strategy.txt
```

#### **Compare:**
```bash
# View side by side
diff results_ema_only.txt results_multi_strategy.txt
```

**Look for:**
- Higher win rate?
- Better P&L?
- More consistent returns?
- Strategy acceptance rates?

---

## 🎓 Understanding Results

### **Key Metrics**

#### **Strategy Performance Section:**
```
Strategy: EMA_Crossover
  Signals Generated: 80      ← How many signals this strategy produced
  Signals Used: 30           ← How many were actually used for trading
  Avg Confidence: 65.00%     ← Average confidence of signals
  Acceptance Rate: 37.5%     ← Percentage of signals that passed aggregation
```

#### **Acceptance Rate Interpretation:**

| Rate | Meaning | Action |
|------|---------|--------|
| >70% | Strategy dominates | Consider increasing weight |
| 40-70% | Healthy contribution | Good balance |
| 20-40% | Moderate filter | Normal for strict aggregation |
| <20% | Too filtered | Check aggregation mode or lower threshold |

#### **Signal Generation vs Usage:**

**Example:**
```
EMA Generated: 80 signals
EMA Used: 30 signals
RSI+BB Generated: 70 signals
RSI+BB Used: 15 signals
```

**Analysis:**
- EMA has better acceptance (37.5% vs 21.4%)
- EMA signals are higher quality for this period
- Consider increasing EMA weight slightly

---

## 🔍 Advanced Testing

### **1. Market Condition Testing**

Test different time periods for different market conditions:

#### **Bull Market (Trending):**
```bash
# Test during known bull run (e.g., Oct-Nov 2023)
python backtest.py 60  # Adjust dates in code
```

#### **Bear Market (Trending Down):**
```bash
# Test during known bear market
python backtest.py 60
```

#### **Sideways/Ranging:**
```bash
# Test during consolidation periods
python backtest.py 60
```

**Hypothesis:**
- EMA should perform better in trending markets
- RSI+BB should perform better in ranging markets

---

### **2. Timeframe Testing**

Test different candle timeframes:

```bash
# 1-hour (default)
BOT_TIMEFRAME=1h
python backtest.py 60

# 4-hour (more stable)
BOT_TIMEFRAME=4h
python backtest.py 60

# 15-minute (more trades)
BOT_TIMEFRAME=15m
python backtest.py 60
```

---

### **3. Parameter Optimization**

Create a testing script:

**`test_parameters.sh`:**
```bash
#!/bin/bash

echo "Testing different configurations..."

# Test 1: Conservative
export BOT_STRATEGY_AGGREGATION_MODE=unanimous
export BOT_MIN_SIGNAL_CONFIDENCE=0.5
python backtest.py 60 > results_conservative.txt

# Test 2: Balanced
export BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
export BOT_MIN_SIGNAL_CONFIDENCE=0.3
python backtest.py 60 > results_balanced.txt

# Test 3: Aggressive
export BOT_STRATEGY_AGGREGATION_MODE=any
export BOT_MIN_SIGNAL_CONFIDENCE=0.2
python backtest.py 60 > results_aggressive.txt

echo "Tests complete! Check results_*.txt files"
```

---

## 📊 Sample Output Analysis

### **Good Multi-Strategy Result:**

```
Win rate: 58.5%                  ✓ Above 50%
Total P&L: $450.00              ✓ Profitable
Strategy vs Buy & Hold: +8.2%   ✓ Beats buy & hold

EMA Acceptance: 45%             ✓ Healthy contribution
RSI+BB Acceptance: 38%          ✓ Healthy contribution
```

**Conclusion:** Both strategies contributing well, good synergy

---

### **Strategy Imbalance:**

```
Win rate: 52.0%
Total P&L: $280.00

EMA Acceptance: 78%             ⚠️ Dominates
RSI+BB Acceptance: 12%          ⚠️ Barely used
```

**Conclusion:** RSI+BB not contributing much
**Action:** Either:
- Increase RSI+BB weight
- Lower confidence threshold
- Disable RSI+BB if consistently low

---

### **Poor Results:**

```
Win rate: 42.0%                 ❌ Below 50%
Total P&L: -$125.00            ❌ Losing money
Strategy vs Buy & Hold: -12.5%  ❌ Worse than holding

Both strategies acceptance: <20% ❌ Too filtered
```

**Conclusion:** Configuration too conservative
**Action:**
- Lower confidence threshold
- Change to less strict aggregation mode
- Check if individual strategies work alone

---

## 💡 Best Practices

### **1. Test Before Live Trading**

```bash
# Test your exact live configuration
python backtest.py 60

# If results are good:
./deploy.sh
./start.sh

# If results are bad:
# Adjust configuration and test again
```

### **2. Test Multiple Time Periods**

```bash
# Short term (recent market)
python backtest.py 30

# Medium term
python backtest.py 60

# Long term
python backtest.py 90
```

Consistent performance across periods = robust strategy

### **3. Document Your Tests**

Create a testing log:

**`backtest_results.md`:**
```markdown
## Backtest Results Log

### Test 1: Multi-Strategy Weighted Voting (2024-01-10)
- Period: 60 days
- Config: EMA + RSI+BB, weighted_voting, 0.3 confidence
- Win Rate: 58.5%
- P&L: $450.00
- Notes: Good balance, both strategies contributing
- Status: ✅ Approved for production

### Test 2: EMA Only (2024-01-10)
- Period: 60 days  
- Config: EMA only
- Win Rate: 52.0%
- P&L: $320.00
- Notes: Lower win rate than multi-strategy
- Status: ❌ Multi-strategy performs better
```

---

## 🚨 Troubleshooting

### **Problem: "Multi-strategy system not available"**

**Cause:** `strategies/` module not found

**Solution:**
```bash
# Check if strategies folder exists
ls strategies/

# If not, you're using old code
# Pull latest changes or reinstall
```

---

### **Problem: Backtest uses wrong strategy**

**Cause:** `.env` settings don't match what you expect

**Solution:**
```bash
# Check current settings
cat .env | grep STRATEGY

# Verify what will be used
python -c "from config import BotConfig; c = BotConfig.load(); print(f'Multi-strategy: {c.use_multi_strategy}'); print(f'EMA enabled: {c.strategy_ema_enabled}'); print(f'RSI+BB enabled: {c.strategy_rsi_bb_enabled}')"
```

---

### **Problem: No strategy stats shown**

**Cause:** Multi-strategy disabled or only one strategy enabled

**Solution:**
- Enable multi-strategy: `BOT_USE_MULTI_STRATEGY=true`
- Enable both strategies

---

## 📚 Summary

### **Backtest Commands**

```bash
# Basic: Test current config for 30 days
python backtest.py 30

# Extended: Test for 60 days
python backtest.py 60

# Comprehensive: Test for 90 days
python backtest.py 90

# With custom days
python backtest.py 45
```

### **Configuration Checklist**

Before backtesting, verify your `.env`:

```bash
✓ BOT_USE_MULTI_STRATEGY=true
✓ BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
✓ BOT_MIN_SIGNAL_CONFIDENCE=0.3
✓ BOT_STRATEGY_EMA_ENABLED=true
✓ BOT_STRATEGY_RSI_BB_ENABLED=true
✓ BOT_STRATEGY_EMA_WEIGHT=1.0
✓ BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

### **What to Look For**

In results:
- ✅ Win rate >50%
- ✅ P&L positive
- ✅ Beats buy & hold
- ✅ Both strategies contributing (20-70% acceptance)
- ✅ Consistent across different periods

---

**Happy backtesting! 📊🔬🚀**
