"""
Retrieval Augmented Generation (RAG) for Trading Bot

This module implements semantic search over historical trades to provide
relevant context to the LLM. Instead of sending ALL trade history, we:
1. Embed each trade as a vector (semantic representation)
2. Store in vector database (ChromaDB)
3. Retrieve only the most similar trades to current market conditions
4. Send relevant trades to LLM for better analysis

Benefits:
- Faster LLM inference (less context to process)
- Better signal quality (only relevant historical patterns)
- Works with smaller LLM models (reduced token requirements)
"""

import logging
import os
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Optional dependencies - fail gracefully if not installed
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
    logger.info("✅ chromadb imported successfully")
except ImportError as e:
    CHROMADB_AVAILABLE = False
    logger.warning(f"chromadb not installed: {e}. Install with: pip install chromadb")
except Exception as e:
    CHROMADB_AVAILABLE = False
    logger.error(f"Error importing chromadb: {e}", exc_info=True)

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
    logger.info("✅ sentence-transformers imported successfully")
except ImportError as e:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning(f"sentence-transformers not installed: {e}. Install with: pip install sentence-transformers")
except Exception as e:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.error(f"Error importing sentence-transformers: {e}", exc_info=True)


class TradeEmbedder:
    """
    Convert trades to semantic embeddings using sentence transformers.
    
    Uses 'all-MiniLM-L6-v2' model:
    - Small and fast (~80MB)
    - Good for semantic similarity
    - Outputs 384-dimensional vectors
    """
    
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers required for RAG. Install with: pip install sentence-transformers")
        
        self.model_name = model_name
        self.model = None
        
        # Lazy load model (only when first used)
        self._load_model()
    
    def _load_model(self):
        """Load the sentence transformer model"""
        if self.model is None:
            logger.info(f"Loading embedding model: {self.model_name}")
            try:
                self.model = SentenceTransformer(self.model_name)
                logger.info(f"Embedding model loaded successfully (dimension: {self.model.get_sentence_embedding_dimension()})")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise
    
    def embed_trade(self, trade) -> List[float]:
        """
        Convert a trade to a semantic vector.
        
        Args:
            trade: Trade object from database
            
        Returns:
            List of floats representing the embedding vector
        """
        # Create a rich text description of the trade
        description = self._create_trade_description(trade)
        
        # Convert to embedding
        embedding = self.model.encode(description, convert_to_numpy=True)
        
        return embedding.tolist()
    
    def embed_market_state(self, market_data: Dict) -> List[float]:
        """
        Convert current market conditions to a vector for similarity search.
        
        Args:
            market_data: Dictionary with current market indicators
            
        Returns:
            List of floats representing the embedding vector
        """
        description = self._create_market_description(market_data)
        embedding = self.model.encode(description, convert_to_numpy=True)
        return embedding.tolist()
    
    def _create_trade_description(self, trade) -> str:
        """
        Create a natural language description of a trade for embedding.
        
        This captures:
        - Market conditions at entry
        - Trade direction and outcome
        - Technical indicators
        - Duration and profitability
        """
        # Determine market condition
        if hasattr(trade, 'rsi') and trade.rsi:
            if trade.rsi < 30:
                rsi_condition = "oversold"
            elif trade.rsi > 70:
                rsi_condition = "overbought"
            else:
                rsi_condition = "neutral"
        else:
            rsi_condition = "unknown"
        
        # Determine trend (using EMA if available)
        if hasattr(trade, 'short_ema') and hasattr(trade, 'long_ema') and trade.short_ema and trade.long_ema:
            trend = "bullish" if trade.short_ema > trade.long_ema else "bearish"
        else:
            trend = "unknown"
        
        # Calculate outcome
        outcome = "winning" if (trade.pnl and trade.pnl > 0) else "losing"
        
        # Build description
        description = f"""
        Trade direction: {trade.side}
        Market trend: {trend}
        RSI condition: {rsi_condition}
        Entry price: ${trade.price:.2f}
        Trade outcome: {outcome} trade
        Exit reason: {trade.exit_reason if hasattr(trade, 'exit_reason') else 'unknown'}
        Strategy: {trade.strategy_name if hasattr(trade, 'strategy_name') else 'unknown'}
        Signal confidence: {trade.signal_confidence if hasattr(trade, 'signal_confidence') else 0.5}
        """.strip()
        
        # Add PnL context if available
        if trade.pnl:
            pnl_pct = (trade.pnl / trade.notional * 100) if trade.notional else 0
            description += f"\nProfit/Loss: {pnl_pct:.2f}%"
        
        return description
    
    def _create_market_description(self, market_data: Dict) -> str:
        """
        Create a natural language description of current market state.
        
        This should match the format used for trade embeddings to ensure
        semantic similarity works correctly.
        """
        # Determine RSI condition
        rsi = market_data.get('rsi', 50)
        if rsi < 30:
            rsi_condition = "oversold"
        elif rsi > 70:
            rsi_condition = "overbought"
        else:
            rsi_condition = "neutral"
        
        # Determine trend
        trend = market_data.get('trend', 'neutral')
        
        # Build query description
        description = f"""
        Market trend: {trend}
        RSI condition: {rsi_condition}
        Current price: ${market_data.get('current_price', 0):.2f}
        MACD histogram: {market_data.get('macd_histogram', 0):.2f}
        Volume ratio: {market_data.get('volume_ratio', 1.0):.2f}x average
        """.strip()
        
        return description


class TradeVectorDB:
    """
    Vector database for storing and retrieving trade embeddings.
    
    Uses ChromaDB for efficient similarity search.
    """
    
    def __init__(self, db_manager, persist_directory: str = "./data/chroma_db"):
        if not CHROMADB_AVAILABLE:
            raise ImportError("chromadb required for RAG. Install with: pip install chromadb")
        
        self.db_manager = db_manager
        self.persist_directory = persist_directory
        self.embedder = TradeEmbedder()
        
        # Create directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize ChromaDB client
        logger.info(f"Initializing ChromaDB at {persist_directory}")
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Get or create collection for trades
        self.collection = self.client.get_or_create_collection(
            name="trades",
            metadata={"hnsw:space": "cosine"}  # Use cosine similarity
        )
        
        logger.info(f"Trade vector database initialized ({self.collection.count()} trades indexed)")
    
    def index_trade(self, trade):
        """
        Index a single trade in the vector database.
        
        Args:
            trade: Trade object from database
        """
        try:
            # Generate embedding
            embedding = self.embedder.embed_trade(trade)
            
            # Create metadata for filtering and debugging
            metadata = {
                "trade_id": trade.id,
                "side": trade.side,
                "timestamp": trade.timestamp.isoformat() if trade.timestamp else "",
                "strategy": trade.strategy_name if hasattr(trade, 'strategy_name') else "unknown",
                "pnl": float(trade.pnl) if trade.pnl else 0.0,
                "exit_reason": trade.exit_reason if hasattr(trade, 'exit_reason') else "",
            }
            
            # Add to collection
            self.collection.add(
                ids=[str(trade.id)],
                embeddings=[embedding],
                metadatas=[metadata]
            )
            
            logger.debug(f"Indexed trade {trade.id} (side: {trade.side}, pnl: {trade.pnl})")
            
        except Exception as e:
            logger.error(f"Failed to index trade {trade.id}: {e}")
            raise
    
    def index_all_trades(self, limit: int = 1000, batch_size: int = 50):
        """
        Index all historical trades from database.
        
        Args:
            limit: Maximum number of trades to index
            batch_size: Number of trades to process at once
        """
        logger.info(f"Starting batch indexing of up to {limit} trades...")
        
        # Get all trades
        trades = self.db_manager.get_trades(limit=limit)
        
        if not trades:
            logger.warning("No trades found to index")
            return
        
        logger.info(f"Found {len(trades)} trades to index")
        
        # Process in batches for efficiency
        indexed_count = 0
        failed_count = 0
        
        for i in range(0, len(trades), batch_size):
            batch = trades[i:i+batch_size]
            
            for trade in batch:
                try:
                    # Skip if already indexed
                    existing = self.collection.get(ids=[str(trade.id)])
                    if existing and existing['ids']:
                        logger.debug(f"Trade {trade.id} already indexed, skipping")
                        continue
                    
                    self.index_trade(trade)
                    indexed_count += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to index trade {trade.id}: {e}")
                    failed_count += 1
            
            logger.info(f"Progress: {i + len(batch)}/{len(trades)} trades processed")
        
        logger.info(f"Indexing complete: {indexed_count} indexed, {failed_count} failed")
    
    def retrieve_similar_trades(
        self, 
        market_data: Dict, 
        n_results: int = 10,
        min_pnl_filter: Optional[float] = None
    ) -> List:
        """
        Retrieve most similar trades to current market conditions.
        
        Args:
            market_data: Current market state (RSI, MACD, trend, etc.)
            n_results: Number of similar trades to return
            min_pnl_filter: Optional filter to only return profitable trades
            
        Returns:
            List of Trade objects from database
        """
        try:
            # Create embedding for current market state
            query_embedding = self.embedder.embed_market_state(market_data)
            
            # Build filter if needed
            where_filter = None
            if min_pnl_filter is not None:
                where_filter = {"pnl": {"$gte": min_pnl_filter}}
            
            # Query vector database
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, self.collection.count()),
                where=where_filter
            )
            
            # Extract trade IDs
            if not results or not results['ids'] or not results['ids'][0]:
                logger.warning("No similar trades found")
                return []
            
            trade_ids = [int(id_str) for id_str in results['ids'][0]]
            distances = results['distances'][0] if 'distances' in results else []
            
            logger.info(f"Retrieved {len(trade_ids)} similar trades")
            if distances:
                logger.debug(f"Similarity scores (lower=better): {[f'{d:.3f}' for d in distances[:5]]}")
            
            # Retrieve full trade objects from database
            similar_trades = []
            for trade_id in trade_ids:
                trade = self._get_trade_by_id(trade_id)
                if trade:
                    similar_trades.append(trade)
            
            return similar_trades
            
        except Exception as e:
            logger.error(f"Error retrieving similar trades: {e}")
            return []
    
    def _get_trade_by_id(self, trade_id: int):
        """Helper to get a single trade by ID"""
        return self.db_manager.get_trade_by_id(trade_id)
    
    def clear_index(self):
        """Clear all indexed trades (useful for re-indexing)"""
        logger.warning("Clearing trade vector index...")
        
        # Delete collection
        self.client.delete_collection("trades")
        
        # Recreate empty collection
        self.collection = self.client.get_or_create_collection(
            name="trades",
            metadata={"hnsw:space": "cosine"}
        )
        
        logger.info("Trade vector index cleared")
    
    def get_stats(self) -> Dict:
        """Get statistics about the vector database"""
        return {
            "total_trades_indexed": self.collection.count(),
            "collection_name": self.collection.name,
            "embedding_dimension": 384,  # all-MiniLM-L6-v2 dimension
            "persist_directory": self.persist_directory,
        }


def is_rag_available() -> bool:
    """Check if RAG dependencies are installed and working"""
    return CHROMADB_AVAILABLE and SENTENCE_TRANSFORMERS_AVAILABLE
