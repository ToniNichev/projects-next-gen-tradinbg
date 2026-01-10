# Direct API Configuration Guide

## Overview

The trading bot now supports **direct API-based configuration** for strategy parameters. Configuration is stored in a SQLite database and can be updated via the web dashboard without restarting the bot.

## Features

✅ **Database-backed Configuration**: Strategy parameters stored in `strategy_config` table  
✅ **Hot Reload**: Apply changes instantly without bot restart  
✅ **Web UI**: User-friendly sliders and inputs in `/strategy-config` page  
✅ **Priority System**: Database values override `.env` settings  
✅ **Fallback**: Automatically uses `.env` values if database is empty  
✅ **Backwards Compatible**: Works with existing `.env` configuration

## How It Works

### Configuration Priority

1. **Database** (highest priority) - values from `strategy_config` table
2. **Environment Variables** - values from `.env` file
3. **Defaults** - hardcoded defaults in `config.py`

### Architecture

```
┌─────────────────┐
│  Web Dashboard  │
│ (UI Controls)   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  API Endpoints          │
│  /api/strategy-config   │ ← GET current config
│  /update                │ ← POST save to database
│  /apply                 │ ← POST hot reload
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Database               │
│  strategy_config table  │
│  (key-value store)      │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  BotConfig.load()       │
│  (reads DB → ENV)       │
└────────┬────────────────┘
         │
         ▼
┌─────────────────────────┐
│  StrategyManager        │
│  (hot reload support)   │
└─────────────────────────┘
```

## Usage

### Via Web Dashboard (Recommended)

1. Navigate to **Strategy Configuration** page (`/strategy-config`)
2. Adjust parameters using sliders and inputs
3. Click **"Apply Configuration"** button
4. Changes take effect immediately (no restart needed)

### Via API

#### Get Current Configuration

```bash
GET /api/strategy-config
```

Response:
```json
{
  "success": true,
  "config": {
    "strategy_aggregation_mode": "weighted_voting",
    "min_signal_confidence": 0.3,
    "strategy_ema_enabled": true,
    "strategy_ema_weight": 1.0,
    ...
  },
  "source": "database"
}
```

#### Update Configuration

```bash
POST /api/strategy-config/update
Content-Type: application/json

{
  "strategy_aggregation_mode": "weighted_voting",
  "min_signal_confidence": 0.4,
  "strategy_ema_enabled": true,
  "strategy_ema_weight": 1.2,
  "short_window": 12,
  "long_window": 26,
  ...
}
```

Response:
```json
{
  "success": true,
  "message": "Updated 15 configuration parameters",
  "updated_keys": ["strategy_aggregation_mode", ...]
}
```

#### Apply Configuration (Hot Reload)

```bash
POST /api/strategy-config/apply
```

Response:
```json
{
  "success": true,
  "message": "Configuration applied successfully",
  "strategies_reloaded": 2
}
```

## Database Schema

### `strategy_config` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `key` | STRING(100) | Configuration key (unique) |
| `value` | STRING(500) | Configuration value (stored as string) |
| `value_type` | STRING(20) | Data type: `bool`, `int`, `float`, `str` |
| `category` | STRING(50) | Category: `multi_strategy`, `ema`, `rsi_bb`, `general` |
| `description` | STRING(500) | Human-readable description |
| `created_at` | DATETIME | Creation timestamp |
| `updated_at` | DATETIME | Last update timestamp |

### Example Records

```sql
key: "strategy_ema_enabled"
value: "true"
value_type: "bool"
category: "ema"
description: "Enable EMA Crossover strategy"

key: "min_signal_confidence"
value: "0.3"
value_type: "float"
category: "multi_strategy"
description: "Minimum confidence threshold"
```

## Configurable Parameters

### Multi-Strategy System

- `strategy_aggregation_mode` (str): `weighted_voting`, `voting`, `unanimous`, `any`, `best`
- `min_signal_confidence` (float): 0.1 to 0.8

### EMA Crossover Strategy

- `strategy_ema_enabled` (bool): Enable/disable strategy
- `strategy_ema_weight` (float): 0.5 to 2.0
- `short_window` (int): 5 to 50
- `long_window` (int): 10 to 100
- `min_trend_strength` (float): 0.00001 to 0.001

### RSI + Bollinger Bands Strategy

- `strategy_rsi_bb_enabled` (bool): Enable/disable strategy
- `strategy_rsi_bb_weight` (float): 0.5 to 2.0
- `strategy_rsi_bb_rsi_oversold` (float): 10 to 40
- `strategy_rsi_bb_rsi_overbought` (float): 60 to 90
- `strategy_rsi_bb_bb_period` (int): 10 to 50
- `strategy_rsi_bb_bb_std_dev` (float): 1.0 to 3.0
- `strategy_rsi_bb_stop_loss_pct` (float): 0.01 to 0.05
- `strategy_rsi_bb_take_profit_pct` (float): 0.02 to 0.08

## Hot Reload Behavior

When you click "Apply Configuration":

1. **Database Update**: New values saved to `strategy_config` table
2. **Config Reload**: `BotConfig.load()` called, reads from database
3. **Strategy Reload**: `StrategyManager.reload_config()` called:
   - Updates aggregation mode
   - Updates minimum confidence
   - Reloads each strategy's parameters
   - Enables/disables strategies as needed
4. **Immediate Effect**: Next signal computation uses new parameters

### What Requires Restart

Most parameters can be hot-reloaded. However, these require a full bot restart:

- API keys and credentials
- Database connection settings
- Dashboard host/port
- Exchange type
- Symbol or timeframe changes

## Code Examples

### Python: Update Config via API

```python
import requests

config = {
    "strategy_ema_weight": 1.5,
    "strategy_rsi_bb_weight": 0.8,
    "min_signal_confidence": 0.4
}

# Save to database
response = requests.post(
    "http://localhost:8000/api/strategy-config/update",
    json=config,
    auth=("admin", "your_password")
)
print(response.json())

# Apply changes (hot reload)
response = requests.post(
    "http://localhost:8000/api/strategy-config/apply",
    auth=("admin", "your_password")
)
print(response.json())
```

### JavaScript: Update Config from Browser

```javascript
async function updateStrategy() {
  const config = {
    strategy_ema_enabled: true,
    strategy_ema_weight: 1.5,
    min_signal_confidence: 0.4
  };
  
  // Save to database
  const updateResp = await fetch('/api/strategy-config/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
  
  // Apply changes
  const applyResp = await fetch('/api/strategy-config/apply', {
    method: 'POST'
  });
  
  console.log('Configuration applied!');
}
```

## Migration from .env to Database

To migrate your existing `.env` configuration to the database:

1. Start the bot with your current `.env` file
2. Go to `/strategy-config` page
3. Click "Apply Configuration" (this saves current values to database)
4. Future changes will be stored in database and override `.env`

## Troubleshooting

### Configuration Not Applying

**Check logs:**
```bash
tail -f logs/bot.log | grep -i "reload"
```

**Verify database:**
```bash
sqlite3 data/trading.db "SELECT * FROM strategy_config;"
```

### Reset to .env Defaults

Clear the database to use `.env` values:

```bash
sqlite3 data/trading.db "DELETE FROM strategy_config;"
```

Or via API:
```bash
curl -X DELETE http://localhost:8000/api/strategy-config/reset \
  -u admin:your_password
```

### View Current Active Config

```bash
curl http://localhost:8000/api/config -u admin:your_password | jq .
```

## Best Practices

1. **Test in Paper Trading**: Always test configuration changes in paper trading mode first
2. **Small Adjustments**: Make incremental changes rather than large jumps
3. **Monitor Performance**: Watch the `/strategies` dashboard after applying changes
4. **Backup Database**: Regularly backup `data/trading.db` before major changes
5. **Document Changes**: Keep notes on what works best for your trading style

## Security Considerations

- Configuration endpoints require authentication
- Rate limited to 10 requests/minute for updates
- No sensitive credentials stored in database (API keys still in `.env`)
- Configuration changes logged for audit trail

## Future Enhancements

- [ ] Configuration versioning/rollback
- [ ] A/B testing of different parameter sets
- [ ] Auto-optimization based on backtesting results
- [ ] Configuration presets (conservative, balanced, aggressive)
- [ ] Real-time configuration validation
- [ ] Configuration import/export (JSON)

## Summary

The direct API configuration system makes it easy to:
- Adjust strategy parameters on the fly
- Test different configurations without downtime
- Store configurations persistently in the database
- Maintain backwards compatibility with `.env` files

All changes are logged and can be monitored via the dashboard!
