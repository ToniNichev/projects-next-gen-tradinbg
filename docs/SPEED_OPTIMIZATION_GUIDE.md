# LLM Backtest Speed Optimization Guide

## Problem: Your System Takes 60-90s Per Analysis

Current situation:
- **168 analyses** = 3+ hours total
- phi3 taking 60-90s per request
- Backtest unusably slow

---

## Why RAG Won't Help

**Your Question**: "Could RAG help speed this up?"

**Answer**: No, RAG actually makes it **SLOWER**

### What RAG Does:
- Adds context: Retrieves similar trades from history
- **Adds to prompt length**: More tokens to process
- **Increases processing time**: More data for LLM to analyze
- **Purpose**: Better decisions, NOT faster inference

### Current Status:
Your RAG is already enabled but won't affect speed. It's for **accuracy**, not **performance**.

---

## Solutions to Speed Up Backtests

### 🏆 Solution 1: Reduce Number of Analyses (BEST)

**Problem**: Analyzing every 12 candles = 168 analyses
**Solution**: Analyze every 50 candles = ~10 analyses

```python
"llm_backtest_sample_interval": 50  # Was 12
```

**Impact**:
- Time: 3 hours → 15 minutes ✅
- Trade opportunities: Slightly reduced (acceptable tradeoff)

**Use script**: `python3 backtest_llm_fast.py`

---

### 🚀 Solution 2: Optimize Prompt Length

**Problem**: Long prompt = more processing
**Current**: ~2669 characters

**Optimizations**:
```python
"llm_num_predict": 500,        # Shorter responses (was 1000)
"llm_lookback_days": 3,        # Less history context (was 7)
"llm_use_rag": False,          # Disable RAG for speed
```

**Impact**: 60-90s → 40-60s per analysis

---

### ⚡ Solution 3: Use Streaming (Advanced)

Not currently implemented, but could add:
- Stream responses instead of waiting for completion
- Process partial results
- Cancel early if confidence threshold met

**Impact**: Could reduce to 30-40s per analysis

---

### 🔧 Solution 4: Hardware Optimization

**Check if Ollama is using GPU**:
```bash
# Check GPU usage while LLM runs
# macOS:
sudo powermetrics --samplers gpu_power -i 1000

# Or Activity Monitor → Window → GPU History
```

**If NO GPU acceleration**:
- phi3 running on CPU is SLOW
- M1/M2 Mac should use GPU automatically
- Intel Mac may need manual GPU setup

**Fix**:
```bash
# Restart Ollama to reinitialize
pkill ollama
sleep 2
ollama serve
```

---

### 📊 Solution 5: Reduce Backtest Period

**Current**: 7 days, 168 candles
**Alternative**: 3 days, 72 candles

```python
result = run_backtest(days_back=3, ...)
```

**Impact**: Fewer candles = fewer analyses = faster completion

---

### 🎯 Solution 6: Batch Processing (Future)

Not implemented, but could:
- Queue multiple analysis requests
- Process in parallel
- Use multiple Ollama instances

**Impact**: Could process 2-3 analyses simultaneously

---

## Recommended Configuration for Your System

### For Quick Testing (10-15 minutes):
```python
config_overrides = {
    "llm_backtest_sample_interval": 50,  # ~10 analyses
    "llm_timeout_seconds": 120,
    "llm_num_predict": 500,
    "llm_lookback_days": 3,
    "llm_use_rag": False,
}

run_backtest(days_back=7, config_overrides=config_overrides)
```

### For Production (30-45 minutes):
```python
config_overrides = {
    "llm_backtest_sample_interval": 24,  # ~30 analyses
    "llm_timeout_seconds": 120,
    "llm_num_predict": 600,
    "llm_lookback_days": 5,
    "llm_use_rag": True,  # Keep for accuracy
}

run_backtest(days_back=14, config_overrides=config_overrides)
```

---

## Performance Comparison

| Config | Analyses | Time per | Total Time | Use Case |
|--------|----------|----------|------------|----------|
| **Current** | 168 | 75s | 3.5 hours | ❌ Too slow |
| **Fast** | 10 | 60s | 10 min | ✅ Quick test |
| **Balanced** | 30 | 60s | 30 min | ✅ Production |
| **Thorough** | 100 | 60s | 100 min | ⚠️ Deep analysis |

---

## Why Your System Is Slow

### Typical Performance:
- **Fast systems**: 8-15s per phi3 analysis
- **Average systems**: 20-30s per phi3 analysis
- **Your system**: 60-90s per phi3 analysis

### Possible Causes:
1. **No GPU acceleration** (most likely)
2. **CPU bottleneck** (system busy)
3. **Memory swapping** (insufficient RAM)
4. **Ollama configuration issue**

### Debug:
```bash
# Check system resources during LLM call
top -l 1 | head -20

# Check if phi3 is in memory
ps aux | grep "ollama runner"

# Check Ollama version
ollama --version
```

---

## Alternative: Cloud LLM Services

If local LLM is too slow, consider:

### Option 1: OpenAI API
- **Speed**: 2-5s per analysis
- **Cost**: ~$0.01 per analysis
- **Quality**: Better than phi3

### Option 2: Anthropic Claude
- **Speed**: 3-6s per analysis
- **Cost**: ~$0.015 per analysis
- **Quality**: Excellent

### Implementation:
Would require modifying `llm_client.py` to support API providers.

---

## Immediate Action Plan

1. **Stop current backtest** (Ctrl+C)

2. **Run fast version**:
   ```bash
   python3 backtest_llm_fast.py
   ```
   This completes in 10-15 minutes

3. **Check GPU usage** during run:
   - Activity Monitor → GPU tab
   - If 0% GPU usage, restart Ollama

4. **If satisfied**, adjust `sample_interval` for your needs:
   - 50 = super fast, fewer trades
   - 30 = balanced
   - 20 = thorough, slower

---

## Long-term Solutions

### For Your System:
1. **Accept longer runtimes** with optimized sampling
2. **Use for live trading** (1 analysis per 15 min is fine)
3. **Run backtests overnight** with thorough settings
4. **Consider cloud LLM** for faster iteration

### Hardware Upgrade Path:
- **M1/M2 Mac**: Already optimal for phi3
- **Intel Mac**: Consider M-series or cloud
- **Linux**: Ensure CUDA/ROCm for GPU acceleration

---

## Summary

**RAG won't help speed** - it's for accuracy, not performance.

**Best solution for you**:
```bash
python3 backtest_llm_fast.py
```

This reduces analyses from 168 → 10, cutting time from 3 hours → 15 minutes.

**For production**: Use `sample_interval: 24-50` based on speed/accuracy tradeoff you need.
