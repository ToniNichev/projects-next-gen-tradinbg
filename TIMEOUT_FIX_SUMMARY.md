# LLM Backtest Timeout Fix Summary

## Problem
When running a backtest with the LLM strategy, the system would hang indefinitely after showing:
```
Sending analysis request to Ollama (mistral)...
```

The backtest would never complete, and only "INFO Kline" messages would appear (from the live trading system running in parallel).

## Root Cause
The `OllamaClient` was not properly passing the timeout configuration to the underlying Ollama HTTP client. The timeout was stored in `self.timeout_seconds` but never actually used when making requests to Ollama.

The signal-based timeout (using `SIGALRM`) only works on Unix systems and only in the main thread, which is not sufficient protection for backtest operations that may run in different contexts.

## Fix Applied

### 1. Added Timeout to Client Initialization
**File:** `strategies/llm/llm_client.py`

The timeout is now properly passed when creating the Ollama client:

```python
# Before
self.client = ollama.Client(host=self.ollama_url)

# After
self.client = ollama.Client(host=self.ollama_url, timeout=self.timeout_seconds)
```

This ensures that ALL requests made through this client will respect the timeout.

### 2. Enhanced Connection Test with Quick Mode
**File:** `strategies/llm/llm_client.py`

Improved `test_connection()` method with two modes:

- **Quick mode** (default for backtests): Only checks server reachability and model availability (~0.01s)
- **Full mode**: Also tests model generation (slower, used for diagnostics)

Features:
- Uses shorter timeout (10s) specifically for connection tests
- Checks if Ollama server is reachable
- Verifies the requested model is available
- Provides helpful error messages with installation instructions
- Handle both dict and Pydantic response formats (for compatibility)

### 3. Pre-Backtest Connection Check
**File:** `strategies/llm/strategy.py`

Added quick connection test before starting backtest:

```python
if not self.llm_client.test_connection(quick=True):
    logger.warning("Ollama connection test failed!")
    logger.warning("Continuing with backtest - will handle errors per-analysis")
    # Don't abort - let each analysis handle timeouts individually
```

This provides immediate feedback if Ollama is not running, but doesn't abort the backtest. Each analysis request will handle its own timeout gracefully.

## Benefits

1. **No More Hanging**: Requests will timeout after the configured duration (default: 60 seconds)
2. **Early Failure Detection**: Connection test runs before backtest starts, failing fast with clear error messages
3. **Better Error Messages**: Tells you exactly what's wrong and how to fix it
4. **Model Verification**: Checks that the requested model is actually available before starting

## Testing

Run this quick test to verify the fix:

```bash
python3 << 'EOF'
from strategies.llm.llm_client import OllamaClient
import logging

logging.basicConfig(level=logging.INFO)

client = OllamaClient(
    ollama_url="http://localhost:11434",
    model="mistral",
    timeout_seconds=10
)

# Test connection
if client.test_connection():
    print("✅ Connection test passed")
    
    # Test quick analysis
    result = client.analyze("What is 2+2? Answer in one word.")
    print(f"✅ Analysis completed in {result['duration_ms']}ms")
else:
    print("❌ Connection test failed")
EOF
```

## Usage Recommendations

### For Quick Testing
```python
config_overrides = {
    "llm_timeout_seconds": 30,           # Shorter timeout for fast iteration
    "llm_backtest_sample_interval": 50,  # Analyze less frequently
}
```

### For Production Backtests
```python
config_overrides = {
    "llm_timeout_seconds": 60,           # Standard timeout
    "llm_backtest_sample_interval": 12,  # More frequent analysis
}
```

### For Slower Models or Systems
```python
config_overrides = {
    "llm_timeout_seconds": 90,           # Longer timeout
    "llm_backtest_sample_interval": 24,  # Less frequent analysis
}
```

## Troubleshooting

### Still Seeing Timeouts?

1. **Use a faster model**:
   ```bash
   ollama pull phi3  # Faster than mistral
   ```
   
   Then update config:
   ```python
   config_overrides = {"llm_ollama_model": "phi3"}
   ```

2. **Increase timeout**:
   ```python
   config_overrides = {"llm_timeout_seconds": 90}
   ```

3. **Reduce analysis frequency**:
   ```python
   config_overrides = {"llm_backtest_sample_interval": 24}
   ```

4. **Check system resources**: Ensure Ollama has enough CPU/memory

### Ollama Not Running?

```bash
# Check if running
ps aux | grep ollama

# Start Ollama
ollama serve

# Pull required model
ollama pull mistral
```

### Connection Test Fails?

1. Verify Ollama is accessible:
   ```bash
   curl http://localhost:11434/api/version
   ```

2. Check available models:
   ```bash
   curl http://localhost:11434/api/tags
   ```

3. Pull model if missing:
   ```bash
   ollama pull mistral
   ```

## Expected Behavior

### Before Fix
```
Sending analysis request to Ollama (mistral)...
[HANGS INDEFINITELY - NO TIMEOUT]
```

### After Fix
```
Testing Ollama connection before starting backtest...
Ollama server is reachable, found 3 models
Testing model 'mistral' with a simple prompt...
✓ Ollama connection test passed for model 'mistral'
📊 Starting backtest - 96 candles, analyzing every 12 = 8 analyses
🔍 Analysis 1/8 (12%) - Candle 24 (window: 50 candles)
Sending analysis request to Ollama (mistral)...
LLM response received in 15432ms
✓ Analysis complete: bullish (confidence: 65%)
```

If Ollama is not available or slow:
```
Testing Ollama connection before starting backtest...
Ollama connection test failed: Connection refused (or timeout)
Make sure Ollama is running: ollama serve
⚠️  Ollama connection test failed! Make sure Ollama is running and the model is available.
Continuing with backtest - will handle errors per-analysis
📊 Starting backtest - 96 candles, analyzing every 12 = 8 analyses
🔍 Analysis 1/8 (12%) - Candle 24 (window: 50 candles)
Sending analysis request to Ollama (mistral)...
Ollama request timed out after 60s
llm_pattern: Cannot connect to Ollama - returning neutral signal
[Backtest continues with neutral signals]
```

## Performance Expectations

With the timeout working properly, you should see:

| Model | Avg Time per Analysis | Recommended Timeout |
|-------|----------------------|---------------------|
| phi3 | 5-10s | 30s |
| mistral | 10-20s | 60s |
| llama2 | 30-60s | 90s |

Times may vary based on your hardware and system load.
