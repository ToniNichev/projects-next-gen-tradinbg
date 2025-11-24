# 🚀 Quick Start: Interactive Dashboard

## Start the Dashboard

```bash
python3 main.py
```

The dashboard will automatically start on **http://localhost:8000**

## Access the Features

Open your browser and visit:

### 📊 Live Dashboard
**http://localhost:8000/ui**
- Real-time price chart with candlesticks
- Buy/sell signal indicators
- Current balance and trade status
- Zoomable, pannable chart

### ⚙️ Settings & Configuration
**http://localhost:8000/settings**
- Adjust all trading parameters through web UI
- Configure EMA periods, stop losses, position sizing
- Enable/disable filters and confirmations
- Changes apply to backtests (restart bot to apply to live trading)

### 🔬 Backtest Runner
**http://localhost:8000/backtest**
- Run backtests with custom parameters
- Test multiple configurations (7-90 days of history)
- Compare results side-by-side
- Try preset strategies: Conservative, Balanced, Aggressive, Scalping

## Features Overview

### 1. Run a Quick Backtest
1. Go to http://localhost:8000/backtest
2. Select "30 days" history
3. Click "Run Backtest"
4. Wait 30-60 seconds for results
5. View P&L, win rate, trades executed

### 2. Compare Different Strategies
1. Run "Conservative" preset
2. Run "Aggressive" preset
3. Select both results (click on cards)
4. Click "Compare Selected"
5. See which performs better

### 3. Optimize Parameters
1. Go to http://localhost:8000/backtest
2. Switch to "Custom Parameters" tab
3. Try different combinations:
   - Stop Loss: 1.5%, 2.5%, 3.5%
   - Position Size: 15%, 25%, 35%
   - EMA: (8,21), (12,26), (20,50)
4. Compare results to find optimal settings

### 4. Apply Best Configuration
1. Go to http://localhost:8000/settings
2. Set parameters from best backtest
3. Click "Save Configuration"
4. Restart bot to apply changes

## Navigation

All pages include a top navigation bar:
- **Dashboard** - Live monitoring
- **Settings** - Configure parameters
- **Backtest** - Historical testing
- **API** - JSON endpoints

## API Access

Query data programmatically:

```bash
# Get current config
curl http://localhost:8000/api/config

# Get trading stats
curl http://localhost:8000/api/stats

# Get recent trades
curl http://localhost:8000/api/trades?limit=50

# Run backtest via API
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"days_back": 30, "stop_loss_pct": 0.03}'
```

## Troubleshooting

### Dashboard not loading?
- Check bot is running: `ps aux | grep python3 | grep main.py`
- Verify port 8000 is free: `lsof -i :8000`
- Check logs for errors in terminal

### Backtest stuck?
- Only one backtest runs at a time
- Refresh page to see updated status
- Large backtests (90+ days) take 2-3 minutes

### Settings not saving?
- Settings apply to backtests automatically
- For live trading: restart bot after changing settings
- Or use environment variables in `.env` file

## Read the Full Guide

For detailed instructions, see **DASHBOARD_GUIDE.md**

---

**Ready to start?** Run `python3 main.py` and open http://localhost:8000/ui









