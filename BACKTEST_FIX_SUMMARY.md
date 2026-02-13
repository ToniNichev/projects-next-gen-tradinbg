# Backtest Chart Buy/Sell Display Fix

## Problem Summary
Backtest charts were not showing the correct strategy attribution for SELL (exit) trades. All exit trades appeared with gray markers labeled "Unknown" instead of the strategy colors that opened the position.

## Root Cause
When positions were closed (stop loss, take profit, trailing stop), the exit trades were recorded without `strategy_name` information, causing the backtest chart to:
- Show BUY markers with correct strategy colors ✓
- Show SELL markers as "Unknown" (gray) ✗

## Changes Made

### 1. `paper_trader.py` - Position Tracking
- **Line 51**: Added `strategy_name: Optional[str] = None` field to `Position` dataclass
- **Line 385**: Store strategy name when opening position: `strategy_name=signal.to_dict().get("strategy_name", "Unknown")`
- **Line 320**: Include strategy name in exit trade signal: `signal={"strategy_name": pos.strategy_name}`
- **Line 254**: Save strategy name to database when opening position

### 2. `backtest.py` - Exit Trade Recording
- **Lines 328-348**: Extract strategy name from exit trade signal and include in chart data
- **Lines 448-468**: Same fix for final backtest end exit

### 3. `database.py` - Database Schema
- **Line 103**: Added `strategy_name = Column(String(100), index=True)` to Position table

## Database Migration Required

Since we added a new column to the Position table, you need to handle existing data:

### Option 1: Drop and Recreate (Development/Testing)
```bash
# Backup if needed
cp data/trading.db data/trading.db.backup

# Delete and recreate (will lose position history)
rm data/trading.db
python -c "from database import initialize_database; initialize_database('sqlite:///data/trading.db')"
```

### Option 2: Add Column Manually (Production)
```bash
# Add the column to existing database
sqlite3 data/trading.db "ALTER TABLE positions ADD COLUMN strategy_name VARCHAR(100);"
sqlite3 data/trading.db "CREATE INDEX idx_positions_strategy_name ON positions(strategy_name);"
```

### Option 3: Python Migration Script
```python
from database import get_database
from sqlalchemy import text

db = get_database()
with db.engine.connect() as conn:
    # Check if column exists
    result = conn.execute(text("PRAGMA table_info(positions)"))
    columns = [row[1] for row in result]
    
    if 'strategy_name' not in columns:
        print("Adding strategy_name column...")
        conn.execute(text("ALTER TABLE positions ADD COLUMN strategy_name VARCHAR(100)"))
        conn.execute(text("CREATE INDEX idx_positions_strategy_name ON positions(strategy_name)"))
        conn.commit()
        print("✓ Migration complete!")
    else:
        print("Column already exists, no migration needed.")
```

## Testing

1. **Run a backtest**:
   ```bash
   python backtest.py 7
   ```

2. **Check the chart** in the Dashboard:
   - Navigate to Backtest page
   - Run a backtest with multiple strategies enabled
   - Click "View Chart" on a result
   - Verify both BUY and SELL markers show correct strategy colors

3. **Expected behavior**:
   - BUY markers: Triangle pointing up, colored by strategy
   - SELL markers: Triangle pointing down, SAME color as the BUY that opened it
   - Legend shows all active strategies with their colors
   - Hover over any marker shows strategy name in tooltip

## Strategy Color Reference
- EMA_Crossover: Cyan (#00D9FF)
- RSI_BB_MeanReversion: Pink (#FF6B9D)
- MACD_Volume_Momentum: Gold (#FFD700)
- LLM_Pattern: Purple (#9D4EDD)
- Aggregated (Multi-Strategy): White (#FFFFFF)
- Unknown (fallback): Gray (#808080)

## Verification Checklist
- [ ] Backtest runs without errors
- [ ] Chart shows both BUY and SELL markers
- [ ] SELL markers have strategy colors (not gray)
- [ ] Tooltip shows correct strategy name for exits
- [ ] Legend displays all strategies used
- [ ] Database migration completed (if applicable)
- [ ] No "Unknown" markers for proper strategy exits

## Rollback (if needed)
If issues occur, restore from backup:
```bash
cp data/trading.db.backup data/trading.db
git checkout paper_trader.py backtest.py database.py
```

---
**Author**: Assistant  
**Date**: 2026-02-12  
**Issue**: Backtest charts showing incorrect strategy attribution for exit trades
