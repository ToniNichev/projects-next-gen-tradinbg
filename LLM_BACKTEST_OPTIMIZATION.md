# LLM Backtest Optimization - Sampling Implementation

**Date**: 2026-02-07  
**Status**: ✅ Implemented and Ready to Test

---

## Problem Solved

**Before**: LLM backtests were extremely slow or timing out
- 7 days on 5m timeframe = 2,016 candles
- Each LLM call takes ~8 seconds (phi3)
- Total time: 2,016 × 8s = **4.5 hours!** ⏰

**After**: LLM analyzes only every Nth candle (sampling)
- Default: Every 12 candles = once per hour on 5m
- 7 days = 168 LLM calls (instead of 2,016)
- Total time: 168 × 8s = **22 minutes** ✅

---

## Changes Implemented

### 1. **Added Shorter Backtest Periods** ✅

**File**: `templates/backtest.html`

Added quick test options:
- **1 day** (Quick test) - NEW!
- **3 days** - NEW!
- 7 days
- 14 days
- 30 days
- 60 days
- 90 days

### 2. **Implemented LLM Sampling Logic** ✅

**File**: `strategies/llm_pattern_strategy.py`

**New Features**:
- `backtest_sample_interval` parameter (default: 12 candles)
- Tracks candle count during backtests
- Only calls LLM every Nth candle
- Reuses last analysis for skipped candles
- Logs sampling activity for visibility

**How it works**:
```python
# Backtest mode detected
self._backtest_candle_count += 1  # Track candles

# Should we analyze this candle?
should_analyze = (self._backtest_candle_count % 12 == 0)

if should_analyze:
    # Call LLM (every 12th candle)
    analysis = self._analyze_with_llm(...)
    self._last_backtest_analysis = analysis  # Save for reuse
else:
    # Reuse last analysis (11 out of 12 candles)
    return self._signal_from_analysis(self._last_backtest_analysis, ...)
```

### 3. **Added Configuration Parameter** ✅

**Files Modified**:
- `config.py` - Added `llm_backtest_sample_interval`
- `dashboard.py` - Added to API endpoints
- `strategies/llm_pattern_strategy.py` - Added to initialization

**Configuration Options**:

| Setting | Timeframe | Frequency | Best For |
|---------|-----------|-----------|----------|
| `llm_backtest_sample_interval = 1` | Any | Every candle | Testing (very slow!) |
| `llm_backtest_sample_interval = 6` | 5m | Every 30 min | Frequent analysis |
| `llm_backtest_sample_interval = 12` | 5m | Every 1 hour | **Default - Recommended** |
| `llm_backtest_sample_interval = 24` | 5m | Every 2 hours | Less frequent |
| `llm_backtest_sample_interval = 288` | 5m | Once per day | Very infrequent |

---

## Performance Improvements 🚀

### Example: 7-Day Backtest on 5m Timeframe

**Before** (analyzing every candle):
```
Total candles: 2,016
LLM calls: 2,016
Time per call: 8s
Total time: 4.5 hours ❌
```

**After** (sampling every 12 candles):
```
Total candles: 2,016
LLM calls: 168 (2,016 / 12)
Time per call: 8s
Total time: 22 minutes ✅ (12x faster!)
```

### Recommended Test Periods

| Timeframe | Days | Total Candles | LLM Calls (12×) | Est. Time (phi3) |
|-----------|------|---------------|-----------------|------------------|
| **5m** | 1 day | 288 | 24 | 3 min |
| **5m** | 3 days | 864 | 72 | 10 min |
| **5m** | 7 days | 2,016 | 168 | 22 min |
| **1h** | 7 days | 168 | 14 | 2 min |
| **1h** | 30 days | 720 | 60 | 8 min |

---

## How to Use

### Option 1: Quick Test (Recommended for First Run)

1. **Open Backtest page**
2. **Select "1 day (Quick test)"** from dropdown
3. **Keep LLM enabled**
4. **Click "Run Backtest"**
5. **Wait ~3 minutes**

Expected output:
```
INFO: Analyzing candle 12 (every 12 candles)
INFO: llm_pattern: LLM response received in 8234ms
INFO: Analyzing candle 24 (every 12 candles)
...
```

### Option 2: Longer Backtest

1. **Select "3 days" or "7 days"**
2. **Ensure Ollama is running**: `ollama serve`
3. **Ensure phi3 model is loaded**: Model should be "phi3" (not "phi")
4. **Run backtest**

### Option 3: Adjust Sampling Interval

**Via Database** (before starting backtest):
```bash
sqlite3 data/trading.db "INSERT OR REPLACE INTO strategy_config (key, value, value_type) VALUES ('llm_backtest_sample_interval', '6', 'int');"
```

**Via .env File**:
```bash
BOT_LLM_BACKTEST_SAMPLE_INTERVAL=6  # More frequent (every 30 min on 5m)
```

**Via Code** (for testing):
```python
# In backtest.py or config
llm_backtest_sample_interval = 6  # Analyze every 6 candles
```

---

## Understanding the Logs

### Good Backtest Logs (Working)

```
INFO: ✓ Enabled: llm_pattern (weight: 1.0)
INFO: Analyzing candle 12 (every 12 candles)
INFO: llm_pattern: Sending market analysis request to Ollama (phi3)...
INFO: HTTP Request: POST http://localhost:11434/api/generate "HTTP/1.1 200 OK"
INFO: llm_pattern: LLM response received in 8234ms
INFO: Manual LLM analysis completed: bullish (confidence: 0.65)
DEBUG: llm_pattern: Skipping candle 13 (sampling every 12)
DEBUG: llm_pattern: Skipping candle 14 (sampling every 12)
...
DEBUG: llm_pattern: Skipping candle 23 (sampling every 12)
INFO: Analyzing candle 24 (every 12 candles)
```

### Problem Indicators

**❌ Model Not Found**:
```
ERROR: model 'phi' not found (status code: 404)
```
→ Fix: Update model name to `phi3` in database

**❌ Ollama Not Running**:
```
ERROR: Cannot connect to Ollama
```
→ Fix: Start Ollama with `ollama serve`

**❌ Too Slow**:
```
INFO: Analyzing candle 1
INFO: Analyzing candle 2
INFO: Analyzing candle 3
```
→ Issue: Sampling not working, analyzing every candle!
→ Check: `llm_backtest_sample_interval` is set correctly

---

## Configuration Details

### New Configuration Parameter

**Name**: `llm_backtest_sample_interval`  
**Type**: Integer  
**Default**: 12  
**Range**: 1-288 (practical)  
**Unit**: Number of candles

**What it controls**: How often the LLM analyzes during backtests
- `1` = Every candle (very slow, only for testing)
- `12` = Every 12 candles (recommended default)
- `24` = Every 24 candles (less frequent)
- `288` = Once per day on 5m timeframe

### Environment Variable

```bash
# In .env file
BOT_LLM_BACKTEST_SAMPLE_INTERVAL=12
```

### Database Config

```sql
-- Check current value
SELECT key, value FROM strategy_config WHERE key='llm_backtest_sample_interval';

-- Set new value
INSERT OR REPLACE INTO strategy_config (key, value, value_type, category, description)
VALUES ('llm_backtest_sample_interval', '12', 'int', 'llm', 'Analyze every Nth candle in backtests');
```

---

## Important Notes ⚠️

### 1. **Sampling Only Affects Backtests**
- Live trading: LLM called normally (no sampling)
- Manual analysis: LLM called immediately (no sampling)
- Backtests: LLM sampled every N candles

### 2. **Trade Signals Between Samples**
When LLM is not analyzing:
- Strategy returns last known signal
- No new analysis = no new decision changes
- Trades can still execute based on last signal

### 3. **First Candle Behavior**
- First few candles (before first sample) return neutral
- Analysis starts at candle #12 (or whatever interval is set)

### 4. **Timeframe Matters**
- 5m timeframe: 12 candles = 1 hour ✓
- 1h timeframe: 12 candles = 12 hours (adjust to 6 for 6-hour sampling)
- 4h timeframe: 12 candles = 2 days (adjust to 3 for 12-hour sampling)

---

## Troubleshooting

### "Backtest still taking forever"

**Check**:
1. Is sampling enabled? (should see "Analyzing candle 12, 24, 36...")
2. Is interval too small? (default should be 12)
3. Is Ollama responding quickly? (should be <10 seconds per call)

**Fix**:
```bash
# Verify sampling is configured
sqlite3 data/trading.db "SELECT * FROM strategy_config WHERE key LIKE '%llm%';"

# Set higher interval for faster backtest
sqlite3 data/trading.db "UPDATE strategy_config SET value='24' WHERE key='llm_backtest_sample_interval';"
```

### "All signals are neutral"

**Cause**: No analysis has run yet (before first sample)

**Fix**: Wait for first sample (candle #12) - you'll see "Analyzing candle 12..."

### "Model not found"

**Cause**: Model name mismatch (`phi` vs `phi3`)

**Fix**:
```bash
# Update model name
sqlite3 data/trading.db "UPDATE strategy_config SET value='phi3' WHERE key='llm_ollama_model';"

# Restart bot
```

---

## Testing Checklist

Before running a full backtest:

- [ ] Ollama is running (`curl http://localhost:11434/api/version`)
- [ ] Model exists (`ollama list` shows `phi3:latest`)
- [ ] Model config is correct (`phi3`, not `phi`)
- [ ] Sampling is configured (check logs for "every 12 candles")
- [ ] Start with 1-day test first
- [ ] Check logs for sampling messages

---

## Future Improvements (Optional)

### Potential Enhancements:

1. **Adaptive Sampling**: Sample more frequently during volatile periods
2. **Multiple Analysis Modes**: Different sampling for different market conditions
3. **Caching LLM Results**: Pre-compute and cache all LLM analyses before backtest
4. **Parallel Processing**: Analyze multiple candles simultaneously
5. **UI Control**: Add sampling interval slider to Backtest page

---

## Summary

✅ **1-day backtest option added**  
✅ **3-day backtest option added**  
✅ **LLM sampling implemented** (every 12 candles by default)  
✅ **Configuration parameter added** (`llm_backtest_sample_interval`)  
✅ **Performance: 12x faster** backtests  
✅ **Logs show sampling activity** for visibility  

**Ready to test!** Start with a 1-day backtest to verify everything works, then scale up to longer periods.

---

## Quick Start Commands

```bash
# 1. Ensure phi3 model exists
ollama list | grep phi3

# 2. If not, update config
sqlite3 data/trading.db "UPDATE strategy_config SET value='phi3' WHERE key='llm_ollama_model';"

# 3. Restart bot
python3 main.py

# 4. Run 1-day backtest from UI
# → Select "1 day (Quick test)"
# → Click "Run Backtest"
# → Wait ~3 minutes

# 5. Check logs for sampling
tail -f backtest.log | grep "Analyzing candle"
```

---

**Happy Backtesting!** 🚀
