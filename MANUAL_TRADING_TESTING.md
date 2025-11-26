# Manual Trading - Testing Checklist

## Pre-Testing Setup

### 1. Start the Bot
```bash
python main.py
```

### 2. Access Dashboard
Navigate to: `http://localhost:8000/ui`

### 3. Verify Manual Trading Panel
- [ ] Manual trading panel visible below summary cards
- [ ] Three sections present: Position Status, Trade Controls, Trade Estimate
- [ ] Buy and Sell buttons visible
- [ ] Position size input field present

---

## Backend API Tests

### Test 1: Status Endpoint
```bash
curl -X GET http://localhost:8000/api/manual/status \
  -u admin:your_password
```

**Expected Response:**
```json
{
  "available": true,
  "current_price": 50000.00,
  "balances": {
    "USDT": 1000.0,
    "BASE": 0.0
  },
  "portfolio_value": 1000.0,
  "position": null,
  "can_buy": true,
  "can_sell": false
}
```

**Checklist:**
- [ ] Returns 200 OK status
- [ ] `available` is true
- [ ] Current price is accurate
- [ ] Balances match initial config
- [ ] `can_buy` is true when USDT > 0
- [ ] `can_sell` is false when no position

---

### Test 2: Buy Endpoint (No Position)
```bash
curl -X POST http://localhost:8000/api/manual/buy \
  -H "Content-Type: application/json" \
  -u admin:your_password \
  -d '{"position_size": 0.2}'
```

**Expected Response:**
```json
{
  "success": true,
  "trade": {
    "side": "buy",
    "price": 50025.0,
    "amount": 0.004,
    "notional": 200.0,
    "fee": 0.15,
    ...
  },
  "message": "Buy order executed successfully",
  "balances": {
    "USDT": 799.85,
    "BASE": 0.004
  }
}
```

**Checklist:**
- [ ] Returns 200 OK status
- [ ] `success` is true
- [ ] Trade object contains all fields
- [ ] USDT balance decreased correctly
- [ ] BASE balance increased
- [ ] Fee calculated (0.075% default)
- [ ] Slippage applied
- [ ] Trade logged to database

---

### Test 3: Sell Endpoint (With Long Position)
```bash
curl -X POST http://localhost:8000/api/manual/sell \
  -H "Content-Type: application/json" \
  -u admin:your_password \
  -d '{}'
```

**Expected Response:**
```json
{
  "success": true,
  "trade": {
    "side": "sell",
    "price": 49975.0,
    "exit_reason": "manual",
    "pnl": -2.5,
    ...
  },
  "message": "Position closed successfully",
  "balances": {
    "USDT": 997.5,
    "BASE": 0.0
  }
}
```

**Checklist:**
- [ ] Returns 200 OK status
- [ ] Position closed successfully
- [ ] P&L calculated correctly
- [ ] USDT balance updated
- [ ] BASE balance back to 0
- [ ] Exit reason is "manual"

---

### Test 4: Validation - Buy When Already Long
```bash
# First buy
curl -X POST http://localhost:8000/api/manual/buy \
  -H "Content-Type: application/json" \
  -u admin:your_password \
  -d '{"position_size": 0.2}'

# Try to buy again (should fail)
curl -X POST http://localhost:8000/api/manual/buy \
  -H "Content-Type: application/json" \
  -u admin:your_password \
  -d '{"position_size": 0.2}'
```

**Expected Response (Second Call):**
```json
{
  "error": "Already in long position"
}
```

**Checklist:**
- [ ] Second buy returns 400 status
- [ ] Error message is clear
- [ ] No duplicate position created

---

### Test 5: Validation - Position Size Limits
```bash
# Too small
curl -X POST http://localhost:8000/api/manual/buy \
  -H "Content-Type: application/json" \
  -u admin:your_password \
  -d '{"position_size": 0.05}'

# Too large
curl -X POST http://localhost:8000/api/manual/buy \
  -H "Content-Type: application/json" \
  -u admin:your_password \
  -d '{"position_size": 0.95}'
```

**Expected Responses:**
```json
{
  "error": "Position size too small (min: 15%)"
}
```
```json
{
  "error": "Position size too large (max: 35%)"
}
```

**Checklist:**
- [ ] Minimum size validation works (default 15%)
- [ ] Maximum size validation works (default 35%)
- [ ] Error messages are descriptive

---

### Test 6: Rate Limiting
```bash
# Execute 15 rapid requests
for i in {1..15}; do
  curl -X GET http://localhost:8000/api/manual/status \
    -u admin:your_password
done
```

**Expected Behavior:**
- First ~10 requests succeed (200 OK)
- Subsequent requests return 429 (Too Many Requests)

**Checklist:**
- [ ] Rate limiting active (10 per minute for trades)
- [ ] Returns 429 status when exceeded
- [ ] Limit resets after 1 minute

---

## Frontend UI Tests

### Test 7: Initial Page Load
**Actions:**
1. Open dashboard in browser
2. Observe manual trading panel

**Checklist:**
- [ ] Panel renders correctly
- [ ] No console errors (F12)
- [ ] Position status loads ("No open position")
- [ ] Trade estimate shows current price
- [ ] Buy button enabled
- [ ] Sell button disabled
- [ ] Position size input has default value (20)

---

### Test 8: Buy Flow (Happy Path)
**Actions:**
1. Set position size to 25%
2. Click "Buy" button
3. Review confirmation modal
4. Click "Confirm"

**Checklist:**
- [ ] Position size input updates preview
- [ ] Trade estimate recalculates
- [ ] Buy button clickable
- [ ] Confirmation modal appears
- [ ] Modal shows correct details (price, amount, value)
- [ ] "Processing..." spinner shows during execution
- [ ] Success notification appears (green)
- [ ] Position status updates immediately
- [ ] Balance updates in summary cards
- [ ] Buy button becomes disabled
- [ ] Sell button becomes enabled
- [ ] Modal closes automatically

---

### Test 9: Sell Flow (Happy Path)
**Actions:**
1. With open long position
2. Click "Sell" button
3. Review confirmation modal (shows P&L)
4. Click "Confirm"

**Checklist:**
- [ ] Sell button clickable when position exists
- [ ] Confirmation modal shows position details
- [ ] Unrealized P&L displayed (green/red)
- [ ] Entry price shown
- [ ] Current price shown
- [ ] Success notification appears
- [ ] Position status shows "No open position"
- [ ] Balance updates correctly
- [ ] P&L reflected in balance change
- [ ] Sell button becomes disabled
- [ ] Buy button becomes enabled

---

### Test 10: Cancel Trade
**Actions:**
1. Click "Buy" button
2. Review confirmation modal
3. Click "Cancel"

**Checklist:**
- [ ] Modal closes
- [ ] No trade executed
- [ ] Balance unchanged
- [ ] Position unchanged

---

### Test 11: Error Handling
**Actions:**
1. Stop the bot (Ctrl+C)
2. Try to execute a trade from dashboard

**Expected Behavior:**
- Error notification: "Trader not available"
- Red notification displayed
- No trade executed

**Checklist:**
- [ ] Error caught gracefully
- [ ] User-friendly error message
- [ ] Red notification displayed
- [ ] UI remains functional

---

### Test 12: Real-Time Updates
**Actions:**
1. Open long position
2. Wait and observe updates
3. Watch position panel

**Checklist:**
- [ ] Current price updates every 5 seconds
- [ ] Unrealized P&L updates automatically
- [ ] Balance reflects current position value
- [ ] No console errors during updates
- [ ] Updates don't cause UI flicker

---

### Test 13: Modal Overlay Click
**Actions:**
1. Click "Buy" button
2. Click outside modal (on dark overlay)

**Checklist:**
- [ ] Modal closes when overlay clicked
- [ ] No trade executed

---

### Test 14: Position Size Input Validation
**Actions:**
1. Type "5" in position size input
2. Type "150" in position size input
3. Type "-20" in position size input

**Checklist:**
- [ ] Input accepts only numbers
- [ ] Min value respected (10)
- [ ] Max value respected (100)
- [ ] Negative values prevented
- [ ] Preview updates on valid input

---

### Test 15: Multiple Quick Clicks
**Actions:**
1. Click "Buy" button
2. Quickly click "Confirm" multiple times

**Checklist:**
- [ ] Only one trade executed
- [ ] Button disables after first click
- [ ] No duplicate trades created
- [ ] Spinner prevents re-clicks

---

## Integration Tests

### Test 16: Manual + Automated Trading
**Actions:**
1. Let bot run and open a position
2. Manually close that position
3. Wait for bot to detect

**Checklist:**
- [ ] Bot respects manual close
- [ ] Bot can open new position after manual close
- [ ] No position conflicts
- [ ] Both trades logged correctly
- [ ] Thread-safe execution (no crashes)

---

### Test 17: Database Logging
**Actions:**
1. Execute several manual trades
2. Check database:
```bash
sqlite3 data/trading.db
SELECT * FROM trades WHERE signal_direction IS NULL OR signal_direction = 'manual' LIMIT 10;
```

**Checklist:**
- [ ] Manual trades logged to database
- [ ] All fields populated (price, amount, fee, etc.)
- [ ] Timestamp accurate
- [ ] P&L calculated for closes
- [ ] Exit reason is "manual"

---

### Test 18: CSV Logging (if enabled)
**Actions:**
1. Execute manual trades
2. Check `data/trade_log.csv`

**Checklist:**
- [ ] Manual trades appear in CSV
- [ ] All columns populated
- [ ] Format consistent with automated trades

---

## Performance Tests

### Test 19: Concurrent Operations
**Actions:**
1. Execute manual trade while bot is processing signal
2. Update multiple UI elements simultaneously

**Checklist:**
- [ ] No race conditions
- [ ] No deadlocks
- [ ] UI remains responsive
- [ ] Both operations complete successfully

---

### Test 20: Long-Running Session
**Actions:**
1. Leave dashboard open for 30 minutes
2. Execute trades periodically
3. Monitor for issues

**Checklist:**
- [ ] No memory leaks
- [ ] Updates continue working
- [ ] No connection timeouts
- [ ] UI remains responsive
- [ ] All features functional

---

## Edge Cases

### Test 21: Zero Balance
**Actions:**
1. Manually trade until USDT balance ≈ $0
2. Try to buy

**Checklist:**
- [ ] Error: "Insufficient USDT balance"
- [ ] Buy button disabled
- [ ] Graceful error handling

---

### Test 22: Extreme Position Sizes
**Actions:**
1. Set position size to 10% (minimum)
2. Execute buy
3. Close position
4. Set position size to 100% (maximum)
5. Execute buy

**Checklist:**
- [ ] Minimum size executes correctly
- [ ] Maximum size executes correctly
- [ ] Small position values handled (no rounding errors)
- [ ] Large position values handled

---

### Test 23: Price Volatility
**Actions:**
1. Execute trades during high volatility
2. Check slippage impact

**Checklist:**
- [ ] Trades execute even in volatile market
- [ ] Slippage applied correctly (0.05% default)
- [ ] Stop loss/take profit set appropriately

---

### Test 24: Browser Refresh
**Actions:**
1. Open position
2. Refresh browser (F5)
3. Observe state

**Checklist:**
- [ ] Position persists after refresh
- [ ] Status loads correctly
- [ ] All data accurate
- [ ] UI functional immediately

---

### Test 25: Multiple Browser Tabs
**Actions:**
1. Open dashboard in two tabs
2. Execute trade in tab 1
3. Observe tab 2

**Checklist:**
- [ ] Tab 2 reflects changes (after next update cycle)
- [ ] No conflicts between tabs
- [ ] Both tabs remain functional

---

## Security Tests

### Test 26: Unauthenticated Access
```bash
curl -X POST http://localhost:8000/api/manual/buy \
  -H "Content-Type: application/json" \
  -d '{"position_size": 0.2}'
```

**Expected Response:**
```
401 Unauthorized
```

**Checklist:**
- [ ] Returns 401 without auth
- [ ] No trade executed
- [ ] Authentication required

---

### Test 27: SQL Injection Attempt
```bash
curl -X POST http://localhost:8000/api/manual/buy \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{"position_size": "0.2; DROP TABLE trades;--"}'
```

**Checklist:**
- [ ] Input sanitized
- [ ] Database not affected
- [ ] Error returned (invalid input)

---

### Test 28: XSS Attempt
**Actions:**
1. Try to inject script in position size
2. Check notification display

**Checklist:**
- [ ] Scripts not executed
- [ ] Input escaped properly
- [ ] No security vulnerabilities

---

## Mobile/Responsive Tests

### Test 29: Mobile View
**Actions:**
1. Open dashboard on mobile device or resize browser to 375px width
2. Test all manual trading features

**Checklist:**
- [ ] Manual trading panel responsive
- [ ] Grid layouts stack vertically
- [ ] Buttons remain clickable
- [ ] Modal displays correctly
- [ ] Text readable (no overflow)
- [ ] Touch interactions work

---

## Final Checklist

### Documentation
- [x] MANUAL_TRADING_PLAN.md created
- [x] MANUAL_TRADING_GUIDE.md created
- [x] MANUAL_TRADING_TESTING.md created
- [ ] README.md updated with feature mention

### Code Quality
- [x] Backend endpoints implemented
- [x] Frontend UI implemented
- [x] Thread safety ensured
- [x] Error handling comprehensive
- [x] No linter errors (only import warnings)

### Functionality
- [ ] Buy orders work correctly
- [ ] Sell orders work correctly
- [ ] Position tracking accurate
- [ ] P&L calculation correct
- [ ] Stop loss/take profit set

### User Experience
- [ ] UI intuitive and clear
- [ ] Confirmations prevent accidents
- [ ] Notifications informative
- [ ] Real-time updates smooth
- [ ] Mobile-friendly

### Integration
- [ ] Works with automated trading
- [ ] Database logging functional
- [ ] CSV logging functional (if enabled)
- [ ] No conflicts or race conditions

### Security
- [ ] Authentication enforced
- [ ] Rate limiting active
- [ ] Input validation thorough
- [ ] No vulnerabilities found

---

## Test Results Summary

**Date**: _____________

**Tester**: _____________

**Total Tests**: 29

**Passed**: _____

**Failed**: _____

**Notes**:
```
[Add any additional notes, issues, or observations here]
```

---

## Known Issues

_(Document any known issues discovered during testing)_

1. 
2. 
3. 

---

## Next Steps

After completing testing:
1. [ ] Fix any critical bugs
2. [ ] Update README.md with new feature
3. [ ] Create demo video/screenshots
4. [ ] Deploy to production
5. [ ] Monitor for issues in production
6. [ ] Gather user feedback

---

**Testing Complete!** ✅

Once all tests pass, the manual trading feature is ready for production use.


