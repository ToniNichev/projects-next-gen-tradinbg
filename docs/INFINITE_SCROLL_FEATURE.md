# 📜 Infinite Scroll Feature - Chart Historical Data Loading

## Overview

The dashboard now supports **infinite scroll** for historical chart data! When you drag or pan the chart back in time, older candles are automatically fetched and loaded seamlessly.

## ✨ Features

### Automatic Historical Data Loading
- **Smart Detection**: Automatically detects when you're within 20% of the left edge of loaded data
- **Seamless Loading**: Fetches 100 additional candles at a time without disrupting your view
- **No Duplicates**: Intelligently filters out duplicate timestamps when merging data
- **Smooth UX**: Loading happens in the background with a subtle indicator

### Supported Triggers
The infinite scroll activates when you navigate left using:
- 🖱️ **Drag**: Click and drag the chart to the left
- ⌨️ **Keyboard**: Press and hold the left arrow key
- 🖱️ **Shift + Mouse Wheel**: Scroll horizontally to the left
- 🔘 **Pan Button**: Click the "◀ Left" button

### Visual Feedback
- **Loading Indicator**: Shows "Loading historical data..." when fetching
- **Candle Counter**: Displays total number of candles loaded (e.g., "456 candles")
- **Status Badge**: Shows current state:
  - 📡 **Live data** - for 1h timeframe (uses real-time streaming)
  - 🔄 **Scroll left for more history** - infinite scroll is active
  - 📊 **All available data loaded** - reached the exchange's data limit

## 🎯 How It Works

### Backend (API)
Updated `/api/candles/<timeframe>` endpoint to accept a `since` parameter:
```python
GET /api/candles/4h?limit=100&since=1704067200000
```
- **timeframe**: 5m, 15m, 30m, 1h, 4h, 1d, 1w
- **limit**: Number of candles (max 500)
- **since**: Unix timestamp in milliseconds (optional)

### Frontend (JavaScript)
1. **Edge Detection**: Monitors pan/zoom position relative to data boundaries
2. **Fetch Logic**: Calculates timestamp for next batch (100 candles back)
3. **Data Merge**: Prepends new candles while avoiding duplicates
4. **View Preservation**: Maintains your current zoom/pan position
5. **Limit Updates**: Extends pan boundaries to include new data

## 🚀 Usage

### Basic Navigation
1. Open the dashboard and select a timeframe (e.g., 4h, 1d)
2. Drag the chart to the left or use keyboard navigation
3. When you approach the left edge, new data loads automatically
4. Continue scrolling left to load progressively older data

### Timeframe Behavior
- **1h (default)**: Uses live streaming data, infinite scroll disabled
- **5m, 15m, 30m, 4h, 1d, 1w**: Infinite scroll enabled, loads historical data

### Performance
- **Batch Size**: 100 candles per fetch (configurable in code)
- **Rate Limit**: 30 requests per minute (Exchange API limit)
- **Max Load**: No hard limit, but browser may slow with 1000+ candles
- **Memory**: Each candle is ~100 bytes, so 1000 candles ≈ 100KB

## 🔧 Technical Details

### Key Variables
```javascript
let isLoadingHistorical = false;  // Prevents duplicate fetches
let hasMoreHistoricalData = true; // Tracks if more data is available
```

### Key Functions
- `loadMoreHistoricalData()` - Fetches and prepends historical candles
- `checkAndLoadHistoricalData()` - Checks if we're near the edge
- `getTimeframeMs(timeframe)` - Converts timeframe string to milliseconds
- `updateChartInfo()` - Updates the candle count and status badge

### Edge Detection Threshold
```javascript
const threshold = dataMin + (dataRange * 0.2);  // 20% from left edge
if (visibleMin <= threshold) {
  loadMoreHistoricalData();
}
```

## 📊 Example Scenarios

### Scenario 1: Day Trader Analysis
- **Timeframe**: 15m
- **Initial Load**: Last 200 candles (≈ 50 hours)
- **Scroll Back**: Load additional weeks of data
- **Use Case**: Compare current price action to previous patterns

### Scenario 2: Swing Trading Setup
- **Timeframe**: 4h
- **Initial Load**: Last 200 candles (≈ 33 days)
- **Scroll Back**: Load several months of data
- **Use Case**: Identify long-term support/resistance levels

### Scenario 3: Long-Term Analysis
- **Timeframe**: 1d
- **Initial Load**: Last 200 candles (≈ 6.5 months)
- **Scroll Back**: Load years of historical data
- **Use Case**: Analyze macro trends and cycles

## ⚠️ Limitations

1. **Exchange Data Availability**: 
   - Binance US typically has 1-2 years of historical data
   - Older data may not be available

2. **Rate Limiting**: 
   - Exchange API has rate limits (30 req/min)
   - Rapid scrolling may temporarily pause loading

3. **Browser Performance**: 
   - Loading 1000+ candles may slow chart rendering
   - Consider using longer timeframes for very old data

4. **1h Timeframe**: 
   - Infinite scroll disabled (uses live streaming)
   - Shows real-time trading signals only

## 🛠️ Troubleshooting

### Data Not Loading?
1. Check browser console for errors (F12 → Console)
2. Verify Binance US API credentials in `.env`
3. Check rate limit status (may need to wait 60 seconds)
4. Try a different timeframe

### Chart Performance Slow?
1. Reset zoom to default view (press '0' or click "Reset")
2. Switch to a longer timeframe (e.g., 1d instead of 5m)
3. Refresh the page to clear loaded data
4. Close other browser tabs to free memory

### Status Shows "All data loaded"?
- This means you've reached the exchange's data limit
- No older data is available from Binance US
- This is normal and expected

## 🎨 UI Customization

### Change Batch Size
In `ui.html`, update the limit parameter:
```javascript
const response = await fetch(
  `/api/candles/${currentTimeframe}?limit=200&since=${fetchFromTime}`  // Change 100 to 200
);
```

### Change Edge Threshold
Adjust when loading triggers:
```javascript
const threshold = dataMin + (dataRange * 0.1);  // 10% instead of 20%
```

### Hide Status Badge
In `ui.html`, comment out or remove:
```html
<span id="infinite-scroll-status">🔄 Infinite scroll active</span>
```

## 📝 Future Enhancements

Potential improvements for future versions:
- [ ] Add a "Jump to Date" calendar picker
- [ ] Cache loaded data in browser localStorage
- [ ] Add progress indicator showing % of available data
- [ ] Support for multiple exchanges
- [ ] Configurable batch size in UI settings
- [ ] Preload data in background during idle time

## 🐛 Known Issues

None currently! 🎉

Report issues with:
- Browser version and OS
- Timeframe being used
- Console error messages
- Steps to reproduce

---

**Version**: 1.0  
**Last Updated**: February 8, 2026  
**Author**: Trading Bot Dashboard Team
