"""
Migration script to add strategy_name and signal_confidence columns to trades table.

This adds support for multi-strategy tracking in the database.
"""

import sqlite3
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")


def migrate_database(db_path="data/trading.db"):
    """Add strategy_name and signal_confidence columns to trades table"""
    
    import os
    if not os.path.exists(db_path):
        logging.info(f"⊘ Database does not exist: {db_path} (will be created when needed)")
        return True
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if trades table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cursor.fetchone():
            logging.info(f"⊘ Trades table does not exist in {db_path} (will be created when needed)")
            return True
        
        # Check if strategy_name column exists
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]
        
        needs_strategy_name = "strategy_name" not in columns
        needs_signal_confidence = "signal_confidence" not in columns
        
        if not needs_strategy_name and not needs_signal_confidence:
            logging.info(f"✓ Database already up to date: {db_path}")
            return True
        
        logging.info(f"Migrating database: {db_path}")
        
        # Add strategy_name column if missing
        if needs_strategy_name:
            logging.info("  Adding column: strategy_name")
            cursor.execute("""
                ALTER TABLE trades 
                ADD COLUMN strategy_name VARCHAR(50)
            """)
            logging.info("  ✓ Added strategy_name column")
        
        # Add signal_confidence column if missing
        if needs_signal_confidence:
            logging.info("  Adding column: signal_confidence")
            cursor.execute("""
                ALTER TABLE trades 
                ADD COLUMN signal_confidence FLOAT
            """)
            logging.info("  ✓ Added signal_confidence column")
        
        # Create index on strategy_name if we just added it
        if needs_strategy_name:
            logging.info("  Creating index: idx_strategy_name")
            try:
                cursor.execute("""
                    CREATE INDEX idx_strategy_name ON trades(strategy_name)
                """)
                logging.info("  ✓ Created index on strategy_name")
            except sqlite3.OperationalError as e:
                if "already exists" not in str(e):
                    raise
                logging.info("  ✓ Index already exists")
        
        conn.commit()
        logging.info(f"✓ Migration completed successfully")
        return True
        
    except Exception as e:
        logging.error(f"✗ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()


if __name__ == "__main__":
    # Migrate both trading and backtest databases
    databases = [
        "data/trading.db",
        "data/backtest.db",
    ]
    
    success = True
    for db_path in databases:
        try:
            if not migrate_database(db_path):
                success = False
        except Exception as e:
            logging.error(f"✗ Failed to migrate {db_path}: {e}")
            success = False
    
    if success:
        logging.info("\n" + "="*80)
        logging.info("✓ All databases migrated successfully!")
        logging.info("="*80)
        sys.exit(0)
    else:
        logging.error("\n" + "="*80)
        logging.error("✗ Some databases failed to migrate")
        logging.error("="*80)
        sys.exit(1)
