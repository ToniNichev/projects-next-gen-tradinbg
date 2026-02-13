#!/usr/bin/env python3
"""
Database migration script to add strategy_name column to positions table.

This script safely adds the new column if it doesn't exist.
Run this before using the updated backtest functionality.

Usage:
    python migrate_add_strategy_name.py
"""

import sys
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(message)s")

def migrate():
    """Add strategy_name column to positions table if it doesn't exist"""
    try:
        from database import initialize_database
        
        # Initialize database connection
        print("\n🔧 Database Migration: Add strategy_name to positions")
        print("=" * 60)
        
        db_manager = initialize_database("sqlite:///data/trading.db")
        
        with db_manager.engine.connect() as conn:
            # Check if column already exists
            print("Checking current schema...")
            result = conn.execute(text("PRAGMA table_info(positions)"))
            columns = [row[1] for row in result]
            
            if 'strategy_name' in columns:
                print("✓ Column 'strategy_name' already exists!")
                print("  No migration needed.")
                return True
            
            # Add the column
            print("\nAdding 'strategy_name' column to positions table...")
            conn.execute(text("ALTER TABLE positions ADD COLUMN strategy_name VARCHAR(100)"))
            conn.commit()
            print("✓ Column added successfully!")
            
            # Create index for performance
            print("Creating index on strategy_name...")
            try:
                conn.execute(text("CREATE INDEX idx_positions_strategy_name ON positions(strategy_name)"))
                conn.commit()
                print("✓ Index created successfully!")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print("✓ Index already exists!")
                else:
                    print(f"⚠ Could not create index: {e}")
                    print("  (This is not critical, continuing...)")
            
            # Verify the change
            print("\nVerifying migration...")
            result = conn.execute(text("PRAGMA table_info(positions)"))
            columns = [row[1] for row in result]
            
            if 'strategy_name' in columns:
                print("✓ Migration completed successfully!")
                print("\n" + "=" * 60)
                print("✅ Your database is now ready for the updated backtest!")
                print("\nNext steps:")
                print("  1. Run a backtest: python backtest.py 7")
                print("  2. View the chart in the Dashboard")
                print("  3. Verify SELL markers show strategy colors")
                return True
            else:
                print("✗ Migration verification failed!")
                return False
                
    except ImportError as e:
        print(f"\n✗ Error: Could not import database module")
        print(f"  {e}")
        print("\nMake sure you have:")
        print("  - SQLAlchemy installed: pip install sqlalchemy")
        print("  - database.py in the current directory")
        return False
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("BACKTEST FIX: Strategy Name Migration")
    print("=" * 60)
    
    success = migrate()
    
    if success:
        sys.exit(0)
    else:
        print("\n⚠ Migration encountered issues. Please check the errors above.")
        print("You may need to:")
        print("  - Backup your database: cp data/trading.db data/trading.db.backup")
        print("  - Manually run: sqlite3 data/trading.db \"ALTER TABLE positions ADD COLUMN strategy_name VARCHAR(100);\"")
        sys.exit(1)
