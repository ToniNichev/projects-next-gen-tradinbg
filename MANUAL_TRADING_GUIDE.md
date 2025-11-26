# Manual Trading Feature - User Guide

## Overview

The manual trading feature allows you to execute buy and sell orders directly from the dashboard while your automated trading bot continues to run. This gives you full control to take advantage of market opportunities or manually manage your positions.

## Accessing Manual Trading

1. Navigate to the dashboard: `http://localhost:8000/ui`
2. The **Manual Trading Panel** is located below the summary cards and above the price chart

## Understanding the Interface

### Current Position Panel
Shows your active position (if any):
- **Side**: LONG or SHORT
- **Entry Price**: Price at which you entered the position
- **Current Price**: Live market price
- **Amount**: Quantity of BTC in the position
- **Unrealized P&L**: Current profit/loss (green = profit, red = loss)
- **Stop Loss**: Automatic exit price if market moves against you
- **Take Profit**: Automatic exit price when target profit is reached

### Trade Controls Panel
Execute manual trades:
- **Position Size (%)**: Percentage of your available USDT to use (10-100%)
- **Buy Button**: Opens a long position or closes a short position
- **Sell Button**: Closes a long position or opens a short position

### Trade Estimate Panel
Preview your trade before execution:
- **Current Price**: Latest market price
- **Available USDT**: Your current USD Tether balance
- **Position Value**: Dollar amount that will be traded
- **Est. Amount**: Estimated BTC quantity you'll receive

## How to Execute a Trade

### Buying (Going Long)

1. **Set Position Size**: Enter the percentage of your balance to use (e.g., 20 = 20%)
2. **Click Buy Button**: The green "🟢 BUY" button
3. **Review Confirmation**: A modal shows trade details including:
   - Entry price
   - Position size
   - Order value
   - Estimated BTC amount
4. **Confirm**: Click "Confirm" to execute or "Cancel" to abort
5. **Success**: You'll see a green notification and your position will appear in the Current Position panel

**Example:**
- Available USDT: $1,000
- Position Size: 25%
- Order Value: $250
- Current BTC Price: $50,000
- You'll receive: ~0.005 BTC

### Selling (Closing Long or Going Short)

1. **If you have a long position**:
   - Click "🔴 SELL" to close your position
   - The confirmation shows your realized P&L
   - Your USDT balance increases by the sale value

2. **If you have no position**:
   - Click "🔴 SELL" to open a short position (paper trading)
   - Set position size percentage
   - Confirm to execute

### Button States

- **Buy Button Disabled**: You're already in a long position or have no USDT
- **Sell Button Disabled**: You have no position to close or sell
- **Both Enabled**: You can execute either action

## Risk Management

### Automatic Stop Loss & Take Profit

All manual trades automatically include risk management:

- **Stop Loss**: Set based on your bot configuration (default: 2.5% or 2.5x ATR)
  - LONG: Exits if price falls below stop loss
  - SHORT: Exits if price rises above stop loss

- **Take Profit**: Set based on your bot configuration (default: 4%)
  - LONG: Exits if price rises to take profit
  - SHORT: Exits if price falls to take profit

- **Trailing Stop**: If enabled, adjusts stop loss as price moves in your favor (default: 1.5%)

### Position Sizing Guidelines

- **Conservative**: 10-20% per trade
- **Moderate**: 20-30% per trade
- **Aggressive**: 30-50% per trade
- **Maximum**: 100% (all-in, high risk)

**Recommendation**: Start with 15-25% to allow multiple trades and risk diversification.

## Integration with Automated Trading

### Coexistence
- Manual and automated trading work together seamlessly
- The bot continues analyzing signals while you trade manually
- Thread-safe implementation prevents conflicts

### What Happens When...

**You manually buy while bot is running:**
- Your manual position is tracked
- Bot will respect your open position
- Bot's signals still computed but won't override your manual trade
- Stop loss/take profit remain active

**Bot generates a signal while you have a manual position:**
- Bot follows normal position management rules
- Won't open conflicting position
- May close your position if opposite signal triggers

**You manually close a position:**
- Position removed immediately
- Bot can open new positions on next signal
- All P&L logged to database

## Monitoring Your Trades

### Real-Time Updates
- Position status updates every 5 seconds
- Price updates every 15 seconds (for 1h timeframe)
- Balance reflects immediately after trades

### Trade History
All manual trades are logged with:
- `"manual": true` flag in database
- Full execution details (price, amount, fees, slippage)
- P&L calculation on closing trades

### Notifications
- **Success** (green): Trade executed successfully
- **Error** (red): Trade failed with reason
- **Auto-dismiss**: Disappears after 5 seconds

## Common Scenarios

### Scenario 1: Quick Profit Taking
```
1. Bot opens long position at $50,000
2. Price quickly rises to $52,000
3. You manually sell to lock in profit
4. Bot continues watching for next signal
```

### Scenario 2: Manual Entry on Breakout
```
1. You see a chart breakout forming
2. Manually buy before bot signal triggers
3. Bot respects your position
4. Position managed with automatic stop loss
```

### Scenario 3: Risk Reduction
```
1. Bot has long position at $50,000
2. Market shows weakness
3. You manually sell to exit early
4. Avoid larger loss from stop loss trigger
```

## Safety Features

### Pre-Trade Validations
- ✅ Sufficient balance check
- ✅ Position size limits (min/max)
- ✅ Duplicate trade prevention
- ✅ Position conflict detection

### Confirmations
- ✅ Modal dialog before execution
- ✅ Trade details preview
- ✅ Clear P&L display
- ✅ Cancel option

### Rate Limiting
- Maximum 10 manual trades per minute
- Prevents accidental rapid-fire trading
- Protects against double-clicks

## Troubleshooting

### "Trader not available" Error
**Cause**: Dashboard started before bot initialized
**Solution**: Wait a few seconds and refresh the page

### "Already in long position" Error
**Cause**: Trying to buy when already long
**Solution**: Close current position first, then buy

### "Insufficient USDT balance" Error
**Cause**: Not enough funds for trade
**Solution**: Reduce position size percentage

### "Trade execution failed" Error
**Cause**: Internal error during trade processing
**Solution**: 
1. Check browser console for details
2. Verify bot is running
3. Check API connection
4. Try again with smaller position size

### Button Disabled
**Cause**: Current state doesn't allow that action
**Solution**: Check "Current Position" panel to understand why

## Best Practices

### 1. Start Small
Begin with 10-15% position sizes to learn the system

### 2. Use Confirmations
Always review the confirmation modal carefully

### 3. Monitor Positions
Watch unrealized P&L and adjust stops if needed

### 4. Respect Stop Loss
Don't disable or ignore stop losses—they protect capital

### 5. Keep Records
Review trade history to improve decision-making

### 6. Test First
Use small amounts initially to verify everything works

### 7. Don't Fight the Bot
Let automated and manual trades complement each other

## Advanced Tips

### Position Sizing Strategy
```
Conservative Portfolio (Risk-Averse):
- 10-15% per trade
- Maximum 2-3 concurrent positions
- Total exposure: 30-45%

Aggressive Portfolio (Risk-Tolerant):
- 25-35% per trade
- Maximum 3-4 concurrent positions
- Total exposure: 75-100%
```

### When to Trade Manually

**Good Times:**
- ✅ Clear breakout patterns forming
- ✅ Major news events (if you act quickly)
- ✅ Bot signal aligns with your analysis
- ✅ Taking profit before bot's take profit level
- ✅ Cutting losses before stop loss hits

**Avoid:**
- ❌ Trading out of FOMO (fear of missing out)
- ❌ Revenge trading after a loss
- ❌ Overriding bot without good reason
- ❌ Trading during high volatility without analysis

## API Endpoints (for Advanced Users)

### Get Status
```bash
GET /api/manual/status
```
Returns current position, balances, and trading availability

### Execute Buy
```bash
POST /api/manual/buy
Content-Type: application/json

{
  "position_size": 0.2
}
```

### Execute Sell
```bash
POST /api/manual/sell
Content-Type: application/json

{
  "position_size": 0.2
}
```

## Security Notes

- All manual trades require dashboard authentication
- Rate limiting prevents abuse
- Same security as rest of dashboard
- Trades logged for audit trail

## Support & Questions

If you encounter issues:
1. Check browser console (F12) for errors
2. Check bot logs for server-side errors
3. Verify configuration in `.env` file
4. Review `MANUAL_TRADING_PLAN.md` for architecture details

## Configuration

Relevant settings in `.env`:
```bash
# Position sizing
BOT_MIN_POSITION_SIZE=0.15
BOT_MAX_POSITION_SIZE=0.35

# Risk management
BOT_STOP_LOSS_PCT=0.025
BOT_TAKE_PROFIT_PCT=0.04
BOT_TRAILING_STOP_PCT=0.015
BOT_USE_TRAILING_STOP=true

# ATR-based stops (recommended)
BOT_USE_ATR_STOPS=true
BOT_ATR_STOP_MULTIPLIER=2.5
```

## Future Enhancements

Planned features:
- [ ] Partial position closes
- [ ] Custom stop loss/take profit for manual trades
- [ ] Limit orders (not just market)
- [ ] Trade scheduling
- [ ] Mobile-optimized interface
- [ ] Keyboard shortcuts (B for buy, S for sell)
- [ ] Trade notes/journal
- [ ] Performance comparison (manual vs automated)

---

**Remember**: Manual trading gives you control, but with control comes responsibility. Use risk management, start small, and trade with a plan!

Happy Trading! 📈💰


