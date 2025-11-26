# Portfolio History Chart Fix

## Problem Fixed

The dashboard's portfolio value chart was **incorrectly displaying historical portfolio values** by using current balances to recalculate past portfolio values. This made the chart misleading - it showed "what if I held my current positions at past prices" instead of "how my portfolio actually performed over time."

## Solution Implemented

### 1. New API Endpoint: `/api/portfolio/history`

**File: `dashboard.py`**

Added a new REST API endpoint that reconstructs actual portfolio history from the trades database:

```python
@app.route("/api/portfolio/history")
@require_auth
@limiter.limit("30 per minute")
def get_portfolio_history():
    """Get historical portfolio values from trade history"""
    # Fetches trades from database
    # Rebuilds portfolio timeline from actual trade data
    # Returns chronological portfolio values
```

**Features:**
- Pulls real trade data from the database
- Calculates actual portfolio value at each trade point
- Returns chronological history (oldest to newest)
- Supports pagination with `limit` parameter (default 500, max 1000)
- Includes balance breakdown (USDT + BTC) for each point

**Response format:**
```json
{
  "history": [
    {
      "timestamp": "2025-11-25T21:37:04.265000",
      "value": 999.85,
      "price": 87985.31,
      "usdt_balance": 799.85,
      "base_balance": 0.002273
    },
    ...
  ],
  "count": 25
}
```

### 2. Updated Dashboard Chart

**File: `templates/ui.html`**

Modified the chart refresh logic to fetch real portfolio history:

**Before (incorrect):**
```javascript
// Used current balances for ALL historical points
const portfolioHistory = history.map((row) => {
  const portfolioValue = state.balances.USDT + (state.balances.BASE * price);
  return { x: timestamp, y: portfolioValue };
});
```

**After (correct):**
```javascript
// Fetches actual portfolio history from trades database
const portfolioResp = await fetch('/api/portfolio/history?limit=500');
const portfolioData = await portfolioResp.json();
const portfolioHistory = portfolioData.history.map(p => ({
  x: new Date(p.timestamp).getTime(),
  y: p.value
}));
```

**Fallback behavior:**
- If no trades have been executed yet (new bot), falls back to the old calculation
- If the API fails, falls back gracefully
- Console logs indicate which data source is being used

## Benefits

✅ **Accurate Performance Tracking**: Chart now shows true portfolio evolution
✅ **Trade-by-Trade Progression**: Each trade creates a portfolio snapshot
✅ **Matches Backtest Chart**: Same calculation method as backtest results
✅ **Historical Analysis**: Can see actual gains/losses over time
✅ **Database-Driven**: Uses existing trade database, no extra storage needed

## Comparison: Before vs After

### Before (Incorrect)
```
Time    Price    Chart Shows
10:00   $100     $1000  (current 10 BTC × $100)
11:00   $110     $1100  (current 10 BTC × $110)  ← Wrong!
12:00   $120     $1200  (current 10 BTC × $120)  ← Wrong!
```
This shows a simple price tracking line, not actual portfolio performance.

### After (Correct)
```
Time    Price    Chart Shows       Actual Holdings
10:00   $100     $1000  (10 BTC)   10 BTC
11:00   $110     $1100  (10 BTC)   10 BTC (held)
11:30   $115     $575   (5 BTC)    5 BTC (sold 5)
12:00   $120     $600   (5 BTC)    5 BTC (held)
```
This shows actual portfolio value changes based on real trading activity.

## Testing

### Automated Test

Run the included test script:
```bash
python3 test_portfolio_history.py
```

This will:
1. Test the API endpoint
2. Show sample portfolio history data
3. Verify dashboard is accessible
4. Provide clear pass/fail results

### Manual Testing

1. **Restart the bot** to load the new code:
   ```bash
   # Stop current bot (Ctrl+C in terminal)
   python3 main.py
   ```

2. **Open the dashboard**:
   ```
   http://localhost:8000/ui
   ```

3. **Look at the portfolio chart**:
   - The gold "Portfolio Value" line should now show step changes at trade points
   - Before trades: Line will be flat or follow price (if no trades yet)
   - After trades: Line will show actual gains/losses

4. **Verify with API**:
   ```bash
   curl -u admin:changeme http://localhost:8000/api/portfolio/history
   ```

### What to Expect

**If no trades executed yet:**
- Chart will use the fallback calculation (current balances)
- Console will log: "No trade history available, using current balance calculation"
- This is normal for a new bot

**After trades are executed:**
- Chart will show actual trade-by-trade portfolio progression
- Console will log: "Loaded N portfolio history points from trades"
- The line will have steps/jumps at trade execution times
- Matches the backtest chart behavior

## Files Modified

1. **`dashboard.py`** - Added `/api/portfolio/history` endpoint
2. **`templates/ui.html`** - Updated chart data fetching logic
3. **`test_portfolio_history.py`** - New test script (optional)

## Compatibility

✅ Backward compatible - no breaking changes
✅ Graceful fallback if database unavailable
✅ Works with existing trade history
✅ No migration needed

## Future Enhancements (Optional)

Consider these improvements later:

1. **Cache portfolio history** - Reduce database queries
2. **Add portfolio snapshots on schedule** - Not just on trades
3. **Include performance metrics** - Max drawdown, Sharpe ratio on chart
4. **Export portfolio history** - CSV/JSON download option

## Troubleshooting

**Chart still shows old behavior:**
- Restart the bot to load new dashboard code
- Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
- Check browser console for errors

**API returns empty history:**
- Normal if no trades executed yet
- Execute a manual trade to test
- Run a backtest to generate test data

**Authentication errors:**
- Update credentials in test script
- Check DASHBOARD_PASSWORD environment variable

---

**Fix completed:** November 26, 2025
**Status:** ✅ Ready for testing


