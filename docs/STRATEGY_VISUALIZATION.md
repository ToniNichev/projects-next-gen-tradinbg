# Strategy Attribution Visualization

## Overview

The backtest chart now visualizes which strategy triggered each trade with color-coded markers and detailed tooltips. This makes it easy to see which strategies are most active and how they perform.

## Features Implemented

### 1. Color-Coded Trade Markers
- Each strategy has a distinct color for easy visual identification
- Buy trades: upward triangles
- Sell trades: downward triangles
- Colors persist across the entire chart for consistency

### 2. Strategy Color Mapping

| Strategy | Color | Hex Code |
|----------|-------|----------|
| EMA Crossover | Bright Cyan | `#00D9FF` |
| RSI+BB Mean Reversion | Pink | `#FF6B9D` |
| MACD+Volume Momentum | Gold | `#FFD700` |
| LLM Pattern | Purple | `#9D4EDD` |
| Multi-Strategy (Aggregated) | White | `#FFFFFF` |
| Unknown/Exit Trades | Gray | `#808080` |

### 3. Enhanced Tooltips
Tooltips now display:
- **Strategy Name**: Which strategy triggered the trade
- **Confidence**: Signal confidence (0-100%)
- **Reason**: Signal, stop_loss, take_profit, trailing_stop
- **P&L**: Profit/loss for exit trades
- **Amount**: Trade size in BTC
- **Price**: Execution price

### 4. Dynamic Legend
- Automatically shows only strategies that were used in the backtest
- Updates when viewing different backtest results
- Clean, compact design below chart controls

## How to Use

### Running a Backtest with Visualization

1. **Start the Dashboard**
   ```bash
   cd /Users/toninichev/Applications/trading.toninichev.com
   python3 dashboard.py
   ```

2. **Navigate to Backtest Page**
   - Open http://localhost:5001/backtest in your browser

3. **Configure Strategies** (Optional)
   - Go to Strategy Center to enable/disable strategies
   - Set aggregation mode (voting, weighted, best, etc.)
   - Adjust strategy weights

4. **Run Backtest**
   - Select days of history (7-90 days recommended)
   - Click "🚀 Run Backtest"
   - Wait for completion

5. **View Chart**
   - Click "📊 View Chart" on any completed backtest result
   - Observe color-coded trade markers
   - Hover over markers to see strategy details

### Testing Different Scenarios

#### Single Strategy Test
1. Disable all strategies except one in Strategy Center
2. Run backtest
3. All markers should be the same color (that strategy's color)

#### Multi-Strategy Test
1. Enable 2-3 strategies
2. Set aggregation mode to "weighted_voting" or "best"
3. Run backtest
4. Markers should show different colors based on which strategy triggered each trade

#### Aggregated Signals
1. Enable all strategies
2. Set aggregation mode to "voting" or "unanimous"
3. Run backtest
4. Markers should show white (aggregated) when multiple strategies agree

## Technical Details

### Modified Files

1. **backtest.py**
   - Added `strategy_name` and `confidence` to chart_data trade markers
   - Extracts info from signal dictionary

2. **templates/backtest.html**
   - Added strategy color mapping constants
   - Groups trades by strategy for color-coding
   - Creates separate datasets per strategy
   - Enhanced tooltip callbacks
   - Dynamic legend generation

### Data Flow

```
StrategySignal (strategy_name, confidence)
    ↓
TradeRecord (signal dict contains strategy info)
    ↓
chart_data["trades"] (includes strategy_name, confidence)
    ↓
JavaScript groups by strategy
    ↓
Color-coded scatter plot datasets
    ↓
Visual chart with attribution
```

## Troubleshooting

### Issue: All markers are gray
- **Cause**: Strategy name not captured in trade data
- **Solution**: Ensure strategies are properly initialized and returning StrategySignal objects with `strategy_name` field

### Issue: No legend appears
- **Cause**: No trades in backtest result
- **Solution**: Verify backtest completed successfully and has trades

### Issue: Tooltips don't show strategy info
- **Cause**: Exit trades (stop loss, etc.) don't have strategy attribution
- **Solution**: This is expected - only entry signals show strategy info

### Issue: Colors don't match legend
- **Cause**: JavaScript caching
- **Solution**: Hard refresh browser (Cmd+Shift+R or Ctrl+Shift+R)

## Future Enhancements

Potential additions (not yet implemented):

1. **Confidence Heat Map**
   - Background color intensity based on signal confidence
   - Helps identify high-conviction vs low-conviction trades

2. **Strategy Performance Panel**
   - Per-strategy win rate breakdown
   - Average confidence vs actual performance correlation

3. **Signal Timeline**
   - Detailed textual log of all strategy decisions
   - Shows rejected signals (below confidence threshold)

4. **LLM Reasoning Tooltips**
   - Click markers to see full LLM analysis
   - Expandable modal with market context

5. **Strategy Voting Visualization**
   - When using voting aggregation, show how each strategy voted
   - Display vote counts and weights

## Testing Checklist

- [ ] Dashboard starts without errors
- [ ] Backtest page loads correctly
- [ ] Strategy legend appears with correct colors
- [ ] Trade markers show strategy-specific colors
- [ ] Tooltips display strategy name
- [ ] Tooltips display confidence percentage
- [ ] Multiple strategies show different colors
- [ ] Exit trades (stop loss, etc.) show gray markers
- [ ] Legend only shows strategies that were actually used
- [ ] Browser refresh preserves functionality

## Example Output

When you run a backtest with multiple strategies enabled, you should see:

```
Chart Legend:
• Cyan triangles: EMA Crossover
• Pink triangles: RSI+BB Mean Reversion  
• Gold triangles: MACD+Volume Momentum
• Purple triangles: LLM Pattern
• Gray triangles: Exit trades

Tooltip Example (hovering over cyan buy triangle):
EMA Crossover Buy @ $67,234.50 (SIGNAL)
Strategy: EMA Crossover
Confidence: 75%
Amount: 0.014856 BTC
```

## Next Steps

1. Start dashboard and navigate to backtest page
2. Run a quick 7-day backtest with multiple strategies
3. View chart and verify colors match strategies
4. Test tooltip functionality
5. Compare performance of different strategies visually
6. Report any issues or suggestions for improvement

---

**Status**: ✅ Implementation complete, ready for testing
**Version**: 1.0
**Date**: 2026-02-09
