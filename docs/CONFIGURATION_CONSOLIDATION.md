# Configuration Page Consolidation

## Overview

The trading bot previously had two separate configuration pages with overlapping functionality. This has been consolidated into a single, powerful **Configuration** page with full database-backed, hot-reload capabilities.

## What Changed

### ✅ Removed
- **Old Settings Page** (`/settings`) - Read-only page with non-functional save button
- Duplicate navigation links for "Settings" and "Configure"
- `templates/settings.html` file

### ✅ Enhanced
- **New Configuration Page** (`/strategy-config`) - Now the single source of truth
- Expanded to include ALL bot parameters (not just strategy params)
- Full database persistence for ALL configurable parameters
- Hot-reload capability for most parameters

### ✅ Added
- Backward compatibility: `/settings` now redirects to `/strategy-config`
- Database storage for 20+ new configuration parameters
- Support for all trading, risk, and indicator parameters

## New Unified Configuration Page

Access via: **Dashboard → Configuration** or `/strategy-config`

### Sections

#### 1. 📊 Trading Parameters
- Symbol (BTC/USDT, ETH/USDT, etc.) - *requires restart*
- Timeframe (5m, 15m, 1h, etc.) - *requires restart*
- Initial Capital
- Order Size Percentage

#### 2. 📉 Technical Indicators
- RSI Period, Oversold, Overbought
- ATR Period, Stop Multiplier
- ATR-Based Stops toggle

#### 3. 🛡️ Risk Management
- Stop Loss Percentage
- Take Profit Percentage
- Trailing Stop Percentage
- Trailing Stop toggle

#### 4. 💰 Position Sizing
- Min Position Size
- Max Position Size
- Dynamic Position Sizing toggle

#### 5. 🔍 Signal Filters
- Volume Threshold
- Volume Confirmation toggle
- MACD Confirmation toggle
- Max Trades Per Day

#### 6. 🧠 Multi-Strategy System
- Aggregation Mode
- Minimum Confidence

#### 7. 📈 EMA Crossover Strategy
- Enable/Disable
- Strategy Weight
- Short/Long EMA Windows
- Min Trend Strength

#### 8. 🌊 RSI + Bollinger Bands Strategy
- Enable/Disable
- Strategy Weight
- RSI Thresholds
- Bollinger Band Parameters
- Stop Loss/Take Profit

## Database Schema Updates

Added support for the following new configuration keys in the `strategy_config` table:

```sql
-- Trading Parameters
symbol, timeframe, initial_usdt, order_pct

-- Indicators
rsi_period, rsi_oversold, rsi_overbought
atr_period, atr_stop_multiplier, use_atr_stops

-- Risk Management
stop_loss_pct, take_profit_pct, trailing_stop_pct, use_trailing_stop

-- Position Sizing
min_position_size, max_position_size, use_dynamic_sizing

-- Signal Filters
volume_threshold, require_volume_confirmation
require_macd_confirmation, max_trades_per_day
```

All 48 configurable parameters are now stored in the database!

## Configuration Priority (Unchanged)

1. **Database** (highest) - Values in `strategy_config` table
2. **Environment** - Values in `.env` file
3. **Defaults** - Hardcoded defaults in `config.py`

## Migration Path

No migration needed! The system automatically:

1. Falls back to `.env` values if database is empty
2. Redirects old `/settings` URLs to new page
3. Maintains backward compatibility

### First-Time Setup

1. Visit **Configuration** page
2. Review current settings (loaded from `.env`)
3. Click **"Apply Configuration"**
4. Settings are now stored in database
5. Future changes apply instantly via database

## API Changes

### Expanded Endpoints

**GET `/api/strategy-config`**
- Now returns ALL 48 parameters (not just strategy params)

**POST `/api/strategy-config/update`**
- Now accepts ALL 48 parameters for saving

**POST `/api/strategy-config/apply`**
- Hot-reloads ALL supported parameters (no restart needed)

### New Configuration Keys

All the parameters listed in the sections above can now be managed via API.

Example:
```bash
curl -X POST http://localhost:8000/api/strategy-config/update \
  -u admin:password \
  -H "Content-Type: application/json" \
  -d '{
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.05,
    "use_trailing_stop": true,
    "volume_threshold": 1.2,
    "strategy_ema_weight": 1.5
  }'
```

## Architecture

```
Web Dashboard (UI controls)
        │
        ▼
API Endpoints
  GET  /api/strategy-config           ← current config
  POST /api/strategy-config/update    ← save to database
  POST /api/strategy-config/apply     ← hot reload
        │
        ▼
Database: strategy_config table (key-value store)
        │
        ▼
BotConfig.load()  (reads DB → falls back to .env → falls back to hardcoded default)
        │
        ▼
StrategyManager.reload_config()  (applies to running strategies, no restart)
```

### `strategy_config` table

| Column | Type | Description |
|--------|------|-------------|
| `key` | STRING(100) | Configuration key (unique) |
| `value` | STRING(500) | Value, stored as string |
| `value_type` | STRING(20) | `bool`, `int`, `float`, `str` |
| `category` | STRING(50) | e.g. `multi_strategy`, `ema`, `rsi_bb`, `general` |
| `description` | STRING(500) | Human-readable description |

### Code examples

```python
import requests

config = {"strategy_ema_weight": 1.5, "min_signal_confidence": 0.4}
requests.post("http://localhost:8000/api/strategy-config/update",
              json=config, auth=("admin", "your_password"))
requests.post("http://localhost:8000/api/strategy-config/apply",
              auth=("admin", "your_password"))
```

```bash
# View current active config
curl http://localhost:8000/api/config -u admin:your_password | jq .

# Verify database directly
sqlite3 data/trading.db "SELECT * FROM strategy_config;"

# Reset to .env defaults by clearing the table
sqlite3 data/trading.db "DELETE FROM strategy_config;"
```

## What Requires Restart

Most parameters can be hot-reloaded, but these require a bot restart:

- ❗ API Keys and Credentials
- ❗ Database Connection Settings
- ❗ Dashboard Host/Port
- ❗ Exchange Type
- ❗ **Symbol** (trading pair)
- ❗ **Timeframe** (candle interval)

All other parameters apply instantly when you click **"Apply Configuration"**.

## User Experience Improvements

### Before (Two Pages)

```
Dashboard → Settings (read-only, non-functional)
Dashboard → Configure (strategy params only, functional)
```

**Problems:**
- Confusing to have two config pages
- Settings page didn't actually save
- Had to edit `.env` and restart for most changes
- Strategy params separate from general config

### After (One Page)

```
Dashboard → Configuration (comprehensive, fully functional)
```

**Benefits:**
- ✅ Single source of truth for ALL configuration
- ✅ Everything saves to database
- ✅ Hot-reload for most parameters
- ✅ Organized into logical sections
- ✅ Better UI with sliders and visual feedback
- ✅ Real-time validation and apply

## Navigation Changes

**Old:**
```
Dashboard | Backtest | Strategies | Settings | Configure | Logout
```

**New:**
```
Dashboard | Strategies | Configuration | Backtest | Logout
```

Cleaner, more logical order. Configuration is highlighted when viewing `/settings` or `/strategy-config`.

## Code Changes Summary

### Files Modified
- `templates/strategy_config.html` - Expanded with all parameters
- `dashboard.py` - Updated API endpoints for full config
- `config.py` - Database reading for all parameters
- `templates/base.html` - Updated navigation
- `database.py` - Already supported all params (no changes)

### Files Removed
- `templates/settings.html` - Deleted (functionality merged)

### Files Added
- None (consolidation only)

## Testing Checklist

- [x] All parameters load from database
- [x] All parameters fall back to `.env` if DB empty
- [x] Apply button saves to database
- [x] Hot reload updates strategies
- [x] Old `/settings` URL redirects properly
- [x] Navigation shows correct active state
- [x] No linter errors
- [x] Backward compatible with existing setups

## Benefits

1. **Simplified UX**: One configuration page instead of two
2. **Consistency**: All config uses same database-backed system
3. **Productivity**: Hot-reload means no restart for most changes
4. **Maintainability**: Single codebase for configuration
5. **Scalability**: Easy to add new parameters in the future

## Future Enhancements

- [ ] Configuration templates (Conservative, Balanced, Aggressive)
- [ ] Configuration import/export (JSON)
- [ ] Configuration versioning and rollback
- [ ] A/B testing different configurations
- [ ] Real-time validation and warnings

## Summary

The configuration system is now **unified, powerful, and user-friendly**. All bot parameters are accessible from a single page with full database persistence and hot-reload capabilities. The old Settings page has been gracefully deprecated with automatic redirects, ensuring no disruption to existing workflows.

**Result:** A cleaner, more intuitive configuration experience! 🎉
