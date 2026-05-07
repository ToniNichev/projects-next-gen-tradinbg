# Chart Not Showing - Debug Guide

## Issue
After the chart flattening fix, the chart may not display if the exchange API is unavailable.

## Root Cause
The fix changed the chart to fetch real market data from `/api/candles/{timeframe}` instead of internal history. If the exchange connection isn't available (e.g., dashboard started without the bot running), the chart will have no data to display.

---

## Quick Fix

### Option 1: Start the Bot First
The chart needs the exchange connection to fetch candle data. Make sure the bot is running:

```bash
# Start the main bot
python main.py
```

Then the dashboard will be able to fetch candle data from Binance.

### Option 2: Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for errors like:
   - "Error fetching candles: ..."
   - "Falling back to /history endpoint"
   - "No chart data available"

---

## What the Fix Does

The chart now has **smart fallback logic**:

1. **Primary**: Try to fetch from `/api/candles/{timeframe}` (real market data)
2. **Fallback**: If that fails, try `/history` endpoint (bot signal history)
3. **Last Resort**: Show empty chart with "No Data" message

---

## Debugging Steps

### 1. Check if Dashboard is Running
```bash
# You should see:
# * Running on http://0.0.0.0:8000
```

### 2. Check API Endpoint Manually
```bash
# Test candles endpoint
curl http://localhost:8000/api/candles/1h?limit=10

# Should return JSON with candles array
# If error, check if bot is running and exchange is configured
```

### 3. Check Bot Configuration
Make sure your `config.py` or `.env` has:
```env
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
```

### 4. Check Exchange Connection
In the bot logs, look for:
```
Exchange connected successfully
Fetching candles for BTC/USDT (1h)
```

---

## Error Messages and Solutions

### "Error fetching candles: Invalid API Key"
**Solution**: Check your Binance API credentials in `.env` or `config.py`

### "Error fetching candles: Network error"
**Solution**: Check internet connection and Binance API status

### "Falling back to /history endpoint"
**Info**: This is normal if bot hasn't started yet. The chart will show historical signal data instead of real candles.

### "No chart data available"
**Solution**: 
1. Start the bot (`python main.py`)
2. Wait 15 seconds for first data fetch
3. Refresh the browser

### Chart shows "BTC/USDT (1h) - No Data"
**Solution**: No data available from either endpoint. Check:
1. Is the bot running?
2. Has the bot made any trades yet?
3. Is there network connectivity?

---

## Temporary Workaround

If you just want to see the dashboard without the bot running, you can temporarily revert to using internal history:

### Edit `templates/ui.html` line ~1526:

**Current (uses exchange data):**
```javascript
const resp = await fetch(`/api/candles/${currentTimeframe}?limit=200`);
```

**Workaround (uses internal history for 1h only):**
```javascript
if (currentTimeframe === '1h') {
  const resp = await fetch("/history");
  const body = await resp.json();
  history = body.history || [];
} else {
  const resp = await fetch(`/api/candles/${currentTimeframe}?limit=200`);
  // ... rest of code
}
```

⚠️ **Note**: This workaround will bring back the flat candle issue for manual trades.

---

## Proper Workflow

For best results, always start in this order:

1. **Start the bot**
   ```bash
   python main.py
   ```
   
2. **Wait for initialization**
   - Exchange connects
   - First candle fetch completes
   - Initial signals generated
   
3. **Open dashboard**
   - Navigate to http://localhost:8000
   - Chart should show real-time market data
   - Trade markers will appear as trades execute

---

## Verifying It Works

Once everything is running correctly, you should see:

✅ **Chart displays candlesticks** with varying OHLC values  
✅ **Trade markers** (circles) appear on the chart  
✅ **Signal markers** (triangles) appear on 1h chart  
✅ **Balance updates** in the top cards  
✅ **No console errors** in browser DevTools  

---

## Still Not Working?

If chart still doesn't show after following these steps:

1. **Check bot logs** for errors
2. **Clear browser cache** (Ctrl+Shift+Delete)
3. **Check browser console** for JavaScript errors
4. **Restart both bot and dashboard**
5. **Check Binance API status**: https://www.binance.com/en/support/announcement

---

## Alternative: Use Paper Trading Mode

If you want to test without exchange connection:

1. Set environment variable:
   ```bash
   export PAPER_TRADING=true
   ```

2. The bot will simulate trades without real exchange
3. Chart will use simulated data

---

## Need More Help?

If issues persist:
1. Share the error from browser console
2. Share relevant bot logs
3. Confirm bot startup sequence completed successfully
4. Check if `/api/candles/1h` returns data when bot is running
