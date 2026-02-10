#!/usr/bin/env python3
"""
Index Historical Trades for RAG (Retrieval Augmented Generation)

This script indexes all historical trades into a vector database for semantic search.
Run this once after installing RAG dependencies, then re-run periodically to index new trades.

Usage:
    python3 index_trades_rag.py                    # Index all trades
    python3 index_trades_rag.py --limit 500        # Index last 500 trades
    python3 index_trades_rag.py --clear            # Clear index and re-index
    python3 index_trades_rag.py --stats            # Show index statistics
"""

import argparse
import logging
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Index trades for RAG semantic search")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum trades to index")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for indexing")
    parser.add_argument("--clear", action="store_true", help="Clear existing index before re-indexing")
    parser.add_argument("--stats", action="store_true", help="Show index statistics only")
    
    args = parser.parse_args()
    
    # Check if RAG dependencies are available
    try:
        from trade_rag import TradeVectorDB, is_rag_available
        
        if not is_rag_available():
            logger.error("RAG dependencies not installed!")
            logger.error("Install with: pip install chromadb sentence-transformers")
            return 1
            
    except ImportError as e:
        logger.error(f"Failed to import trade_rag module: {e}")
        logger.error("Make sure trade_rag.py is in the current directory")
        return 1
    
    # Import database
    try:
        from database import get_database, initialize_database
    except ImportError as e:
        logger.error(f"Failed to import database module: {e}")
        return 1
    
    try:
        # Initialize database
        logger.info("Initializing database...")
        initialize_database()
        
        logger.info("Connecting to database...")
        db = get_database()
        
        # Initialize vector database
        logger.info("Initializing vector database...")
        vector_db = TradeVectorDB(db)
        
        # Show stats if requested
        if args.stats:
            stats = vector_db.get_stats()
            logger.info("=" * 60)
            logger.info("TRADE VECTOR DATABASE STATISTICS")
            logger.info("=" * 60)
            logger.info(f"Total trades indexed: {stats['total_trades_indexed']}")
            logger.info(f"Collection name: {stats['collection_name']}")
            logger.info(f"Embedding dimension: {stats['embedding_dimension']}")
            logger.info(f"Persist directory: {stats['persist_directory']}")
            logger.info("=" * 60)
            return 0
        
        # Clear index if requested
        if args.clear:
            confirm = input("⚠️  Clear existing index? This cannot be undone. (yes/no): ")
            if confirm.lower() == "yes":
                vector_db.clear_index()
                logger.info("Index cleared successfully")
            else:
                logger.info("Clear cancelled")
                return 0
        
        # Index trades
        logger.info("=" * 60)
        logger.info("INDEXING TRADES FOR RAG")
        logger.info("=" * 60)
        logger.info(f"Limit: {args.limit} trades")
        logger.info(f"Batch size: {args.batch_size}")
        logger.info("")
        
        start_time = datetime.now()
        
        vector_db.index_all_trades(
            limit=args.limit,
            batch_size=args.batch_size
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Show final stats
        stats = vector_db.get_stats()
        logger.info("")
        logger.info("=" * 60)
        logger.info("INDEXING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total trades indexed: {stats['total_trades_indexed']}")
        logger.info(f"Time taken: {duration:.1f} seconds")
        logger.info(f"Average: {duration/max(1, stats['total_trades_indexed']):.2f} sec/trade")
        logger.info("=" * 60)
        logger.info("")
        logger.info("✅ Trades are now indexed for RAG semantic search!")
        logger.info("The LLM strategy will automatically use RAG if enabled in config.")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error during indexing: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
