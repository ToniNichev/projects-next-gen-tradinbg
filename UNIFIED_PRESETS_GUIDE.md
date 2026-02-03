# 🎯 Unified Preset System - User Guide

## What Changed?

We've **unified the preset system** for a better, more consistent experience! Previously, there were two separate preset systems that could get out of sync. Now everything is centralized.

### Before (Old System)
```
Strategy Center:  12 database presets ✅
Backtest Page:     4 hardcoded presets ❌

Problems:
- Confusing (which one to use?)
- Out of sync (different values)
- Limited in backtest (only 4 presets)
- Maintenance nightmare (update in 2 places)
```

### After (New Unified System)
```
Strategy Center:  12 database presets ✅
Backtest Page:    Uses Strategy Center presets ✅

Benefits:
- Single source of truth
- All 12 presets available for backtesting
- Consistent values everywhere
- Easy to maintain and update
```

---

## 🚀 How to Use the New System

### **Method 1: One-Click Backtest (Recommended)**

1. Navigate to **Strategy Center** (`/strategy-config`)
2. Browse the **Configuration Presets** section
3. Click any preset card (e.g., "Conservative")
4. Click **"⚡ Apply & Run Backtest"** button
5. Backtest page opens automatically in new tab
6. Wait 30-60 seconds for results
7. Results show a badge with preset name!

**Example:**
```
1. Click "Crypto Bull Market" preset
2. Click "⚡ Apply & Run Backtest"
3. New tab opens showing backtest running
4. Results appear with "🎨 Crypto Bull Market" badge
```

---

### **Method 2: Manual Configuration**

1. Go to **Strategy Center**
2. Select preset from dropdown or grid
3. Click **"✅ Apply Configuration"**
4. Go to **Backtest** page
5. Use **"Current Config"** tab
6. Click **"🚀 Run Backtest with Current Config"**
7. Results use your configured settings

---

## 📊 What You'll See in Backtest Page

### **Presets Tab (Updated)**
The "Presets" tab now shows:
- ✨ Information about the 12 available presets
- 🎯 Direct link to Strategy Center
- ℹ️ Button to view current configuration
- 💡 Pro tips for using presets

**No more hardcoded preset buttons!** Everything goes through Strategy Center now.

### **Current Config Tab (Unchanged)**
Still works the same way:
- Enter custom parameters if you want
- OR leave empty to use database config
- Click "Run Backtest"

---

## 🏷️ Preset Badges in Results

Backtest results now show which preset was used!

**Example Result Card:**
```
┌─────────────────────────────────────────────┐
│ Jan 15, 2026 3:45 PM · 30 days              │
│ 🎨 Conservative (Low Risk)          +8.2%   │
│                                              │
│ Final Value: $1,082.00                      │
│ Total P&L: +$82.00                          │
│ Trades: 12                                  │
└─────────────────────────────────────────────┘
```

Makes it easy to:
- ✅ Know which preset generated each result
- ✅ Compare different presets visually
- ✅ Track which configurations work best

---

## 🎨 Available Presets (All 12)

### **Risk Levels**
1. **Conservative** - Low risk, capital preservation
2. **Night Mode** - Ultra-safe for unmonitored trading
3. **Balanced** - Default, good starting point
4. **Aggressive** - High risk, maximum opportunities

### **Timeframes**
5. **Scalping (5m)** - Fast trades, constant monitoring
6. **Day Trading (1h)** - Check 2-3 times daily
7. **Swing Trading (4h)** - Part-time, bigger moves

### **Specialized Strategies**
8. **Trend Following** - EMA-focused, ride trends
9. **Mean Reversion** - RSI+BB-focused, buy dips
10. **Breakout Hunter** - MACD+Volume-focused, catch momentum

### **Market Conditions**
11. **High Volatility** - Wide stops for wild markets
12. **Low Volatility** - Tight stops for calm markets
13. **Crypto Bull** - Optimized for strong uptrends

---

## 💡 Comparison Workflow

### **Compare Multiple Presets**

```
Goal: Find the best preset for current market conditions

1. Go to Strategy Center
2. Select "Conservative" → Apply & Run Backtest
3. Wait for completion
4. Select "Balanced" → Apply & Run Backtest  
5. Wait for completion
6. Select "Aggressive" → Apply & Run Backtest
7. Wait for completion

8. Go to Backtest page
9. See all 3 results with preset badges:
   - 🎨 Conservative: +5.2%
   - 🎨 Balanced: +8.7%
   - 🎨 Aggressive: +12.1%

10. Select multiple results
11. Click "Compare Selected"
12. Analyze side-by-side
```

---

## 🔍 View Current Configuration

### **From Backtest Page**

Click **"ℹ️ Show Current Config"** in the Presets tab to see:
- Configuration source (Database vs Environment)
- Current risk parameters
- Strategy weights and status
- Number of database parameters loaded

**Example Output:**
```
Configuration Source: Database (45 parameters)

Risk Management:
• Stop Loss: 2.5%
• Take Profit: 4.0%
• Position Size: 25%

Multi-Strategy:
• Aggregation: weighted_voting
• Min Confidence: 30%

Strategy Status:
✓ EMA: Enabled (1.0x)
✓ RSI+BB: Enabled (1.0x)
✓ MACD: Enabled (1.0x)
```

---

## 🔄 Migration from Old System

### **If You Were Using Old Backtest Presets**

The old hardcoded presets (`conservative`, `balanced`, `aggressive`, `scalping`) are **removed**.

**Migration Steps:**

1. **Find Equivalent in Strategy Center:**
   - Old "conservative" → New "Conservative (Low Risk)"
   - Old "balanced" → New "Balanced (Default)"
   - Old "aggressive" → New "Aggressive (High Risk)"
   - Old "scalping" → New "Scalping (5m timeframe)"

2. **Use New Workflow:**
   - Instead of: Backtest page → Presets tab → Click button
   - Now: Strategy Center → Select preset → Apply & Run Backtest

3. **Bonus:** You now have access to **8 more presets**!

---

## 📈 Benefits of Unified System

### **For Users**
✅ Consistent experience across pages  
✅ All 12 presets available for backtesting  
✅ Easy to see which preset was used  
✅ One place to manage all configurations  
✅ Preset names shown in results  

### **For Developers**
✅ Single source of truth (database)  
✅ No code duplication  
✅ Easier to maintain  
✅ Add new presets in one place  
✅ Better tracking and analytics  

---

## 🎓 Tips & Best Practices

### **Tip 1: Label Your Results**
The preset badge makes it easy to:
- Identify which configuration was tested
- Compare apples-to-apples
- Track performance over time

### **Tip 2: Use "Show Current Config"**
Before running a manual backtest, click "Show Current Config" to verify:
- ✅ Configuration source is "Database" not "Environment"
- ✅ Values match what you expect
- ✅ Correct strategies are enabled

### **Tip 3: Systematic Testing**
Test all presets on the same period:
```bash
Days: 30 (keep consistent)
Symbol: BTC/USDT (keep consistent)
Period: Last 30 days (same for all)

Then compare results fairly!
```

### **Tip 4: Create Variations**
1. Load a preset (e.g., "Balanced")
2. Make small tweaks
3. Save as custom preset (e.g., "Balanced v2")
4. Test both
5. Keep the better one

---

## ❓ FAQ

**Q: Where did the preset buttons go in Backtest page?**  
A: They've been moved to Strategy Center for better organization. Use the "Apply & Run Backtest" button there.

**Q: Can I still run backtests without presets?**  
A: Yes! Use the "Current Config" tab and leave parameters empty to use your current configuration.

**Q: How do I know which preset was used?**  
A: Look for the 🎨 badge in the result header showing the preset name.

**Q: Can I still create custom configurations?**  
A: Absolutely! Go to Strategy Center, configure manually, and save as a custom preset.

**Q: What if I want to test a one-off configuration?**  
A: Use the "Current Config" tab and fill in custom parameters - they'll override the database config.

**Q: Are the old preset values preserved?**  
A: Yes! The Strategy Center presets include all the old ones plus 8 new ones with better parameters.

---

## 🚨 Troubleshooting

### **Issue: Backtest shows same results for different presets**

**Solution:**
1. Click "🐛 Debug Config" in Strategy Center
2. Verify source shows "Database (40+ params)"
3. If it shows "Environment", the preset wasn't applied
4. Click "Apply Configuration" again
5. Wait 1-2 seconds before running backtest

### **Issue: Can't find preset buttons in Backtest page**

**Solution:**
- They've been moved to Strategy Center!
- Click the link in the Presets tab to go there
- Use "Apply & Run Backtest" button

### **Issue: Want to use old preset workflow**

**Solution:**
The old workflow is deprecated, but you can:
1. Go to Strategy Center
2. The 4 original presets are still there
3. Use "Apply & Run Backtest" (even easier!)

---

## 📞 Support

Having issues with the new system?

1. Click "Show Current Config" in Backtest page
2. Click "Debug Config" in Strategy Center
3. Compare the values shown
4. Check if preset badge appears in results
5. Verify database has 40+ parameters

Still stuck? Check `PRESET_BACKTEST_GUIDE.md` for detailed troubleshooting.

---

## 🎉 Summary

**Before:** Two separate preset systems, 4 presets in backtest, confusing  
**After:** One unified system, 12 presets available, clear preset badges

**New Workflow:**
```
Strategy Center → Select Preset → Apply & Run Backtest → See Results with Badge
```

**Result:** Simpler, more powerful, easier to compare!

---

**Happy Testing! 📊**
