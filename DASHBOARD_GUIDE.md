# Interactive Dashboard Guide

## Overview

The enhanced dashboard provides a web-based interface for:
- **Monitoring** live trading activity
- **Tweaking** algorithm parameters
- **Running** backtests with different configurations
- **Comparing** backtest results side-by-side

## Getting Started

### 1. Start the Bot

```bash
python3 main.py
```

The dashboard will automatically start on `http://localhost:8000`

### 2. Access the Dashboard

Open your browser and navigate to:
- **Dashboard**: http://localhost:8000/ui
- **Settings**: http://localhost:8000/settings
- **Backtest**: http://localhost:8000/backtest

## Dashboard Features

### 📊 Live Dashboard (`/ui`)

**What you'll see:**
- Real-time candlestick chart with buy/sell signals
- Current signal status (bullish/bearish/neutral)
- Latest trade information
- Current balance (USDT + BTC)

**Features:**
- **Zoom/Pan**: Use mouse wheel to zoom, drag to pan
- **Auto-refresh**: Updates every 15 seconds
- **250 candle history**: Displays last 250 candles

**Chart Controls:**
- **Reset Zoom**: Returns to default view
- **Zoom In/Out**: Manual zoom controls
- **Click & Drag**: Pan across time

---

### ⚙️ Settings Page (`/settings`)

Configure all trading parameters through a user-friendly interface.

#### Trading Parameters
- **Symbol**: Choose trading pair (BTC/USDT, ETH/USDT, etc.)
- **Timeframe**: Select candle interval (5m, 15m, 1h, 4h, 1d)
- **Initial Capital**: Starting USDT amount for backtests

#### Strategy Indicators
- **Short/Long EMA**: Moving average periods (default: 12/26)
- **RSI Period**: RSI calculation period (default: 14)
- **RSI Levels**: Oversold/Overbought thresholds (default: 25/75)
- **ATR Period**: ATR calculation period (default: 14)
- **Min Trend Strength**: Minimum EMA separation (default: 0.00005)

#### Risk Management
- **Stop Loss %**: Exit level for losing trades (default: 2.5%)
- **Take Profit %**: Exit level for winning trades (default: 4%)
- **Trailing Stop %**: Dynamic stop that follows price (default: 1.5%)
- **ATR Stop Multiplier**: Stop distance in ATR units (default: 2.5x)
- **Toggles**: Enable/disable trailing stops and ATR-based stops

#### Position Sizing
- **Min/Max Position Size**: Range for dynamic sizing (default: 15-35%)
- **Dynamic Sizing**: Enable intelligent position sizing based on signal strength

#### Signal Filters
- **Volume Threshold**: Required volume multiplier (default: 1.1 = 110%)
- **Volume Confirmation**: Require above-average volume
- **MACD Confirmation**: Require MACD momentum confirmation

**Usage:**
1. Adjust parameters as desired
2. Click **Save Configuration**
3. Changes apply to future backtests
4. To apply to live trading: restart the bot

---

### 🔬 Backtest Runner (`/backtest`)

Run historical simulations with different parameter configurations.

#### Quick Backtest

**Use Current Config**
- Runs backtest with current bot configuration
- Select days of history (7, 14, 30, 60, or 90 days)
- Click "Run Backtest"

**Custom Parameters**
- Override specific parameters:
  - Position Size %
  - Stop Loss %
  - Take Profit %
  - Short/Long EMA
  - ATR Multiplier
- Runs with custom settings while keeping other params default

**Presets**
Four pre-configured strategies:

1. **🛡️ Conservative**
   - Small position sizes (10-20%)
   - Wide stops (3% / 3x ATR)
   - Requires MACD + Volume confirmation
   - Best for: Risk-averse trading

2. **⚖️ Balanced** (Default)
   - Medium positions (15-30%)
   - Standard stops (2.5% / 2.5x ATR)
   - Volume confirmation only
   - Best for: General use

3. **🚀 Aggressive**
   - Large positions (25-50%)
   - Tight stops (2% / 2x ATR)
   - No confirmation filters
   - Best for: Experienced traders, high risk tolerance

4. **⚡ Scalping**
   - Large positions (30-50%)
   - Very tight stops (1% / 1.5x ATR)
   - Small profit targets (2%)
   - Best for: Short-term trading, high frequency

#### Backtest Results

Each completed backtest shows:

**Summary Metrics**
- **Final Value**: Ending portfolio value
- **Total P&L**: Profit/Loss in dollars and percentage
- **Trades**: Number of trades executed
- **vs Buy & Hold**: Performance comparison

**Detailed View** (click to expand)
- All custom parameters used
- Entry/exit timestamps
- Individual trade results

#### Result Management

**Select Multiple**
- Click any result card to select it
- Selected cards are highlighted
- Counter shows number selected

**Compare**
- Select 2+ results
- Click "Compare Selected"
- View side-by-side metrics
- Identify best parameter combinations

**Clear**
- Remove all backtest history
- Frees up memory
- Cannot be undone

---

## API Endpoints

For programmatic access or custom integrations:

### GET `/api/config`
Returns current bot configuration

```bash
curl http://localhost:8000/api/config
```

### GET `/api/stats`
Returns trading statistics

```bash
curl http://localhost:8000/api/stats
```

Response:
```json
{
  "total_trades": 150,
  "winning_trades": 85,
  "losing_trades": 65,
  "win_rate": 56.67,
  "total_pnl": 342.50,
  "avg_pnl": 2.28
}
```

### GET `/api/trades`
Query trade history with filters

```bash
# Last 100 trades
curl http://localhost:8000/api/trades

# Only buy trades
curl http://localhost:8000/api/trades?side=buy

# Only stop losses
curl http://localhost:8000/api/trades?exit_reason=stop_loss

# Last 7 days
curl http://localhost:8000/api/trades?days_back=7
```

### GET `/api/positions`
Get open positions

```bash
curl http://localhost:8000/api/positions
```

### POST `/api/backtest/run`
Start a new backtest

```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "days_back": 30,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.05
  }'
```

Response:
```json
{
  "message": "Backtest started",
  "backtest_id": "2025-11-22T10:30:00.000000"
}
```

### GET `/api/backtest/status`
Check if backtest is running

```bash
curl http://localhost:8000/api/backtest/status
```

### GET `/api/backtest/results`
Get all backtest results

```bash
curl http://localhost:8000/api/backtest/results
```

---

## Workflow Examples

### Example 1: Test Different Stop Loss Levels

1. Go to `/backtest`
2. Switch to **Custom Parameters**
3. Set **Stop Loss %** to 1.5, click "Run Custom Backtest"
4. Wait for results
5. Set **Stop Loss %** to 3.0, run again
6. Select both results, click "Compare Selected"
7. Identify which stop loss performs better

### Example 2: Optimize EMA Periods

1. Go to `/backtest`
2. Test these combinations:
   - Short 12, Long 26 (default)
   - Short 8, Long 21 (faster)
   - Short 20, Long 50 (slower)
3. Compare results
4. Apply best combination to `/settings`

### Example 3: Compare Preset Strategies

1. Go to `/backtest`
2. Set **Days back** to 60
3. Click "Conservative" preset
4. Wait for completion
5. Click "Balanced" preset
6. Click "Aggressive" preset
7. Select all three, compare
8. Choose strategy that fits your risk tolerance

---

## Tips & Best Practices

### Performance Optimization

**Backtest Duration**
- 7 days: ~10 seconds (quick tests)
- 30 days: ~30-60 seconds (standard)
- 90 days: ~2-3 minutes (comprehensive)

**Multiple Backtests**
- Only one backtest can run at a time
- Queue up tests mentally, run sequentially
- Results persist until "Clear All"

### Parameter Tuning

**Start Conservative**
1. Use Conservative preset as baseline
2. Gradually increase position size
3. Tighten stops only if win rate is high
4. Enable filters if too many losing trades

**Avoid Overfitting**
- Test on different time periods
- Don't optimize for single timeframe
- If strategy works on 7, 30, and 90 days → likely robust
- If only works on one period → likely overfit

**Key Metrics to Watch**
- **Win Rate**: Target 50%+ (higher is better)
- **P&L vs Buy & Hold**: Positive difference shows strategy adds value
- **Number of Trades**: Too few = missed opportunities, too many = overtrading
- **Avg P&L per Trade**: Should be positive and consistent

---

## Troubleshooting

### Backtest Stuck "Running"
- **Cause**: Bot crashed during backtest
- **Fix**: Refresh page, backtest will show as failed
- **Prevention**: Don't run backtests with >90 days

### No Data in Chart
- **Cause**: Bot not running or not connected to Binance
- **Fix**: Check terminal for errors, restart bot
- **Verify**: Check `http://localhost:8000/state` returns data

### Settings Not Applied
- **Remember**: Settings page is for backtests only
- **To apply live**: Stop bot, set environment variables, restart
- **Or**: Edit `.env` file with new values

### API Errors
- **Database Errors**: Ensure database is initialized
- **Connection Errors**: Verify bot is running on port 8000
- **Timeout**: Increase backtest timeout in code if needed

---

## Advanced Usage

### Custom Analysis Scripts

Use the API to build custom analysis:

```python
import requests
import pandas as pd

# Get all backtest results
response = requests.get('http://localhost:8000/api/backtest/results')
results = response.json()['results']

# Convert to DataFrame
df = pd.DataFrame([{
    'timestamp': r['timestamp'],
    'pnl_pct': r['result']['pnl_pct'],
    'trades': r['result']['trades'],
    'days': r['days_back']
} for r in results if r['status'] == 'completed'])

# Find best performing config
best = df.loc[df['pnl_pct'].idxmax()]
print(f"Best result: {best['pnl_pct']:.2f}% over {best['days']} days")
```

### Export Backtest Results

```python
import json

response = requests.get('http://localhost:8000/api/backtest/results')
results = response.json()

# Save to file
with open('backtest_results.json', 'w') as f:
    json.dump(results, f, indent=2)
```

---

## Navigation Quick Reference

| Page | URL | Purpose |
|------|-----|---------|
| Live Dashboard | `/ui` | Monitor real-time trading |
| Settings | `/settings` | Configure parameters |
| Backtest | `/backtest` | Run historical tests |
| API Docs | `/api/stats` | JSON endpoint examples |

---

## Security Notes

**Development Only**
- This dashboard is intended for local development
- Default: listens on `0.0.0.0:8000` (all interfaces)
- **Do not expose to public internet without authentication**

**Production Deployment**
- Add authentication (Basic Auth, OAuth, etc.)
- Use HTTPS/TLS
- Restrict to localhost or VPN
- Set `BOT_DASHBOARD_HOST=127.0.0.1` in config

---

## Future Enhancements

Planned features:
- [ ] Real-time backtest progress bar
- [ ] Download backtest results as CSV
- [ ] Visual parameter optimizer (grid search)
- [ ] Multi-symbol backtesting
- [ ] Paper trading simulator with replay
- [ ] Telegram/Discord notifications
- [ ] Portfolio allocation optimizer
- [ ] Risk metrics dashboard (Sharpe, Sortino, Max DD)

---

**Dashboard Version**: 1.0
**Last Updated**: November 22, 2025
**Compatible with**: Trading Bot v1.0+






