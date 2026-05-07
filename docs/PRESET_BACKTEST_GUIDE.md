# How to Backtest with Presets - Complete Guide

## 🎯 Quick Start (Recommended Method)

### Method 1: Use "Apply & Run Backtest" Button

1. Navigate to **Strategy Center** → **Configuration Presets**
2. Click any preset card to select it
3. Click the **"⚡ Apply & Run Backtest"** button
4. Wait for backtest to complete (30-60 seconds)
5. View results in the Backtest page

✅ This method automatically applies the preset AND runs the backtest with the correct configuration.

---

### Method 2: Manual Apply Then Backtest

1. **Step 1: Select and Apply Preset**
   - Go to Strategy Center
   - Select a preset from dropdown or grid
   - Click **"✅ Apply Configuration"**
   - Wait for success message

2. **Step 2: Verify Configuration**
   - Click **"🐛 Debug Config"** button
   - Verify the configuration shows your preset values
   - Check "Source: Database (X params)"

3. **Step 3: Run Backtest**
   - Go to Backtest page
   - Click **"🚀 Run Backtest with Current Config"**
   - Do NOT fill in any custom parameters
   - Wait for results

---

## 🐛 Troubleshooting: "Different Presets Show Same Results"

### Issue
When you load different presets and run backtests, the results are identical, suggesting the preset isn't being applied.

### Root Cause
The backtest might not be reading the updated database configuration. This can happen if:
1. Preset was not applied before backtest
2. Database wasn't flushed before backtest started
3. Backtest is reading from .env file instead of database

### Solution

**Option A: Use Built-in Button**
- Use the **"⚡ Apply & Run Backtest"** button in the preset section
- This ensures proper timing and configuration

**Option B: Manual with Verification**
1. Load preset → Click "Apply Configuration"
2. **Wait 1-2 seconds**
3. Click "Debug Config" to verify it was applied
4. Then run backtest

**Option C: Restart Bot Between Presets**
```bash
# Apply preset in UI
./restart.sh
# Then run backtest
```

---

## 🔍 Verify Configuration is Applied

### Check #1: Debug Config Button

Click the **"🐛 Debug Config"** button to see:
- **Source**: Should say "Database (40+ params)" not "Environment"
- **Stop Loss**: Should match your preset
- **Strategy Weights**: Should match your preset
- **Aggregation Mode**: Should match your preset

Example output:
```
Source: Database (45 params)  ✅ Good

Risk Management:
• Stop Loss: 1.5%              ← Should match preset
• Take Profit: 3.0%            ← Should match preset
• Position Size: 15%           ← Should match preset

Multi-Strategy:
• Aggregation: unanimous       ← Should match preset
• Min Confidence: 50%          ← Should match preset
```

### Check #2: Backtest Logs

When backtest runs, check the logs (dashboard.log or console) for:
```
CONFIGURATION SOURCE: DATABASE  ← Should say DATABASE, not ENVIRONMENT
Stop Loss: 1.5%                 ← Should match your preset
Take Profit: 3.0%               ← Should match your preset
Aggregation Mode: unanimous     ← Should match your preset
```

---

## 📊 Comparing Presets Correctly

### Method 1: Sequential Testing

```
1. Load "Conservative" preset
2. Click "Apply & Run Backtest"
3. Wait for completion
4. Note results

5. Load "Aggressive" preset  
6. Click "Apply & Run Backtest"
7. Wait for completion
8. Compare results in Backtest page
```

### Method 2: Using Backtest Comparison

1. Run backtest with Preset A
2. Run backtest with Preset B
3. Run backtest with Preset C
4. Go to Backtest page
5. Select multiple results
6. Click "Compare Selected"

---

## ⚠️ Common Mistakes

### ❌ Mistake #1: Not Applying Before Backtest
```
Load preset → Run backtest immediately
```
**Problem**: Preset loaded in UI but not saved to database

**Fix**: Always click "Apply Configuration" first!

### ❌ Mistake #2: Filling Custom Parameters
```
Load preset → Go to backtest page → Fill in custom stop loss → Run
```
**Problem**: Custom parameters override preset configuration

**Fix**: Leave backtest form empty to use preset config

### ❌ Mistake #3: Not Waiting for Database
```
Apply Configuration → Immediately run backtest (< 1 second)
```
**Problem**: Database might not be flushed yet

**Fix**: Wait 1-2 seconds or use "Apply & Run Backtest" button

### ❌ Mistake #4: Comparing Old Results
```
Run backtest with Preset A (yesterday)
Load Preset B today
Compare with yesterday's results
```
**Problem**: Old results used old configuration

**Fix**: Delete old results and re-run all presets fresh

---

## ✅ Best Practices

### 1. Clear Old Results
Before comparing presets:
```
Backtest page → Clear Results → Start fresh
```

### 2. Use Consistent Parameters
Keep these the same across all preset tests:
- Days back (30 days recommended)
- Symbol (BTC/USDT)
- No custom parameter overrides

### 3. Document Your Tests
Create a comparison table:
```
| Preset       | Win Rate | Total Return | Max DD | Sharpe |
|--------------|----------|--------------|--------|--------|
| Conservative | 62%      | +8.2%        | -3.1%  | 1.8    |
| Balanced     | 54%      | +12.5%       | -5.2%  | 1.5    |
| Aggressive   | 48%      | +18.3%       | -8.7%  | 1.3    |
```

### 4. Test Different Market Conditions
- Bull market period (price going up)
- Bear market period (price going down)
- Sideways period (consolidation)

Example:
```
Conservative preset:
- Last 30 days (mixed): +5%
- Last 90 days (bull): +12%
- Jan 2024 (bear): -2%
```

---

## 🎓 Advanced Tips

### Tip #1: Create Test Variations
```
1. Start with "Balanced" preset
2. Save as "Balanced v1"
3. Adjust stop loss from 2.5% → 3%
4. Save as "Balanced v2"
5. Backtest both
6. Compare which works better
```

### Tip #2: Seasonal Testing
```
Test presets across different periods:
- Volatile period: Use "High Volatility" preset
- Calm period: Use "Low Volatility" preset
- Bull market: Use "Crypto Bull" preset
```

### Tip #3: Strategy Isolation
```
Want to test just EMA strategy?
1. Load any preset
2. Disable RSI+BB and MACD in Strategy Overview
3. Apply configuration
4. Run backtest
5. Only EMA signals will be used
```

---

## 📈 Example Workflow

### Full Preset Comparison Workflow

```bash
# Day 1: Test Conservative Presets
1. Load "Conservative" → Apply & Run Backtest → Note results
2. Load "Night Mode" → Apply & Run Backtest → Note results
3. Compare in Backtest page

# Day 2: Test Aggressive Presets  
1. Clear old results
2. Load "Aggressive" → Apply & Run Backtest
3. Load "Crypto Bull" → Apply & Run Backtest
4. Load "Breakout Hunter" → Apply & Run Backtest
5. Compare all three

# Day 3: Test Timeframe Presets
1. Load "Scalping 5m" → Apply Configuration
2. IMPORTANT: Restart bot (timeframe change)
3. Run backtest
4. Load "Day Trading 1h" → Apply → Restart → Backtest
5. Load "Swing 4h" → Apply → Restart → Backtest
6. Compare

# Day 4: Test Specialized
1. Load "Trend Following" → Apply & Run Backtest
2. Load "Mean Reversion" → Apply & Run Backtest  
3. Compare to see which suits current market
```

---

## 🚨 If Presets Still Don't Work

### Last Resort Checklist

1. **Verify Database Exists**
   ```bash
   ls -la data/trading.db
   # Should show the file exists
   ```

2. **Check Database Has Configs**
   - Click "Debug Config" button
   - Should show "Database (40+ params)"
   - If it shows "Environment", database isn't being used

3. **Manually Check Database**
   ```bash
   sqlite3 data/trading.db "SELECT COUNT(*) FROM strategy_config;"
   # Should show 40-50 rows
   ```

4. **Re-run Migration**
   ```bash
   python3 migrate_add_presets.py
   ```

5. **Hard Reset**
   ```bash
   # Backup your data first!
   mv data/trading.db data/trading.db.backup
   ./restart.sh
   # Re-apply your preset
   ```

6. **Check Logs**
   ```bash
   tail -f dashboard.log
   # Look for "CONFIGURATION SOURCE: DATABASE"
   ```

---

## 📞 Support

If you've tried everything and presets still don't work:

1. Click "Debug Config" and take a screenshot
2. Run a backtest and save the logs
3. Check if `data/trading.db` exists
4. Check database contents:
   ```bash
   sqlite3 data/trading.db "SELECT key, value FROM strategy_config LIMIT 10;"
   ```
5. Post issue with all the above information

---

## 🎉 Success Indicators

You'll know presets are working correctly when:

✅ Different presets show different backtest results  
✅ "Debug Config" shows "Source: Database"  
✅ Backtest logs show "CONFIGURATION SOURCE: DATABASE"  
✅ Conservative preset has fewer trades than Aggressive  
✅ Stop loss values in backtest logs match preset values  

---

**Happy Testing! 📊**
