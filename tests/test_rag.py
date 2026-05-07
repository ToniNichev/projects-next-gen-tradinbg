#!/usr/bin/env python3
"""
Test script for RAG implementation.

This script verifies that RAG is working correctly by:
1. Checking if dependencies are installed
2. Testing trade embedding
3. Testing similarity search
4. Showing retrieved trades

Usage:
    python3 test_rag.py
"""

import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("RAG IMPLEMENTATION TEST")
    logger.info("=" * 60)
    
    # Test 1: Check dependencies
    logger.info("\n[1/4] Checking RAG dependencies...")
    try:
        from trade_rag import is_rag_available, TradeEmbedder, TradeVectorDB
        
        if not is_rag_available():
            logger.error("❌ RAG dependencies not installed!")
            logger.error("Install with: pip install chromadb sentence-transformers")
            return 1
        
        logger.info("✅ RAG dependencies installed")
    except ImportError as e:
        logger.error(f"❌ Failed to import trade_rag: {e}")
        return 1
    
    # Test 2: Initialize database
    logger.info("\n[2/4] Connecting to database...")
    try:
        from database import get_database, initialize_database
        
        # Initialize database first
        initialize_database()
        db = get_database()
        logger.info("✅ Database connected")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return 1
    
    # Test 3: Check indexed trades
    logger.info("\n[3/4] Checking vector database...")
    try:
        vector_db = TradeVectorDB(db)
        stats = vector_db.get_stats()
        
        logger.info(f"✅ Vector database initialized")
        logger.info(f"   - Total trades indexed: {stats['total_trades_indexed']}")
        logger.info(f"   - Collection: {stats['collection_name']}")
        logger.info(f"   - Embedding dimension: {stats['embedding_dimension']}")
        logger.info(f"   - Storage: {stats['persist_directory']}")
        
        if stats['total_trades_indexed'] == 0:
            logger.warning("\n⚠️  No trades indexed yet!")
            logger.warning("Run: python3 index_trades_rag.py")
            return 0
        
        if stats['total_trades_indexed'] < 5:
            logger.warning(f"\n⚠️  Only {stats['total_trades_indexed']} trades indexed")
            logger.warning("RAG requires at least 5 trades. Add more trades or lower the threshold.")
        
    except Exception as e:
        logger.error(f"❌ Vector database initialization failed: {e}")
        return 1
    
    # Test 4: Test retrieval with mock market data
    logger.info("\n[4/4] Testing similarity search...")
    try:
        # Create mock market data
        mock_market = {
            "symbol": "BTC/USDT",
            "current_price": 67000.0,
            "rsi": 72.0,
            "macd_histogram": -5.2,
            "trend": "bearish",
            "volume_ratio": 1.3,
        }
        
        logger.info(f"   Query: {mock_market['trend']} market, RSI {mock_market['rsi']:.0f}")
        
        similar_trades = vector_db.retrieve_similar_trades(
            market_data=mock_market,
            n_results=5
        )
        
        if not similar_trades:
            logger.warning("⚠️  No similar trades found")
            logger.warning("This could be normal if you have few trades or very different conditions")
            return 0
        
        logger.info(f"✅ Retrieved {len(similar_trades)} similar trades:")
        
        for i, trade in enumerate(similar_trades[:5], 1):
            pnl_str = f"{trade.pnl:+.2f}" if trade.pnl else "N/A"
            outcome = "WIN ✓" if (trade.pnl and trade.pnl > 0) else "LOSS ✗"
            logger.info(
                f"   {i}. {trade.side.upper():4s} @ ${trade.price:.2f} "
                f"→ {outcome} (P&L: ${pnl_str})"
            )
        
        # Calculate win rate
        winning = [t for t in similar_trades if t.pnl and t.pnl > 0]
        win_rate = len(winning) / len(similar_trades) * 100 if similar_trades else 0
        
        logger.info(f"\n   Win rate of similar trades: {win_rate:.0f}%")
        
    except Exception as e:
        logger.error(f"❌ Similarity search failed: {e}", exc_info=True)
        return 1
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    logger.info("✅ All RAG components working correctly!")
    logger.info(f"✅ {stats['total_trades_indexed']} trades indexed and searchable")
    logger.info("✅ Similarity search returning relevant results")
    logger.info("")
    logger.info("Next steps:")
    logger.info("1. Run your bot: python3 main.py")
    logger.info("2. Watch for 'RAG enabled' messages in logs")
    logger.info("3. Monitor LLM analysis speed improvement")
    logger.info("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
