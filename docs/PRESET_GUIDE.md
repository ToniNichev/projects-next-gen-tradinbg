# Strategy Presets Guide

## Overview

Strategy Presets allow you to instantly switch between different trading configurations. Instead of manually adjusting 40+ parameters, you can load a preset that's optimized for a specific trading style.

## Features

- **Built-in Presets**: 5 pre-configured presets for common trading styles
- **Custom Presets**: Save your own configurations for quick access
- **One-Click Loading**: Apply entire configurations instantly
- **Hot Reload**: Changes apply immediately without restart (except symbol/timeframe)
- **Visual Grid**: Browse presets with descriptions and categories

## Built-in Presets

### 🟢 Conservative (Low Risk)
- **Stop Loss**: 1.5% | **Take Profit**: 3%
- **Position Size**: 15% (10-20% range)
- **Aggregation**: Unanimous (all strategies must agree)
- **Confidence**: 50% minimum
- **Best For**: Cautious traders, capital preservation, low-risk tolerance
- **Trades Per Day**: ~3

### 🔵 Balanced (Default)
- **Stop Loss**: 2.5% | **Take Profit**: 4%
- **Position Size**: 25% (15-35% range)
- **Aggregation**: Weighted Voting
- **Confidence**: 30% minimum
- **Best For**: Most traders, good starting point
- **Trades Per Day**: ~5

### 🔴 Aggressive (High Risk)
- **Stop Loss**: 4% | **Take Profit**: 8%
- **Position Size**: 40% (25-50% range)
- **Aggregation**: Any (one strategy can trigger)
- **Confidence**: 20% minimum
- **Best For**: Experienced traders, high risk tolerance, volatility
- **Trades Per Day**: ~10

### 🟠 Scalping (5m timeframe)
- **Timeframe**: 5 minutes
- **Stop Loss**: 0.8% | **Take Profit**: 1.5%
- **Position Size**: 20% (15-30% range)
- **Aggregation**: Best (most confident strategy)
- **Confidence**: 40% minimum
- **Best For**: Day traders, constant monitoring, quick profits
- **Trades Per Day**: ~15
- **⚠️ Requires Restart**: Changes timeframe

### 🟣 Swing Trading (4h timeframe)
- **Timeframe**: 4 hours
- **Stop Loss**: 5% | **Take Profit**: 12%
- **Position Size**: 35% (20-45% range)
- **Aggregation**: Weighted Voting
- **Confidence**: 35% minimum
- **Best For**: Longer holds, less monitoring, bigger moves
- **Trades Per Day**: ~3
- **⚠️ Requires Restart**: Changes timeframe

## How to Use

### Loading a Preset

1. Navigate to **Strategy Center** → **Configuration Presets**
2. Choose a preset from:
   - **Dropdown menu** at the top
   - **Grid view** by clicking any preset card
3. Review the loaded settings (all form fields update)
4. Click **"Apply Configuration"** to activate
5. If timeframe/symbol changed, restart the bot: `./restart.sh`

### Creating Custom Presets

1. Configure all parameters as desired in the form
2. Click **"💾 Save Current"**
3. Enter:
   - **Name**: Lowercase identifier (e.g., `my_scalping`)
   - **Display Name**: Human-readable (e.g., "My Scalping Setup")
   - **Description**: What makes this preset special
4. Your preset appears in "Custom Presets" group
5. Load it anytime just like built-in presets

### Deleting Custom Presets

1. Select the custom preset from the dropdown
2. Click **"🗑️ Delete"** button (appears for custom presets only)
3. Confirm deletion
4. Built-in presets cannot be deleted

## API Endpoints

### Get All Presets
```bash
GET /api/presets
```

**Response:**
```json
{
  "success": true,
  "presets": [
    {
      "id": 1,
      "name": "conservative",
      "display_name": "Conservative (Low Risk)",
      "description": "Lower risk settings...",
      "config": { /* all parameters */ },
      "is_builtin": true,
      "is_default": false,
      "category": "conservative",
      "created_at": "2024-01-01T00:00:00"
    }
  ],
  "count": 5
}
```

### Get Specific Preset
```bash
GET /api/presets/{preset_name}
```

### Save Preset
```bash
POST /api/presets
Content-Type: application/json

{
  "name": "my_custom",
  "display_name": "My Custom Setup",
  "description": "My personalized configuration",
  "config": {
    "stop_loss_pct": 0.03,
    "take_profit_pct": 0.06,
    // ... all other parameters
  },
  "category": "custom"
}
```

### Apply Preset
```bash
POST /api/presets/{preset_name}/apply
```

This endpoint:
1. Loads the preset configuration
2. Saves all parameters to database
3. Applies to running strategies (hot reload)
4. Returns whether a restart is needed

### Delete Preset
```bash
DELETE /api/presets/{preset_name}
```

## Migration for Existing Users

If you're upgrading from an older version without presets:

```bash
# Run the migration script
python3 migrate_add_presets.py

# Or manually restart the bot (it will auto-create tables)
./restart.sh
```

The migration:
- Creates the `strategy_presets` table
- Initializes all 5 built-in presets
- Doesn't modify your existing configuration

## Tips & Best Practices

### Workflow Recommendations

1. **Start with Balanced**: Load the default balanced preset
2. **Backtest**: Run a backtest to see how it performs
3. **Adjust**: Fine-tune parameters based on results
4. **Save**: Create a custom preset with your adjustments
5. **Compare**: Try other presets and compare results

### Creating Good Custom Presets

- **Name clearly**: Use descriptive names (e.g., `btc_morning_scalp`)
- **Document well**: Write detailed descriptions explaining when to use
- **Test first**: Backtest thoroughly before using in production
- **Start conservative**: You can always increase risk later
- **Version control**: Save variations (v1, v2) as you refine

### Timeframe Considerations

- **5m-15m**: Scalping, requires constant monitoring
- **1h**: Day trading, check every few hours
- **4h-1d**: Swing trading, check once or twice daily
- Changing timeframe **requires restart**: plan accordingly

### Risk Management

- Conservative preset is great for:
  - Starting out
  - Testing new strategies
  - Volatile/uncertain markets
  
- Aggressive preset requires:
  - Experience with the bot
  - Comfort with drawdowns
  - Active monitoring

## Troubleshooting

### Preset doesn't appear
- Check browser console for errors
- Verify database is accessible
- Try refreshing the page

### Configuration not applying
- Click "Apply Configuration" after loading preset
- Check for error alerts at the top of the page
- Verify you have sufficient permissions

### Restart required but forgot to restart
- Symbol/timeframe changes need restart
- Other parameters can hot-reload
- Always check the alert message after applying

### Custom preset disappeared
- Check if you deleted it by accident
- Verify database hasn't been reset
- Custom presets survive bot restarts (stored in DB)

## Technical Details

### Database Schema

```python
class StrategyPreset:
    id: int                    # Primary key
    name: str                  # Unique slug identifier
    display_name: str          # Human-readable name
    description: str           # Preset description
    config_json: str           # JSON blob of all parameters
    is_builtin: bool           # Built-in vs user-created
    is_default: bool           # Default preset flag
    category: str              # conservative, aggressive, etc.
    created_at: datetime       # Creation timestamp
    updated_at: datetime       # Last update timestamp
```

### Configuration Parameters

Presets can include any of these ~45 parameters:

**Trading**: symbol, timeframe, initial_usdt, order_pct

**Risk**: stop_loss_pct, take_profit_pct, trailing_stop_pct, use_trailing_stop

**Position Sizing**: min_position_size, max_position_size, use_dynamic_sizing

**Indicators**: rsi_period, rsi_oversold, rsi_overbought, atr_period, atr_stop_multiplier, use_atr_stops

**Filters**: volume_threshold, require_volume_confirmation, require_macd_confirmation, max_trades_per_day

**Multi-Strategy**: strategy_aggregation_mode, min_signal_confidence

**EMA Strategy**: strategy_ema_weight, short_window, long_window, min_trend_strength

**RSI+BB Strategy**: strategy_rsi_bb_weight, rsi_bb_rsi_oversold, rsi_bb_rsi_overbought, bb_period, bb_std_dev, rsi_bb_stop_loss_pct, rsi_bb_take_profit_pct

**MACD+Volume Strategy**: strategy_macd_weight, macd_fast_period, macd_slow_period, macd_signal_period, macd_volume_multiplier, macd_require_zero_cross, macd_stop_loss_pct, macd_take_profit_pct

## Future Enhancements

Potential features for future versions:

- [ ] Import/export presets as JSON files
- [ ] Share presets with other users
- [ ] Preset performance tracking
- [ ] Auto-select best preset based on market conditions
- [ ] Preset recommendations based on backtest results
- [ ] Scheduled preset switching (day trading vs overnight)
- [ ] Clone/duplicate built-in presets as starting point

## Support

For issues or questions:
1. Check this guide first
2. Review the main README.md
3. Check the dashboard alerts/logs
4. Open an issue on GitHub with preset details

---

**Happy Trading! 📈**
