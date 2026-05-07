# Strategy Enable/Disable Guide

## 🎛️ Three Ways to Control Strategies

### **Method 1: Dynamic Toggle (Recommended) ⚡**

**Via Dashboard UI (No Restart Required!)**

1. Go to: `http://localhost:8000/strategies`
2. Find the strategy card
3. Click the **Enable** or **Disable** button
4. ✅ Done! Changes apply immediately

**Features:**
- ✅ Instant effect (no restart)
- ✅ One-click toggle
- ✅ Visual feedback
- ✅ Prevents disabling all strategies
- ⚠️ Changes don't persist across bot restarts

**Best for:** Testing, temporary adjustments, market condition changes

---

### **Method 2: API Endpoints ⚡**

**Via Command Line (No Restart Required!)**

#### Enable a Strategy
```bash
curl -X POST -u admin:password \
  http://localhost:8000/api/strategies/EMA_Crossover/enable
```

#### Disable a Strategy
```bash
curl -X POST -u admin:password \
  http://localhost:8000/api/strategies/RSI_BB_MeanReversion/disable
```

#### Toggle (Enable ↔ Disable)
```bash
curl -X POST -u admin:password \
  http://localhost:8000/api/strategies/EMA_Crossover/toggle
```

**Response:**
```json
{
  "success": true,
  "message": "Strategy 'EMA_Crossover' enabled",
  "strategy": "EMA_Crossover",
  "enabled": true
}
```

**Features:**
- ✅ Instant effect
- ✅ Scriptable/Automatable
- ✅ Can be scheduled (cron jobs)
- ⚠️ Changes don't persist across bot restarts

**Best for:** Automation, scripts, scheduled strategy switching

---

### **Method 3: Configuration File 📝**

**Via .env File (Persists Across Restarts)**

Edit your `.env` file:

```bash
# Enable/Disable EMA Crossover Strategy
BOT_STRATEGY_EMA_ENABLED=true    # Set to false to disable
BOT_STRATEGY_EMA_WEIGHT=1.0

# Enable/Disable RSI + Bollinger Bands Strategy
BOT_STRATEGY_RSI_BB_ENABLED=true    # Set to false to disable
BOT_STRATEGY_RSI_BB_WEIGHT=1.0
```

**Apply changes:**
```bash
./restart.sh
```

**Features:**
- ✅ Persists across restarts
- ✅ Single source of truth
- ✅ Version controllable
- ⚠️ Requires bot restart

**Best for:** Permanent configuration, production settings

---

## 🎯 Decision Matrix

| Scenario | Best Method | Why |
|----------|-------------|-----|
| Testing different strategies | Method 1 (UI) | Quick, visual, no restart |
| Market just became trending | Method 1 (UI) | Enable EMA, disable RSI+BB instantly |
| Market just became ranging | Method 1 (UI) | Enable RSI+BB, disable EMA instantly |
| Automated strategy switching | Method 2 (API) | Can be scripted |
| Schedule strategy by time | Method 2 (API) | Cron job compatible |
| Production deployment | Method 3 (.env) | Persists, documented |
| Setting defaults | Method 3 (.env) | Survives restarts |

---

## 📊 Use Cases

### **Use Case 1: Testing a Strategy**

**Problem:** Want to test RSI+BB strategy alone for a few hours

**Solution (Method 1 - UI):**
1. Go to `/strategies`
2. Click **Disable** on EMA_Crossover
3. Monitor for a few hours
4. Click **Enable** to turn it back on

**Time:** 5 seconds, no restart needed ✅

---

### **Use Case 2: Market Condition Changed**

**Problem:** BTC just started a strong trend, want to disable mean reversion

**Solution (Method 1 - UI or Method 2 - API):**

**Via UI:**
- Click **Disable** on RSI_BB_MeanReversion

**Via CLI:**
```bash
curl -X POST -u admin:password \
  http://localhost:8000/api/strategies/RSI_BB_MeanReversion/disable
```

**Effect:** EMA strategy now runs alone, perfect for trending markets

---

### **Use Case 3: Scheduled Strategy Switching**

**Problem:** Want EMA active during day, RSI+BB active at night (higher volatility)

**Solution (Method 2 - API + Cron):**

Create script `switch_to_ema.sh`:
```bash
#!/bin/bash
curl -X POST -u admin:password http://localhost:8000/api/strategies/EMA_Crossover/enable
curl -X POST -u admin:password http://localhost:8000/api/strategies/RSI_BB_MeanReversion/disable
```

Create script `switch_to_rsi.sh`:
```bash
#!/bin/bash
curl -X POST -u admin:password http://localhost:8000/api/strategies/EMA_Crossover/disable
curl -X POST -u admin:password http://localhost:8000/api/strategies/RSI_BB_MeanReversion/enable
```

Add to crontab:
```bash
# Switch to EMA at 9 AM
0 9 * * * cd /path/to/bot && ./switch_to_ema.sh

# Switch to RSI+BB at 9 PM
0 21 * * * cd /path/to/bot && ./switch_to_rsi.sh
```

---

### **Use Case 4: Production Configuration**

**Problem:** Setting up production deployment with both strategies

**Solution (Method 3 - .env):**

```bash
# Edit .env
BOT_USE_MULTI_STRATEGY=true
BOT_STRATEGY_AGGREGATION_MODE=weighted_voting

# Enable both with weights
BOT_STRATEGY_EMA_ENABLED=true
BOT_STRATEGY_EMA_WEIGHT=1.2      # Favor trends

BOT_STRATEGY_RSI_BB_ENABLED=true
BOT_STRATEGY_RSI_BB_WEIGHT=1.0

# Deploy
./deploy.sh
./start.sh
```

**Why .env:** Configuration is documented, versioned, survives restarts

---

## ⚠️ Important Notes

### **Safety Features**

1. **Cannot Disable All Strategies**
   - The system prevents disabling the last active strategy
   - At least one strategy must always be enabled
   - Error message: "Cannot disable the last active strategy"

2. **Changes via UI/API Don't Persist**
   - If bot restarts, it reads from `.env` again
   - Dynamic changes are runtime-only
   - To make permanent: update `.env` file

3. **Rate Limited**
   - Toggle endpoints: 10 requests/minute
   - Prevents accidental rapid toggling

---

## 🔍 Check Current Status

### **Via Dashboard:**
```
http://localhost:8000/strategies
```
Shows status badges (Enabled/Disabled) for each strategy

### **Via API:**
```bash
curl -u admin:password http://localhost:8000/api/strategies | jq
```

**Output:**
```json
{
  "multi_strategy_enabled": true,
  "strategies": [
    {
      "name": "EMA_Crossover",
      "enabled": true,
      "weight": 1.0
    },
    {
      "name": "RSI_BB_MeanReversion",
      "enabled": true,
      "weight": 1.0
    }
  ]
}
```

### **Via Logs:**
```bash
tail -f logs/bot.log | grep "Strategy"
```

Look for:
```
Strategy 'EMA_Crossover' enabled
Strategy 'RSI_BB_MeanReversion' disabled
```

---

## 💡 Best Practices

### **1. Test Before Production**
- Use Method 1 (UI toggle) to test in paper trading
- Once validated, update `.env` (Method 3)

### **2. Monitor Performance**
- Check `/strategies` page after toggling
- Verify acceptance rates change as expected
- Monitor trade quality

### **3. Document Changes**
- If you toggle via UI/API, document why
- Update `.env` file to reflect production state
- Keep changelog of strategy adjustments

### **4. Market Adaptation**
```bash
# Trending market detected
curl -X POST http://localhost:8000/api/strategies/RSI_BB_MeanReversion/disable

# Ranging market detected
curl -X POST http://localhost:8000/api/strategies/EMA_Crossover/disable
```

### **5. A/B Testing**
- Run EMA alone for 1 week → measure results
- Run RSI+BB alone for 1 week → measure results
- Run both together for 1 week → compare
- Use best configuration

---

## 🐛 Troubleshooting

### **Problem: Button doesn't work**
**Solution:**
- Check browser console for errors
- Verify bot is running: `./status.sh`
- Check authentication: refresh login
- Verify multi-strategy is enabled

### **Problem: Strategy re-enables after restart**
**Solution:**
- This is expected! UI/API changes are runtime-only
- To persist: edit `.env` file and set to `false`

### **Problem: "Cannot disable last strategy" error**
**Solution:**
- At least one strategy must be enabled
- Enable another strategy first
- Or disable multi-strategy entirely

### **Problem: Changes don't take effect**
**Solution:**
- Wait 1-2 candles for next signal computation
- Check logs: `tail -f logs/bot.log`
- Verify strategy is actually disabled: `/api/strategies`

---

## 📚 Summary

| Method | Speed | Persists | Best For |
|--------|-------|----------|----------|
| **UI Toggle** | Instant | ❌ No | Testing, quick changes |
| **API Toggle** | Instant | ❌ No | Automation, scripts |
| **.env Config** | Restart required | ✅ Yes | Production, defaults |

**Recommended Workflow:**
1. Test with UI toggle (Method 1)
2. Validate results
3. Update `.env` to persist (Method 3)
4. Automate with API if needed (Method 2)

---

## 🎯 Quick Commands

```bash
# Check status
curl -u admin:password http://localhost:8000/api/strategies

# Enable EMA
curl -X POST -u admin:password \
  http://localhost:8000/api/strategies/EMA_Crossover/enable

# Disable RSI+BB
curl -X POST -u admin:password \
  http://localhost:8000/api/strategies/RSI_BB_MeanReversion/disable

# Toggle (works either way)
curl -X POST -u admin:password \
  http://localhost:8000/api/strategies/EMA_Crossover/toggle

# View performance
curl -u admin:password http://localhost:8000/api/strategies/stats
```

---

**Need help?** Check the main guides:
- **MULTI_STRATEGY_GUIDE.md** - Complete documentation
- **MULTI_STRATEGY_QUICKREF.md** - Quick reference

**Happy strategy switching! 🎛️📊**
