# Dashboard Showing Null Data - Bug Fix

## Problem
The dashboard was showing null/empty data even though the console logs showed kline data was being received from Binance websocket.

## Root Cause
When a candle closed, the bot tried to compute the trading signal by calling `exchange.fetch_ohlcv()` to get historical data for moving average calculation. This API call was failing with:

```
ERROR websocket cycle failed: binanceus {"code":-71012,"msg":"IPv6 not supported"}
```

**Why this happened:**
- Your system was trying to connect to Binance.US using IPv6
- Binance.US doesn't support IPv6 connections
- The CCXT library defaults to IPv6 when available

**Impact:**
- Signal computation failed on every closed candle
- `update_state()` was never called
- Dashboard history array remained empty
- UI showed null because there was no data

## Solution Implemented

### 1. Force IPv4 Connections
Added code to force the exchange to use IPv4:

```python
import socket
import urllib3.util.connection as urllib3_cn

def allowed_gai_family():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = allowed_gai_family
```

### 2. Candle Buffer from Websocket Stream (Better Approach)
Instead of fetching historical data on every signal computation:

- **Buffer candles** from the websocket stream in memory
- **Pre-load** initial candles on startup (if possible)
- **Compute signals** from buffered data instead of API calls
- **Avoids API calls** entirely after initial load

**Benefits:**
- ✅ No repeated API calls
- ✅ Faster signal computation
- ✅ Works even if fetch API has issues
- ✅ More reliable and efficient

## Changes Made

### `main.py`
1. Added IPv4 forcing in `build_exchange()`
2. Created `candle_buffer` list to store OHLCV data
3. Pre-load initial candles on startup
4. Collect candles from websocket into buffer
5. Pass buffered candles to `compute_signal()`

### `strategy.py`
1. Added optional `candle_data` parameter to `compute_signal()`
2. Use provided candle data if available, otherwise fetch from exchange

## Testing
Restart your bot:
```bash
python3 main.py
```

You should now see:
1. "Loaded X initial candles" on startup
2. Signals being computed successfully
3. Dashboard `/history` endpoint returning data
4. UI showing candles and signals

## Monitoring
Check these endpoints:
- http://127.0.0.1:8000/state - Should show last_signal and last_trade
- http://127.0.0.1:8000/history - Should show array of candles with signals
- http://127.0.0.1:8000/ui - Should display chart with data

## Future Improvements
Consider adding:
- Retry logic for initial candle fetch
- Persistent candle buffer (save to disk on shutdown)
- Health check to ensure buffer is being updated
- Alert if no candles received for X minutes


