# Manual Trading Feature - Implementation Plan

## Overview
Add manual buy/sell functionality to the trading dashboard, allowing users to execute trades manually while maintaining integration with the existing paper trading system.

## Current Architecture Analysis

### Key Components
1. **main.py**: Main bot loop with websocket price feed and trader instance
2. **paper_trader.py**: Handles trade execution with `_buy()` and `_sell()` methods
3. **dashboard.py**: Flask API and UI serving
4. **templates/ui.html**: Dashboard UI with charts and stats
5. **database.py**: SQLAlchemy models for trades and positions

### Current Trade Flow
```
Websocket Price → Strategy Signal → PaperTrader.handle_signal() → _buy()/_sell()
```

### Challenges Identified
- Trader object is in main.py thread scope
- Need thread-safe access to trader
- Must create synthetic signals for manual trades
- Should maintain consistency with automated trading logs

---

## Implementation Plan

### Phase 1: Backend API Endpoints

#### 1.1 Create Global Trader Reference in dashboard.py
**File**: `dashboard.py`

Add global trader reference and lock:
```python
_trader_instance = None
_trader_lock = None

def set_trader(trader, lock):
    """Set the trader instance for manual trading"""
    global _trader_instance, _trader_lock
    _trader_instance = trader
    _trader_lock = lock
```

#### 1.2 Add Manual Trading Endpoints
**File**: `dashboard.py`

Add two new API endpoints:

**POST /api/manual/buy**
- Parameters: `position_size` (optional, default from config)
- Validates current state (not already in long position)
- Gets current market price
- Creates synthetic bullish signal
- Executes buy via trader
- Returns trade result

**POST /api/manual/sell**
- Parameters: `position_size` (optional)
- Validates current state (has position to sell)
- Gets current market price
- Creates synthetic bearish signal or closes position
- Executes sell via trader
- Returns trade result

**GET /api/manual/status**
- Returns current position info
- Returns available balance
- Returns current price
- Returns whether manual trading is allowed

#### 1.3 Integration with main.py
**File**: `main.py`

After creating trader instance:
```python
# Around line 79, after trader creation
from dashboard import set_trader
set_trader(trader, trader_lock)
```

---

### Phase 2: Frontend UI Components

#### 2.1 Manual Trading Panel
**File**: `templates/ui.html`

Add new section after summary cards:

```html
<div class="manual-trading-panel">
  <h2>Manual Trading</h2>
  
  <div class="position-status">
    <h3>Current Position</h3>
    <div id="position-info">
      <!-- Dynamic position info -->
    </div>
  </div>
  
  <div class="trade-controls">
    <div class="control-group">
      <label>Position Size (%)</label>
      <input type="number" id="position-size" min="10" max="100" value="20" step="5">
    </div>
    
    <div class="button-group">
      <button id="buy-btn" class="trade-btn buy-btn">
        🟢 BUY
      </button>
      <button id="sell-btn" class="trade-btn sell-btn">
        🔴 SELL
      </button>
    </div>
  </div>
  
  <div class="trade-preview">
    <div id="trade-estimate">
      <!-- Shows estimated trade details -->
    </div>
  </div>
</div>
```

#### 2.2 JavaScript Functions
Add JavaScript for:
- Fetching current status
- Buy/Sell button handlers
- Confirmation dialogs
- Loading states
- Success/error notifications
- Real-time balance updates

#### 2.3 Styling
Add CSS for:
- Manual trading panel layout
- Button styling (green for buy, red for sell)
- Position status display
- Loading/disabled states
- Success/error messages

---

### Phase 3: Trade Execution Logic

#### 3.1 Create Synthetic Signal Helper
**File**: `dashboard.py`

```python
def create_manual_signal(direction: str, current_price: float) -> dict:
    """Create a synthetic signal for manual trading"""
    from strategy import StrategySignal
    from datetime import datetime, timezone
    
    return StrategySignal(
        direction=direction,
        price=current_price,
        short_ema=current_price,  # Dummy values
        long_ema=current_price,
        trend_strength=0.0,
        timestamp=datetime.now(timezone.utc),
        info={"manual_trade": True},
        stop_loss=calculate_stop_loss(direction, current_price),
        take_profit=calculate_take_profit(direction, current_price),
        position_size=0.0,  # Will be set by caller
        atr=0.0
    )
```

#### 3.2 Manual Buy Implementation
```python
@app.route("/api/manual/buy", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def manual_buy():
    if not _trader_instance:
        return jsonify({"error": "Trader not available"}), 503
    
    try:
        params = request.get_json() or {}
        position_size = params.get("position_size", 0.2)
        
        with _trader_lock:
            # Check if already in position
            if _trader_instance.open_position:
                if _trader_instance.open_position.side == "long":
                    return jsonify({"error": "Already in long position"}), 400
                # If in short, close it first
                
            # Get current price
            current_price = get_current_price()
            
            # Create synthetic signal
            signal = create_manual_signal("bullish", current_price)
            signal.position_size = position_size
            
            # Execute trade
            trade = _trader_instance.handle_signal(signal)
            
            if trade:
                # Update dashboard state
                update_state(
                    balances=_trader_instance.get_balances(),
                    last_trade=trade.to_dict(),
                    price=current_price,
                )
                
                return jsonify({
                    "success": True,
                    "trade": trade.to_dict(),
                    "message": "Buy order executed"
                })
            else:
                return jsonify({"error": "Trade not executed"}), 400
                
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

#### 3.3 Manual Sell Implementation
Similar structure to buy, but handles both closing long positions and opening short positions.

---

### Phase 4: Safety Features

#### 4.1 Pre-Trade Validations
- Check sufficient balance
- Validate position size (min/max)
- Prevent rapid duplicate trades (cooldown)
- Verify market price availability

#### 4.2 User Confirmations
- Show trade preview before execution
- Display estimated costs (fees, slippage)
- Show P&L for position closes
- Confirm with modal dialog

#### 4.3 Position Management
- Display open position clearly
- Show unrealized P&L
- Show stop loss and take profit levels
- Allow adjusting stop loss (future enhancement)

#### 4.4 Trade History
- Mark manual trades distinctly in database
- Add "manual" flag to trade records
- Show manual trades in different color in history

---

### Phase 5: Enhanced Features (Optional)

#### 5.1 Advanced Order Types
- Market orders (current implementation)
- Limit orders (future)
- Custom stop loss / take profit

#### 5.2 Position Sizing Calculator
- Risk-based sizing
- Kelly Criterion
- Fixed dollar amount
- Percentage of portfolio

#### 5.3 Quick Close Button
- One-click position close at market
- Emergency close with confirmation

#### 5.4 Trade Scheduling
- Schedule trade for specific time
- Price alerts for manual intervention

---

## File Changes Summary

### New Files
- None (all changes to existing files)

### Modified Files

1. **dashboard.py**
   - Add `_trader_instance`, `_trader_lock` globals
   - Add `set_trader()` function
   - Add `/api/manual/buy` endpoint
   - Add `/api/manual/sell` endpoint
   - Add `/api/manual/status` endpoint
   - Add `create_manual_signal()` helper
   - Add `get_current_price()` helper

2. **main.py**
   - Import `set_trader` from dashboard
   - Call `set_trader(trader, trader_lock)` after trader initialization

3. **templates/ui.html**
   - Add manual trading panel HTML
   - Add CSS styles for manual trading UI
   - Add JavaScript for trade execution
   - Add confirmation modals
   - Add status update functions

4. **paper_trader.py** (optional enhancements)
   - Add `manual_trade` flag to TradeRecord
   - Track manual vs automated trades separately

5. **database.py** (optional)
   - Add `is_manual` boolean field to Trade model

---

## Implementation Steps

### Step 1: Backend Core
1. Add global trader reference to dashboard.py
2. Create `set_trader()` function
3. Integrate in main.py
4. Add `/api/manual/status` endpoint (read-only, for testing)

### Step 2: Buy Endpoint
1. Implement `/api/manual/buy`
2. Add validation logic
3. Create synthetic signal
4. Test with curl/Postman

### Step 3: Sell Endpoint
1. Implement `/api/manual/sell`
2. Add position closing logic
3. Test with curl/Postman

### Step 4: Frontend UI
1. Add HTML panel to ui.html
2. Add CSS styling
3. Add JavaScript functions
4. Wire up buttons to API

### Step 5: Testing & Polish
1. Test buy flow end-to-end
2. Test sell flow end-to-end
3. Test error cases
4. Add loading states
5. Add success/error notifications

### Step 6: Documentation
1. Update README
2. Add user guide for manual trading
3. Document API endpoints

---

## Risk Considerations

### Technical Risks
- **Thread Safety**: Must use locks when accessing trader
- **Race Conditions**: Multiple rapid clicks could cause issues
- **State Synchronization**: Dashboard state must stay in sync

### Trading Risks
- **Accidental Trades**: Add confirmation dialogs
- **Double Execution**: Implement cooldown/debouncing
- **Position Sizing**: Validate min/max limits

### Security Risks
- **Unauthorized Access**: Use existing auth system
- **Rate Limiting**: Apply strict limits to manual trade endpoints
- **Input Validation**: Sanitize all user inputs

---

## Testing Strategy

### Unit Tests
- Test signal creation
- Test position validation
- Test thread safety

### Integration Tests
- Test full buy flow
- Test full sell flow
- Test error handling

### UI Tests
- Test button states
- Test confirmation dialogs
- Test loading states

### Manual Testing Checklist
- [ ] Buy when no position
- [ ] Buy when in short position (should close first)
- [ ] Sell when in long position
- [ ] Sell when no position (should open short)
- [ ] Insufficient balance error
- [ ] Network error handling
- [ ] Concurrent trade attempts
- [ ] Balance updates correctly
- [ ] Trade logs correctly
- [ ] Position display accurate

---

## Success Criteria

1. ✅ User can manually buy via dashboard button
2. ✅ User can manually sell via dashboard button
3. ✅ Trades execute immediately at market price
4. ✅ Balances update in real-time
5. ✅ Manual trades logged to database
6. ✅ Manual trades visible in trade history
7. ✅ Thread-safe execution with automated trades
8. ✅ Clear error messages for failures
9. ✅ Confirmation dialogs prevent accidents
10. ✅ Position status clearly displayed

---

## Future Enhancements

1. **Mobile-Friendly**: Optimize UI for mobile trading
2. **Keyboard Shortcuts**: Add hotkeys (B for buy, S for sell)
3. **Trade Presets**: Save common trade configurations
4. **Paper Trading Mode**: Practice without real execution
5. **Trade Journal**: Add notes to manual trades
6. **Performance Analytics**: Track manual vs automated performance
7. **WebSocket Updates**: Real-time price and position updates
8. **Push Notifications**: Alert when trades execute

---

## Timeline Estimate

- **Phase 1 (Backend API)**: 2-3 hours
- **Phase 2 (Frontend UI)**: 2-3 hours  
- **Phase 3 (Integration)**: 1-2 hours
- **Phase 4 (Safety)**: 1-2 hours
- **Phase 5 (Testing)**: 2-3 hours

**Total**: 8-13 hours

---

## Questions to Consider

1. Should manual trades bypass strategy filters (RSI, MACD, etc.)?
   - **Recommendation**: Yes, manual should override all filters

2. Should manual trades use dynamic position sizing?
   - **Recommendation**: User can choose, default to config value

3. Should we allow partial position closes?
   - **Recommendation**: Phase 2 feature

4. Should manual trades affect automated trading?
   - **Recommendation**: No, both can coexist

5. Should we track manual vs automated performance separately?
   - **Recommendation**: Yes, add tracking

---

## Notes

- All manual trades should be marked with `"manual": true` in signal info
- Manual trades should respect existing position management (stop loss, take profit)
- The automated trading loop should continue running independently
- Manual trades should appear immediately on the dashboard
- Consider adding a "Manual Trading" section to settings to enable/disable


