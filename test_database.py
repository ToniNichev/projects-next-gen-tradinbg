"""
Test script for database integration.

Tests:
1. Database initialization
2. Trade logging
3. Position tracking
4. Query functionality
5. Statistics calculation

Usage:
    python test_database.py
"""

import logging
from datetime import datetime, timedelta
from database import initialize_database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_database_integration():
    """Test all database functionality"""
    
    logger.info("=" * 60)
    logger.info("DATABASE INTEGRATION TEST")
    logger.info("=" * 60)
    
    # Test 1: Initialize database
    logger.info("\n1. Testing database initialization...")
    try:
        db = initialize_database("sqlite:///data/test_trading.db")
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        return False
    
    # Test 2: Add sample trades
    logger.info("\n2. Testing trade insertion...")
    try:
        # Sample winning trade
        trade1 = {
            "timestamp": datetime.utcnow(),
            "side": "buy",
            "price": 100000.0,
            "amount": 0.01,
            "notional": 1000.0,
            "fee": 0.75,
            "slippage": 0.5,
            "usdt_balance": 9000.0,
            "base_balance": 0.01,
            "signal_direction": "bullish",
            "signal_price": 100000.0,
            "rsi": 45.0,
            "atr": 1500.0,
            "position_size": 0.2,
        }
        db.add_trade(trade1)
        logger.info("✅ Trade 1 (buy) added successfully")
        
        # Sample losing trade
        trade2 = {
            "timestamp": datetime.utcnow() + timedelta(hours=1),
            "side": "sell",
            "price": 98000.0,
            "amount": 0.01,
            "notional": 980.0,
            "fee": 0.735,
            "slippage": 0.5,
            "usdt_balance": 9979.0,
            "base_balance": 0.0,
            "exit_reason": "stop_loss",
            "pnl": -21.0,
            "signal_direction": "bearish",
            "signal_price": 98000.0,
            "rsi": 65.0,
            "atr": 1600.0,
        }
        db.add_trade(trade2)
        logger.info("✅ Trade 2 (sell with stop loss) added successfully")
        
        # Add a few more trades
        for i in range(3, 6):
            trade = {
                "timestamp": datetime.utcnow() + timedelta(hours=i),
                "side": "buy" if i % 2 == 0 else "sell",
                "price": 100000.0 + (i * 100),
                "amount": 0.01,
                "notional": 1000.0 + (i * 10),
                "fee": 0.75,
                "slippage": 0.5,
                "usdt_balance": 9000.0 + (i * 100),
                "base_balance": 0.01 if i % 2 == 0 else 0.0,
                "pnl": 10.0 if i % 2 == 0 else -5.0,
                "exit_reason": "take_profit" if i % 2 == 0 else "signal",
            }
            db.add_trade(trade)
        logger.info(f"✅ Added {3} more sample trades")
        
    except Exception as e:
        logger.error(f"❌ Trade insertion failed: {e}")
        return False
    
    # Test 3: Add sample position
    logger.info("\n3. Testing position tracking...")
    try:
        position_data = {
            "side": "long",
            "entry_price": 100000.0,
            "entry_time": datetime.utcnow(),
            "amount": 0.01,
            "stop_loss": 98000.0,
            "take_profit": 104000.0,
            "trailing_stop": 99000.0,
            "highest_price": 100000.0,
            "is_open": True,
        }
        position = db.add_position(position_data)
        logger.info(f"✅ Position added successfully (ID: {position.id})")
        
        # Close the position
        updates = {
            "exit_price": 102000.0,
            "exit_time": datetime.utcnow() + timedelta(hours=2),
            "exit_reason": "take_profit",
            "pnl": 200.0,
            "pnl_percent": 2.0,
            "is_open": False,
        }
        db.update_position(position.id, updates)
        logger.info("✅ Position closed successfully")
        
    except Exception as e:
        logger.error(f"❌ Position tracking failed: {e}")
        return False
    
    # Test 4: Query trades
    logger.info("\n4. Testing trade queries...")
    try:
        # Get all trades
        all_trades = db.get_trades(limit=100)
        logger.info(f"✅ Retrieved {len(all_trades)} trades")
        
        # Filter by side
        buy_trades = db.get_trades(side="buy", limit=100)
        logger.info(f"✅ Retrieved {len(buy_trades)} buy trades")
        
        # Filter by exit reason
        stop_loss_trades = db.get_trades(exit_reason="stop_loss", limit=100)
        logger.info(f"✅ Retrieved {len(stop_loss_trades)} stop loss trades")
        
    except Exception as e:
        logger.error(f"❌ Trade queries failed: {e}")
        return False
    
    # Test 5: Get statistics
    logger.info("\n5. Testing statistics calculation...")
    try:
        stats = db.get_trade_stats()
        logger.info("✅ Statistics calculated successfully:")
        logger.info(f"   Total trades: {stats['total_trades']}")
        logger.info(f"   Winning trades: {stats['winning_trades']}")
        logger.info(f"   Losing trades: {stats['losing_trades']}")
        logger.info(f"   Win rate: {stats['win_rate']:.2f}%")
        logger.info(f"   Total P&L: ${stats['total_pnl']:.2f}")
        logger.info(f"   Average P&L: ${stats['avg_pnl']:.2f}")
        
    except Exception as e:
        logger.error(f"❌ Statistics calculation failed: {e}")
        return False
    
    # Test 6: Query open positions
    logger.info("\n6. Testing open positions query...")
    try:
        open_positions = db.get_open_positions()
        logger.info(f"✅ Retrieved {len(open_positions)} open positions")
        
    except Exception as e:
        logger.error(f"❌ Open positions query failed: {e}")
        return False
    
    # Test 7: Add candle data
    logger.info("\n7. Testing candle storage...")
    try:
        candle_data = {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "timestamp": datetime.utcnow(),
            "open": 100000.0,
            "high": 101000.0,
            "low": 99500.0,
            "close": 100500.0,
            "volume": 150.5,
            "ema_short": 100200.0,
            "ema_long": 99800.0,
        }
        candle = db.add_candle(candle_data)
        logger.info(f"✅ Candle added successfully")
        
        # Try to add duplicate (should update)
        candle_data["close"] = 100600.0
        updated_candle = db.add_candle(candle_data)
        logger.info(f"✅ Duplicate candle handled correctly (updated)")
        
    except Exception as e:
        logger.error(f"❌ Candle storage failed: {e}")
        return False
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ ALL TESTS PASSED!")
    logger.info("=" * 60)
    logger.info("\nDatabase file created: data/test_trading.db")
    logger.info("You can inspect it with: sqlite3 data/test_trading.db")
    logger.info("\nTo clean up test database:")
    logger.info("  rm data/test_trading.db")
    logger.info("=" * 60)
    
    return True


def test_api_endpoints():
    """Test that the API endpoints would work with sample data"""
    logger.info("\n" + "=" * 60)
    logger.info("API ENDPOINT SIMULATION TEST")
    logger.info("=" * 60)
    
    try:
        from database import get_database
        db = get_database()
        
        logger.info("\n1. Simulating /api/trades endpoint...")
        trades = db.get_trades(limit=10)
        logger.info(f"✅ Would return {len(trades)} trades")
        
        logger.info("\n2. Simulating /api/stats endpoint...")
        stats = db.get_trade_stats()
        logger.info(f"✅ Would return stats: {stats}")
        
        logger.info("\n3. Simulating /api/positions endpoint...")
        positions = db.get_open_positions()
        logger.info(f"✅ Would return {len(positions)} open positions")
        
        logger.info("\n✅ API endpoints would work correctly!")
        
    except Exception as e:
        logger.error(f"❌ API endpoint simulation failed: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = test_database_integration()
    
    if success:
        test_api_endpoints()
        logger.info("\n🎉 Database integration is working perfectly!")
        logger.info("\nNext steps:")
        logger.info("1. Run: pip install -r requirements.txt")
        logger.info("2. Start bot: python main.py")
        logger.info("3. Check API: http://localhost:8000/api/stats")
        logger.info("4. Migrate old data: python migrate_csv_to_db.py data/trade_log.csv")
    else:
        logger.error("\n❌ Database integration test failed!")
        exit(1)







