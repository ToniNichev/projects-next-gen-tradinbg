# LLM Strategy: Why No Trades Are Happening

## Problem Statement
The LLM backtest completes successfully but produces **zero buy/sell transactions**, even after adjusting LLM parameters.

## Root Cause Analysis

### 1. **LLM Returning Neutral Signals** (Most Common)

**Symptom**: LLM analyzes market data but consistently returns `direction: "neutral"` instead of `"bullish"` or `"bearish"`.

**Why This Happens**:
- The prompt instructs: *"Set direction to neutral if signals are mixed or weak"*
- LLMs err on side of caution by default
- Technical indicators may genuinely show mixed signals
- LLM may not recognize patterns that humans see

**Evidence to Look For**:
```bash
# Check logs for LLM responses
grep -i "direction.*neutral" logs/bot_error.log
```

**Solutions**:
1. **Lower confidence threshold**:
   ```python
   min_signal_confidence: 0.2  # Instead of 0.3
   ```

2. **Adjust LLM temperature** (higher = more decisive):
   ```python
   llm_temperature: 0.5  # Instead of 0.3
   ```

3. **Try different market conditions**:
   - Trending markets generate clearer signals
   - Ranging/choppy markets produce more neutrals

4. **Use faster model** (phi3 more decisive than mistral):
   ```python
   llm_ollama_model: "phi3"
   ```

---

### 2. **Confidence Below Threshold**

**Symptom**: LLM returns bullish/bearish signal but with low confidence (e.g., 0.25) that gets filtered out.

**Why This Happens**:
- Default `min_signal_confidence` is 0.3 (30%)
- LLM may see weak pattern but not strong enough
- `require_patterns` setting can reduce confidence

**Evidence to Look For**:
```bash
# Check if signals are being generated but filtered
python diagnose_llm_signals.py
```

**Solutions**:
1. **Lower minimum confidence**:
   ```bash
   # In .env
   BOT_MIN_SIGNAL_CONFIDENCE=0.2
   ```

2. **Disable pattern requirement**:
   ```bash
   BOT_LLM_REQUIRE_PATTERNS=False
   ```

3. **Check aggregation mode** (see next section)

---

### 3. **Multi-Strategy Aggregation Filtering**

**Symptom**: LLM generates valid signals but they're filtered out by multi-strategy logic.

**Why This Happens**:
- **Unanimous mode**: Requires ALL strategies to agree (very strict)
- **Voting mode**: LLM alone can't create majority if 3+ strategies
- **Other strategies disabled**: LLM has low weight

**Evidence to Look For**:
```python
# Check config
strategy_aggregation_mode: "unanimous"  # Very restrictive!
strategy_llm_weight: 1.0  # vs other strategies with higher weights
```

**Solutions**:
1. **Change aggregation mode**:
   ```python
   strategy_aggregation_mode: "any"  # Any strategy can trigger
   ```

2. **Disable other strategies for testing**:
   ```python
   strategy_ema_enabled: False
   strategy_rsi_bb_enabled: False
   strategy_macd_enabled: False
   strategy_llm_enabled: True
   ```

3. **Increase LLM weight**:
   ```python
   strategy_llm_weight: 2.0  # vs 1.5, 1.3 for others
   ```

---

### 4. **Insufficient Backtest Sampling**

**Symptom**: Only 1-2 LLM analyses occur during entire backtest, missing trading opportunities.

**Why This Happens**:
- `llm_backtest_sample_interval` too high (e.g., 50)
- With 100 candles, only 2 analysis points
- Market conditions may not be right at those exact points

**Evidence to Look For**:
```
llm_pattern: 📊 Backtest configured - 100 candles, sampling every 50 = 2 analyses
```

**Solutions**:
1. **Reduce sampling interval**:
   ```python
   llm_backtest_sample_interval: 12  # Analyze more frequently
   ```

2. **Increase backtest duration**:
   ```bash
   python backtest.py 14  # Instead of 3 days
   ```

---

### 5. **Position Size Too Low**

**Symptom**: Signals generated but trades don't execute due to minimum position requirements.

**Why This Happens**:
- LLM suggests very small position (0.10 = 10%)
- Exchange has minimum order size
- Paper trader may have position size filters

**Evidence to Look For**:
```python
suggested_position_size: 0.10  # Too small?
```

**Solutions**:
1. **Increase min position size**:
   ```python
   min_position_size: 0.20  # 20% minimum
   ```

2. **Check order_pct in config**:
   ```python
   order_pct: 0.40  # 40% per trade
   ```

---

### 6. **LLM Response Parsing Failures**

**Symptom**: LLM generates response but parser can't extract JSON.

**Why This Happens**:
- LLM doesn't follow JSON format exactly
- Extra text before/after JSON
- Malformed JSON (missing quotes, commas)

**Evidence to Look For**:
```
WARNING: No valid JSON found, parsing natural language
```

**Solutions**:
1. **Check raw LLM responses**:
   ```python
   python diagnose_llm_signals.py
   ```

2. **Use different model**:
   - phi3 tends to follow JSON better
   - mistral sometimes adds extra text

3. **Adjust num_predict**:
   ```python
   llm_num_predict: 800  # Shorter, more focused
   ```

---

## Diagnostic Process

### Step 1: Run Diagnostic Tool
```bash
python diagnose_llm_signals.py
```

This will show you:
- ✅ What market data LLM receives
- ✅ Raw LLM response
- ✅ Parsed signal (direction, confidence)
- ✅ Whether it meets thresholds
- ✅ How aggregation filters it
- ✅ Why trade doesn't happen

### Step 2: Check Configuration
```bash
# View current config
python -c "from config import BotConfig; c = BotConfig.load(); print(f'Min Confidence: {c.min_signal_confidence}'); print(f'Aggregation: {c.strategy_aggregation_mode}'); print(f'LLM Enabled: {c.strategy_llm_enabled}')"
```

### Step 3: Test with Minimal Config
```python
# backtest_llm_only.py
from backtest import run_backtest

config_overrides = {
    # Disable all other strategies
    "strategy_ema_enabled": False,
    "strategy_rsi_bb_enabled": False,
    "strategy_macd_enabled": False,
    "strategy_llm_enabled": True,
    
    # Lower thresholds
    "min_signal_confidence": 0.2,
    "llm_require_patterns": False,
    
    # Analyze more frequently
    "llm_backtest_sample_interval": 12,
    
    # Use faster model
    "llm_ollama_model": "phi3",
    "llm_timeout_seconds": 30,
}

result = run_backtest(
    days_back=7,
    config_overrides=config_overrides
)

print(f"Trades: {result['trades']}")
print(f"P&L: {result['pnl_pct']:.2f}%")
```

### Step 4: Enable Enhanced Logging
```python
# In your backtest script
import logging
logging.basicConfig(level=logging.INFO)

# Now run backtest - will show each LLM signal
```

---

## Common Scenarios & Solutions

### Scenario 1: "LLM keeps saying neutral"

**Quick Fix**:
```bash
# In .env or config overrides
BOT_MIN_SIGNAL_CONFIDENCE=0.2
BOT_LLM_TEMPERATURE=0.5
BOT_LLM_REQUIRE_PATTERNS=False
```

**Test**:
```bash
python diagnose_llm_signals.py
# Look at "Reasoning" to understand why LLM is cautious
```

### Scenario 2: "Signals generated but filtered out"

**Quick Fix**:
```bash
# Test with LLM only
BOT_STRATEGY_EMA_ENABLED=False
BOT_STRATEGY_RSI_BB_ENABLED=False
BOT_STRATEGY_MACD_ENABLED=False
BOT_STRATEGY_LLM_ENABLED=True
BOT_STRATEGY_AGGREGATION_MODE=any
```

### Scenario 3: "Only 1-2 analyses in 7-day backtest"

**Quick Fix**:
```bash
BOT_LLM_BACKTEST_SAMPLE_INTERVAL=12  # Analyze every 12 candles
# For 1h timeframe, 7 days = 168 candles = 14 analyses
```

### Scenario 4: "Confidence always below threshold"

**Quick Fix**:
```bash
# Either lower threshold
BOT_MIN_SIGNAL_CONFIDENCE=0.15

# Or investigate why confidence is low
python diagnose_llm_signals.py
# Check "Patterns Found" - if empty, that's why
```

---

## Recommended Backtest Configuration

### For Testing (verify LLM generates signals):
```python
config_overrides = {
    # LLM only
    "strategy_ema_enabled": False,
    "strategy_rsi_bb_enabled": False,
    "strategy_macd_enabled": False,
    "strategy_llm_enabled": True,
    
    # Permissive thresholds
    "min_signal_confidence": 0.2,
    "llm_require_patterns": False,
    
    # Frequent analysis
    "llm_backtest_sample_interval": 12,
    
    # Fast model
    "llm_ollama_model": "phi3",
    "llm_temperature": 0.4,
}

# Run with 7-14 days for meaningful results
result = run_backtest(days_back=7, config_overrides=config_overrides)
```

### For Production (balanced risk):
```python
config_overrides = {
    # All strategies enabled with weights
    "strategy_llm_enabled": True,
    "strategy_llm_weight": 2.0,  # Higher weight
    
    # Moderate thresholds
    "min_signal_confidence": 0.3,
    "llm_require_patterns": False,
    
    # Reasonable sampling
    "llm_backtest_sample_interval": 12,
    
    # Aggregation
    "strategy_aggregation_mode": "weighted_voting",
}

result = run_backtest(days_back=30, config_overrides=config_overrides)
```

---

## Verification Checklist

Before running a backtest, verify:

- [ ] **Ollama is running**: `curl http://localhost:11434/api/tags`
- [ ] **Model is loaded**: `ollama list | grep mistral`
- [ ] **Enough data**: 7+ days for 1h timeframe
- [ ] **Min confidence reasonable**: 0.2-0.4 range
- [ ] **LLM is enabled**: `strategy_llm_enabled=True`
- [ ] **Sample interval appropriate**: 12-24 for hourly data
- [ ] **Other strategies not blocking**: Test with LLM-only first
- [ ] **Timeout sufficient**: 30-60s depending on model

---

## Debug Commands

```bash
# 1. Run full diagnostic
python diagnose_llm_signals.py

# 2. Check Ollama status
curl http://localhost:11434/api/tags

# 3. Test LLM connectivity
python test_llm_backtest.py

# 4. Check recent backtests
tail -50 data/backtest_log.csv

# 5. View LLM analysis logs
grep -i "llm_pattern" logs/bot_error.log | tail -50

# 6. Check signal generation
grep -i "Generated signal" logs/bot_error.log | tail -20

# 7. Verify config
python -c "from config import BotConfig; c=BotConfig.load(); print(c.__dict__)"
```

---

## Expected Behavior

After fixes, you should see:

```
llm_pattern: 📊 Backtest configured - 168 candles, sampling every 12 = 14 analyses
llm_pattern: 🔍 Analysis 1/14 (7%) - Candle 60 (window: 60 candles)
llm_pattern: Generated signal - BULLISH (confidence: 65.0%, position: 25.0%)
llm_pattern: Trade details - Entry: $69000.00, Stop: $67275.00, Target: $71760.00

[2026-02-25 10:15:23] Trade #1: BUY 0.145000 @ $69000.00 | Portfolio: $10250.00
```

If you still see only neutral signals after following this guide:
1. The market data genuinely shows mixed/unclear signals
2. Try different date ranges (trending markets better)
3. Consider adjusting the prompt in `prompt_builder.py` to be less conservative
4. Use a different model (each has different decision-making style)

---

## Files Modified

1. **strategies/llm/strategy.py**: Added signal logging
2. **diagnose_llm_signals.py**: New diagnostic tool
3. **LLM_NO_TRADES_ANALYSIS.md**: This document

## Next Steps

1. **Run diagnostic**: `python diagnose_llm_signals.py`
2. **Review output**: Understand why signals are neutral/filtered
3. **Adjust config**: Based on diagnostic recommendations
4. **Test backtest**: Start with 3-7 days, LLM-only
5. **Verify trades**: Check `data/backtest_log.csv` for trade records
6. **Scale up**: Once working, test with longer periods and multiple strategies
