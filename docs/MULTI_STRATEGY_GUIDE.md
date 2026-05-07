# Multi-Strategy Trading System Guide

## 🎯 Overview

The Next-Gen Trading Bot now supports **multiple concurrent trading strategies** that work together to generate better trading signals. Instead of relying on a single algorithm, the bot can:

- Run multiple strategies simultaneously
- Aggregate signals intelligently
- Track individual strategy performance
- Enable/disable strategies dynamically
- Configure strategy weights for voting

## 🚀 Quick Start

### Enable Multi-Strategy Mode

Edit your `.env` file:

```bash
# Enable multi-strategy system
BOT_USE_MULTI_STRATEGY=true

# Choose aggregation mode
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting

# Minimum confidence threshold (0.0 to 1.0)
BOT_MIN_SIGNAL_CONFIDENCE=0.3

# Enable individual strategies
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.0

BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

Then restart the bot:

```bash
./restart.sh
```

## 📊 Available Strategies

### 1. **EMA Crossover Strategy** (Trend Following)

**Best for:** Trending markets, capturing momentum moves

**How it works:**
- Uses 12/26 EMA crossover to detect trend changes
- Filters signals with RSI (avoids extremes)
- MACD confirmation (optional)
- Volume confirmation (requires above-average volume)
- ATR-based stop losses (volatility-adjusted)

**Strengths:**
- ✅ Excellent in trending markets
- ✅ Catches big moves early
- ✅ Well-tested and reliable

**Weaknesses:**
- ❌ Generates false signals in ranging markets
- ❌ Can lag during rapid reversals

**Configuration:**
```bash
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_SHORT_WINDOW=12
BOT_LONG_WINDOW=26
```

### 2. **RSI + Bollinger Bands Strategy** (Mean Reversion)

**Best for:** Ranging markets, oversold/overbought reversals

**How it works:**
- Detects oversold conditions (RSI < 30 + price at lower BB)
- Detects overbought conditions (RSI > 70 + price at upper BB)
- Looks for divergences (price vs RSI)
- Targets mean reversion to BB middle band
- Tighter stop losses for mean reversion

**Strengths:**
- ✅ Excellent in ranging/sideways markets
- ✅ High win rate on reversals
- ✅ Catches oversold bounces

**Weaknesses:**
- ❌ Can fail in strong trends
- ❌ Multiple false signals during trending moves

**Configuration:**
```bash
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_RSI_OVERSOLD=30
BOT_STRATEGY_RSI_BB_RSI_OVERBOUGHT=70
BOT_STRATEGY_RSI_BB_BB_PERIOD=20
BOT_STRATEGY_RSI_BB_BB_STD_DEV=2.0
```

## 🔄 Signal Aggregation Modes

### 1. **Weighted Voting** (Default, Recommended)

Strategies vote with weighted confidence scores. The direction with the highest weighted confidence wins (must be >50% of total weight).

**Use when:**
- ✅ You want balanced, high-confidence signals
- ✅ Strategies have different strengths
- ✅ You want to weight strategies differently

**Configuration:**
```bash
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

**Example:**
```
EMA Strategy: BULLISH (confidence: 0.7, weight: 1.0) → weighted score: 0.7
RSI+BB Strategy: NEUTRAL (confidence: 0.3, weight: 1.0) → weighted score: 0.0
---
Result: BULLISH (0.7 / 0.7 = 100% > 50% threshold)
```

### 2. **Simple Voting** (Majority Rules)

Each strategy gets one vote. Direction with >50% votes wins.

**Use when:**
- ✅ All strategies should have equal say
- ✅ You want simple democratic voting
- ✅ You don't want to tune confidence weights

**Configuration:**
```bash
BOT_STRATEGY_AGGREGATION_MODE=voting
```

**Example:**
```
EMA Strategy: BULLISH
RSI+BB Strategy: BULLISH
---
Result: BULLISH (2/2 = 100% agreement)
```

### 3. **Unanimous** (Ultra Conservative)

ALL enabled strategies must agree. Very conservative but high accuracy.

**Use when:**
- ✅ You want maximum confidence
- ✅ You prefer fewer, higher-quality signals
- ✅ You want to avoid false signals

**Configuration:**
```bash
BOT_STRATEGY_AGGREGATION_MODE=unanimous
```

**Example:**
```
EMA Strategy: BULLISH
RSI+BB Strategy: NEUTRAL
---
Result: NEUTRAL (not unanimous)
```

### 4. **Any** (Aggressive)

Any strategy can trigger a trade. Uses the most confident signal.

**Use when:**
- ✅ You want maximum trading opportunities
- ✅ You trust individual strategies
- ✅ You want to capture all potential moves

**Configuration:**
```bash
BOT_STRATEGY_AGGREGATION_MODE=any
```

**Example:**
```
EMA Strategy: NEUTRAL (confidence: 0.2)
RSI+BB Strategy: BULLISH (confidence: 0.8)
---
Result: BULLISH (highest confidence)
```

### 5. **Best** (Pick Strongest Signal)

Uses the signal with highest confidence, regardless of agreement.

**Use when:**
- ✅ You want the most confident signal
- ✅ Different strategies excel in different conditions
- ✅ You want dynamic strategy selection

**Configuration:**
```bash
BOT_STRATEGY_AGGREGATION_MODE=best
```

## 📈 Recommended Configurations

### For Beginners (Conservative)

```bash
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_AGGREGATION_MODE=unanimous
BOT_MIN_SIGNAL_CONFIDENCE=0.5

# Both strategies enabled with equal weight
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

**Why:** Only trades when both strategies agree, reducing false signals.

### For Balanced Trading (Recommended)

```bash
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting
BOT_MIN_SIGNAL_CONFIDENCE=0.3

# EMA weighted higher for trend detection
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.2
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

**Why:** Balances signal frequency with accuracy. Slightly favors trend-following.

### For Active Trading (Aggressive)

```bash
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_AGGREGATION_MODE=any
BOT_MIN_SIGNAL_CONFIDENCE=0.25

# Both strategies enabled
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.0
BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

**Why:** Maximizes trading opportunities. Either strategy can trigger.

### For Trending Markets Only

```bash
BOT_USE_MULTI_STRATEGY=false  # Or disable RSI+BB strategy
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_RSI_BB_ENABLED=false
```

**Why:** Mean reversion performs poorly in strong trends.

### For Ranging Markets Only

```bash
BOT_USE_MULTI_STRATEGY=false  # Or disable EMA strategy
BOT_STRATEGY_EMA_ENABLED=false
BOT_STRATEGY_RSI_BB_ENABLED=true
```

**Why:** Trend-following generates many false signals in ranging markets.

## 📊 Dashboard & Monitoring

### View Strategy Performance

Access the dashboard at `http://localhost:8000` and navigate to:

**API Endpoints:**

1. **List Strategies:**
   ```bash
   curl -u admin:password http://localhost:8000/api/strategies
   ```
   
   Returns:
   ```json
   {
     "multi_strategy_enabled": true,
     "aggregation_mode": "weighted_voting",
     "strategies": [
       {
         "name": "EMA_Crossover",
         "description": "EMA Crossover (12/26) with RSI, MACD, and Volume filters",
         "enabled": true,
         "weight": 1.0
       },
       {
         "name": "RSI_BB_MeanReversion",
         "description": "RSI (14) + Bollinger Bands (20, 2σ) Mean Reversion",
         "enabled": true,
         "weight": 1.0
       }
     ]
   }
   ```

2. **Strategy Statistics:**
   ```bash
   curl -u admin:password http://localhost:8000/api/strategies/stats
   ```
   
   Returns:
   ```json
   {
     "multi_strategy_enabled": true,
     "total_signals_generated": 150,
     "total_signals_used": 75,
     "stats": {
       "EMA_Crossover": {
         "signals_generated": 80,
         "signals_used": 45,
         "avg_confidence": 0.65,
         "generation_rate": 53.3,
         "usage_rate": 60.0,
         "acceptance_rate": 56.25
       },
       "RSI_BB_MeanReversion": {
         "signals_generated": 70,
         "signals_used": 30,
         "avg_confidence": 0.58,
         "generation_rate": 46.7,
         "usage_rate": 40.0,
         "acceptance_rate": 42.86
       }
     }
   }
   ```

### Interpret Strategy Stats

- **signals_generated**: Total signals produced by strategy
- **signals_used**: Signals that resulted in trades (passed aggregation)
- **avg_confidence**: Average confidence score (0.0 to 1.0)
- **generation_rate**: % of all signals generated by this strategy
- **usage_rate**: % of all trades attributed to this strategy
- **acceptance_rate**: % of this strategy's signals that passed aggregation

**Good acceptance rate:** 40-70% indicates good signal quality
**Low acceptance rate:** <30% suggests strategy not compatible with current market or aggregation mode
**High acceptance rate:** >80% indicates strategy dominance or over-fitting

## 🔍 Database Schema Updates

Trades now include strategy attribution:

```sql
SELECT 
  timestamp,
  side,
  price,
  pnl,
  strategy_name,
  signal_confidence
FROM trades
WHERE strategy_name = 'EMA_Crossover'
ORDER BY timestamp DESC
LIMIT 10;
```

Query strategy performance:

```sql
SELECT 
  strategy_name,
  COUNT(*) as trades,
  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
  AVG(pnl) as avg_pnl,
  SUM(pnl) as total_pnl
FROM trades
WHERE strategy_name IS NOT NULL
GROUP BY strategy_name;
```

## 🛠️ Advanced Usage

### Create Your Own Strategy

1. **Create a new strategy file:**

   ```python
   # strategies/my_strategy.py
   from .base_strategy import BaseStrategy, StrategySignal
   
   class MyCustomStrategy(BaseStrategy):
       def __init__(self, config: dict):
           super().__init__("MyCustom", config)
           # Initialize parameters from config
           
       def compute_signal(self, exchange, symbol, timeframe, candle_data=None):
           # Your strategy logic here
           # Return StrategySignal object
           pass
       
       def get_description(self):
           return "My custom strategy description"
       
       def get_parameters(self):
           return {"param1": self.param1, "param2": self.param2}
   ```

2. **Register in `strategies/__init__.py`:**

   ```python
   from .my_strategy import MyCustomStrategy
   
   __all__ = [
       'BaseStrategy',
       'StrategySignal',
       'EMACrossoverStrategy',
       'RSIBollingerBandsStrategy',
       'MyCustomStrategy',  # Add here
       'StrategyManager',
       'SignalAggregationMode',
   ]
   ```

3. **Add to config.py and main.py:**

   Follow the pattern for EMA and RSI+BB strategies.

### Disable a Strategy Dynamically

Via API (requires implementation):

```python
POST /api/strategies/disable
{
  "strategy_name": "EMA_Crossover"
}
```

Or via environment:

```bash
BOT_STRATEGY_EMA_ENABLED=false
```

## 📊 Backtesting with Multi-Strategy

Run backtest with multi-strategy enabled:

```bash
python backtest.py 30
```

The backtest will automatically use your configured strategies and aggregation mode.

## 🐛 Troubleshooting

### No Signals Being Generated

**Check:**
1. Are strategies enabled? (`BOT_STRATEGY_EMA_ENABLED=true`)
2. Is multi-strategy enabled? (`BOT_USE_MULTI_STRATEGY=true`)
3. Is confidence threshold too high? (Try `BOT_MIN_SIGNAL_CONFIDENCE=0.2`)
4. Is aggregation mode too strict? (Try `weighted_voting` or `any`)

**View logs:**
```bash
tail -f logs/bot.log | grep "Signal="
```

### Too Many Signals

**Solutions:**
1. Increase confidence threshold: `BOT_MIN_SIGNAL_CONFIDENCE=0.5`
2. Use stricter aggregation: `BOT_STRATEGY_AGGREGATION_MODE=unanimous`
3. Disable one strategy temporarily
4. Add more filters to individual strategies

### Strategy Conflict

**Symptoms:** Strategies constantly disagree (low acceptance rate)

**Solutions:**
1. Use `best` or `any` aggregation mode
2. Adjust strategy weights (favor one over the other)
3. Disable conflicting strategy in current market conditions

## 💡 Pro Tips

1. **Market Condition Adaptation:**
   - **Trending market**: Increase EMA weight, decrease RSI+BB weight
   - **Ranging market**: Increase RSI+BB weight, decrease EMA weight
   - **Volatile market**: Use `unanimous` mode for safety

2. **Confidence Tuning:**
   - Start with `0.3` and adjust based on results
   - Higher = fewer but better signals
   - Lower = more signals but more noise

3. **Strategy Weights:**
   - Weight doesn't need to be 1.0
   - Try 1.5 for primary strategy, 0.8 for secondary
   - Experiment to find your optimal ratio

4. **Monitor Performance:**
   - Check `/api/strategies/stats` daily
   - Look for strategies with low acceptance rates
   - Adjust weights based on current market conditions

5. **Backtesting:**
   - Test different aggregation modes
   - Compare single-strategy vs multi-strategy results
   - Validate on recent data (last 30-60 days)

## 🎓 Learning Resources

### Understanding the Code

- `strategies/base_strategy.py` - Strategy interface
- `strategies/ema_crossover_strategy.py` - Example trend-following strategy
- `strategies/rsi_bb_strategy.py` - Example mean reversion strategy
- `strategies/strategy_manager.py` - Signal aggregation logic

### Key Concepts

1. **Confidence Score**: How certain a strategy is about its signal (0.0 to 1.0)
2. **Strategy Weight**: Importance multiplier for voting (typically 0.5 to 2.0)
3. **Signal Aggregation**: Process of combining multiple signals into one
4. **Attribution**: Tracking which strategy generated a trade

## 📞 Support

If you encounter issues or have questions:

1. Check the logs: `./status.sh` or `tail -f logs/bot.log`
2. Review configuration: `/api/config` endpoint
3. Check strategy stats: `/api/strategies/stats` endpoint
4. Test in backtest mode first before live trading

## 🎉 Success Metrics

**Good multi-strategy performance:**
- ✅ Win rate >50%
- ✅ Both strategies being used (not just one)
- ✅ Acceptance rate between 40-70%
- ✅ Fewer trades but higher quality than single strategy
- ✅ Better risk-adjusted returns

---

**Happy multi-strategy trading! 🚀📈💰**
