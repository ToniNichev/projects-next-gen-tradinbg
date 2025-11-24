# Database Integration Guide

This guide explains how to use the new SQLite database integration for the trading bot.

## Overview

The bot now supports SQLite database storage for:
- **Trade records** - All buy/sell trades with full details
- **Position tracking** - Historical position open/close events
- **Candle data** - Market data storage (optional)
- **Performance metrics** - Aggregate statistics

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `sqlalchemy>=2.0.0` - Database ORM
- `alembic>=1.12.0` - Database migrations (future use)

### 2. Verify Installation

```bash
python3 test_database.py
```

This will:
- Create a test database at `data/test_trading.db`
- Insert sample trades and positions
- Run queries and verify functionality
- Display statistics

Expected output:
```
✅ ALL TESTS PASSED!
Database file created: data/test_trading.db
```

## Configuration

### Environment Variables

Add to your `.env` file or set as environment variables:

```bash
# Database configuration
BOT_DATABASE_URL=sqlite:///data/trading.db
BOT_ENABLE_DATABASE=true
BOT_ENABLE_CSV_LOGGING=true  # Keep CSV for backward compatibility
```

### Config Options

In `config.py`, the following parameters control database behavior:

```python
database_url: str = "sqlite:///data/trading.db"  # Database location
enable_database: bool = True                     # Enable database logging
enable_csv_logging: bool = True                  # Keep CSV logging
```

## Usage

### Running the Bot

The bot automatically uses the database when enabled:

```bash
python3 main.py
```

You'll see:
```
Database initialized: sqlite:///data/trading.db
```

### Migrating Existing CSV Data

If you have existing trade logs in CSV format, migrate them:

```bash
python3 migrate_csv_to_db.py data/trade_log.csv
```

This will:
- Import all trades from CSV to database
- Preserve all historical data
- Show migration statistics
- Display database summary

Example output:
```
Migration completed!
Trades imported: 150
Trades skipped: 0

Database Statistics:
Total trades in database: 150
Win rate: 52.50%
Total P&L: $342.50
```

### Migrate Backtest Results

```bash
python3 migrate_csv_to_db.py data/backtest_log.csv
```

## API Endpoints

The dashboard now exposes database query endpoints:

### 1. Get Trades

```bash
# Get last 100 trades
curl http://localhost:8000/api/trades

# Filter by side
curl http://localhost:8000/api/trades?side=buy&limit=50

# Filter by exit reason
curl http://localhost:8000/api/trades?exit_reason=stop_loss

# Filter by date range
curl http://localhost:8000/api/trades?days_back=7
```

Response:
```json
{
  "trades": [
    {
      "id": 1,
      "timestamp": "2025-11-22T10:30:00",
      "side": "buy",
      "price": 100000.0,
      "amount": 0.01,
      "pnl": 42.50,
      "exit_reason": "take_profit",
      ...
    }
  ],
  "count": 100
}
```

### 2. Get Statistics

```bash
curl http://localhost:8000/api/stats
```

Response:
```json
{
  "total_trades": 150,
  "winning_trades": 80,
  "losing_trades": 70,
  "win_rate": 53.33,
  "total_pnl": 342.50,
  "avg_pnl": 2.28
}
```

### 3. Get Open Positions

```bash
curl http://localhost:8000/api/positions
```

Response:
```json
{
  "positions": [
    {
      "id": 5,
      "side": "long",
      "entry_price": 98500.0,
      "entry_time": "2025-11-22T12:00:00",
      "amount": 0.01,
      "stop_loss": 96575.0,
      "take_profit": 102440.0,
      "trailing_stop": 97025.0
    }
  ],
  "count": 1
}
```

### 4. Get Performance Metrics

```bash
curl http://localhost:8000/api/performance
```

Response:
```json
{
  "total_trades": 150,
  "win_rate": 53.33,
  "total_pnl": 342.50,
  "avg_pnl": 2.28,
  "avg_win": 8.50,
  "avg_loss": -5.20,
  "profit_factor": 1.63,
  "recent_trades_count": 100
}
```

## Database Schema

### trades Table

Stores individual trade records:

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| timestamp | DateTime | Trade timestamp |
| side | String | buy/sell |
| price | Float | Execution price |
| amount | Float | Trade amount |
| notional | Float | Total value |
| fee | Float | Trading fee |
| slippage | Float | Slippage amount |
| pnl | Float | Profit/loss |
| exit_reason | String | stop_loss, take_profit, etc. |
| signal_direction | String | bullish/bearish/neutral |
| rsi | Float | RSI at trade time |
| atr | Float | ATR at trade time |
| ... | ... | More fields |

**Indexes:**
- `timestamp` - Fast time-based queries
- `side` - Filter by buy/sell
- `exit_reason` - Filter by exit type
- `pnl` - Sort by profitability

### positions Table

Tracks position lifecycle:

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| side | String | long/short |
| entry_price | Float | Entry price |
| entry_time | DateTime | Open time |
| exit_price | Float | Exit price |
| exit_time | DateTime | Close time |
| amount | Float | Position size |
| stop_loss | Float | Stop loss level |
| take_profit | Float | Take profit level |
| trailing_stop | Float | Trailing stop level |
| exit_reason | String | Why closed |
| pnl | Float | Profit/loss |
| pnl_percent | Float | P&L percentage |
| is_open | Boolean | Currently open |

### candles Table

Optional market data storage:

| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| symbol | String | BTC/USDT, etc. |
| timeframe | String | 1m, 5m, 1h, etc. |
| timestamp | DateTime | Candle time |
| open | Float | Open price |
| high | Float | High price |
| low | Float | Low price |
| close | Float | Close price |
| volume | Float | Volume |
| ema_short | Float | Short EMA (optional) |
| ema_long | Float | Long EMA (optional) |
| rsi | Float | RSI (optional) |
| atr | Float | ATR (optional) |

**Unique constraint:** (symbol, timeframe, timestamp)

## Querying the Database

### Using Python

```python
from database import get_database

# Get database instance
db = get_database()

# Query trades
recent_trades = db.get_trades(limit=50)
buy_trades = db.get_trades(side="buy", limit=100)
stop_losses = db.get_trades(exit_reason="stop_loss")

# Get statistics
stats = db.get_trade_stats()
print(f"Win rate: {stats['win_rate']:.2f}%")
print(f"Total P&L: ${stats['total_pnl']:.2f}")

# Get open positions
open_positions = db.get_open_positions()
for pos in open_positions:
    print(f"Open {pos.side} at {pos.entry_price}")
```

### Using SQLite CLI

```bash
# Open database
sqlite3 data/trading.db

# List tables
.tables

# View recent trades
SELECT timestamp, side, price, pnl, exit_reason 
FROM trades 
ORDER BY timestamp DESC 
LIMIT 10;

# Calculate win rate
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
FROM trades 
WHERE pnl IS NOT NULL;

# Exit
.quit
```

## Backward Compatibility

### Dual Mode Operation

The bot can run in dual mode with both CSV and database logging:

```python
enable_database=True       # Log to database
enable_csv_logging=True    # Also log to CSV
```

This ensures:
- No disruption to existing workflows
- Easy rollback if needed
- Data redundancy

### CSV-Only Mode

To disable database and use only CSV:

```bash
BOT_ENABLE_DATABASE=false
BOT_ENABLE_CSV_LOGGING=true
```

## Backup & Maintenance

### Backup Database

```bash
# Simple copy
cp data/trading.db data/trading_backup_$(date +%Y%m%d).db

# Or use SQLite backup
sqlite3 data/trading.db ".backup data/trading_backup.db"
```

### Database Size

SQLite databases are efficient:
- ~1 KB per trade
- 10,000 trades ≈ 10 MB
- 100,000 trades ≈ 100 MB

### Vacuum Database

To reclaim space after deletions:

```bash
sqlite3 data/trading.db "VACUUM;"
```

## Troubleshooting

### Issue: Module not found

```
ModuleNotFoundError: No module named 'sqlalchemy'
```

**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: Database locked

```
sqlite3.OperationalError: database is locked
```

**Solution:**
- Only one writer at a time (this is handled automatically)
- If bot crashed, remove lock file:
  ```bash
  rm data/trading.db-journal
  ```

### Issue: Migration fails

```
Failed to save trade to database: ...
```

**Solution:**
- Check database file permissions
- Verify data/ directory exists
- Check CSV format matches expected columns

### Issue: Old CSV format

If your CSV doesn't have `exit_reason` or `pnl` columns:

1. The migration script will still work (fills None)
2. Or manually add columns to CSV:
   ```bash
   # Add headers if missing
   sed -i '1s/$/,exit_reason,pnl/' data/trade_log.csv
   ```

## Advanced Usage

### Custom Queries

Create custom analysis scripts:

```python
from database import get_database
from datetime import datetime, timedelta

db = get_database()

# Trades in last 24 hours
yesterday = datetime.utcnow() - timedelta(days=1)
recent = db.get_trades(start_date=yesterday)

# Group by exit reason
from collections import Counter
exit_reasons = Counter(t.exit_reason for t in recent if t.exit_reason)
print(exit_reasons)
# {'take_profit': 15, 'stop_loss': 10, 'signal': 8}

# Calculate profit factor by time of day
morning_trades = [t for t in recent if 6 <= t.timestamp.hour < 12]
afternoon_trades = [t for t in recent if 12 <= t.timestamp.hour < 18]
```

### Exporting Data

```python
import pandas as pd
from database import get_database

db = get_database()

# Export to CSV
with db.get_session() as session:
    trades = session.query(Trade).all()
    df = pd.DataFrame([{
        'timestamp': t.timestamp,
        'side': t.side,
        'price': t.price,
        'pnl': t.pnl,
        'exit_reason': t.exit_reason
    } for t in trades])
    df.to_csv('export.csv', index=False)
```

## Next Steps

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Test database**: `python3 test_database.py`
3. **Migrate old data**: `python3 migrate_csv_to_db.py data/trade_log.csv`
4. **Start bot**: `python3 main.py`
5. **Query API**: Visit `http://localhost:8000/api/stats`

## Benefits

✅ **Fast queries** - SQL indexes make queries instant  
✅ **Complex analytics** - JOIN tables, aggregate data  
✅ **Data integrity** - Foreign keys, constraints, transactions  
✅ **Easy backup** - Single .db file  
✅ **Standard tools** - Any SQLite client works  
✅ **Future-proof** - Easy to add new features  

---

**Database file location**: `data/trading.db`  
**Test database**: Run `python3 test_database.py`  
**API docs**: See API Endpoints section above  
**Support**: Check logs for detailed error messages









