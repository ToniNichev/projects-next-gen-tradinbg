"""
CSV to Database Migration Script

Imports existing CSV trade logs into the SQLite database.
Preserves all historical data and allows querying through the database.

Usage:
    python migrate_csv_to_db.py [csv_file_path] [database_url]
    
Example:
    python migrate_csv_to_db.py data/trade_log.csv sqlite:///data/trading.db
"""

import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

from database import initialize_database, DatabaseManager


def parse_timestamp(timestamp_str: str) -> datetime:
    """
    Parse timestamp from CSV (handles multiple formats).
    
    Args:
        timestamp_str: Timestamp string from CSV
        
    Returns:
        datetime object
    """
    # Try ISO format first
    try:
        return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Unable to parse timestamp: {timestamp_str}")


def migrate_csv_to_database(csv_file: str, database_url: str = "sqlite:///data/trading.db") -> dict:
    """
    Migrate CSV trade log to database.
    
    Args:
        csv_file: Path to CSV file
        database_url: SQLAlchemy database URL
        
    Returns:
        Dictionary with migration statistics
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    logger = logging.getLogger(__name__)
    
    # Check if CSV file exists
    csv_path = Path(csv_file)
    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_file}")
        return {"error": "CSV file not found"}
    
    # Initialize database
    logger.info(f"Initializing database: {database_url}")
    db = initialize_database(database_url)
    
    # Read CSV file
    logger.info(f"Reading CSV file: {csv_file}")
    trades_imported = 0
    trades_skipped = 0
    errors = []
    
    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            
            # Check if CSV has expected columns
            expected_columns = {'timestamp', 'side', 'price', 'amount', 'notional', 'fee'}
            if not expected_columns.issubset(set(reader.fieldnames)):
                logger.error(f"CSV missing required columns. Expected: {expected_columns}")
                logger.error(f"Found: {reader.fieldnames}")
                return {"error": "Invalid CSV format"}
            
            for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
                try:
                    # Parse timestamp
                    timestamp = parse_timestamp(row['timestamp'])
                    
                    # Prepare trade data
                    trade_data = {
                        'timestamp': timestamp,
                        'side': row['side'],
                        'price': float(row['price']),
                        'amount': float(row['amount']),
                        'notional': float(row['notional']),
                        'fee': float(row['fee']),
                        'slippage': float(row.get('slippage', 0.0)),
                        'usdt_balance': float(row.get('usdt_balance', 0.0)),
                        'base_balance': float(row.get('base_balance', 0.0)),
                        'exit_reason': row.get('exit_reason') or None,
                        'pnl': float(row['pnl']) if row.get('pnl') and row['pnl'] != '' else None,
                    }
                    
                    # Add to database
                    db.add_trade(trade_data)
                    trades_imported += 1
                    
                    if trades_imported % 100 == 0:
                        logger.info(f"Imported {trades_imported} trades...")
                    
                except Exception as e:
                    trades_skipped += 1
                    error_msg = f"Row {row_num}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(f"Skipped row {row_num}: {e}")
        
        logger.info("=" * 60)
        logger.info("Migration completed!")
        logger.info(f"Trades imported: {trades_imported}")
        logger.info(f"Trades skipped: {trades_skipped}")
        
        if errors:
            logger.info(f"Errors encountered: {len(errors)}")
            logger.info("First 5 errors:")
            for error in errors[:5]:
                logger.info(f"  - {error}")
        
        # Get final statistics
        stats = db.get_trade_stats()
        logger.info("=" * 60)
        logger.info("Database Statistics:")
        logger.info(f"Total trades in database: {stats['total_trades']}")
        logger.info(f"Winning trades: {stats['winning_trades']}")
        logger.info(f"Losing trades: {stats['losing_trades']}")
        logger.info(f"Win rate: {stats['win_rate']:.2f}%")
        logger.info(f"Total P&L: ${stats['total_pnl']:.2f}")
        logger.info(f"Average P&L: ${stats['avg_pnl']:.2f}")
        logger.info("=" * 60)
        
        return {
            "success": True,
            "trades_imported": trades_imported,
            "trades_skipped": trades_skipped,
            "errors": len(errors),
            "database_stats": stats,
        }
    
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {"error": str(e)}


def migrate_backtest_csv(csv_file: str = "data/backtest_log.csv", database_url: str = "sqlite:///data/trading.db"):
    """
    Migrate backtest CSV to database (separate table or marked differently).
    
    This is similar to migrate_csv_to_database but could be extended
    to store backtest results in a separate table or with a flag.
    """
    return migrate_csv_to_database(csv_file, database_url)


def main():
    """Main entry point for migration script"""
    if len(sys.argv) < 2:
        print("Usage: python migrate_csv_to_db.py <csv_file> [database_url]")
        print()
        print("Examples:")
        print("  python migrate_csv_to_db.py data/trade_log.csv")
        print("  python migrate_csv_to_db.py data/backtest_log.csv sqlite:///data/trading.db")
        print()
        sys.exit(1)
    
    csv_file = sys.argv[1]
    database_url = sys.argv[2] if len(sys.argv) > 2 else "sqlite:///data/trading.db"
    
    result = migrate_csv_to_database(csv_file, database_url)
    
    if "error" in result:
        print(f"Migration failed: {result['error']}")
        sys.exit(1)
    else:
        print(f"\n✅ Migration successful!")
        print(f"   Imported: {result['trades_imported']} trades")
        if result['trades_skipped'] > 0:
            print(f"   Skipped: {result['trades_skipped']} trades")


if __name__ == "__main__":
    main()


