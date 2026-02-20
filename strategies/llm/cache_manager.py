"""
Cache Manager Module

Handles caching of LLM analysis results in the database.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AnalysisCache:
    """Manage caching of LLM analysis results"""
    
    def __init__(self, db_manager, cache_minutes: int = 15):
        """
        Initialize analysis cache
        
        Args:
            db_manager: Database manager instance
            cache_minutes: Cache validity duration in minutes
        """
        self.db_manager = db_manager
        self.cache_minutes = cache_minutes
    
    def get_cached_analysis(self) -> Optional[Dict]:
        """
        Get valid cached LLM analysis from database
        
        Returns:
            Dict with cached analysis, or None if no valid cache exists
        """
        if not self.db_manager:
            return None
        
        try:
            cached = self.db_manager.get_valid_cached_analysis()
            if not cached:
                return None
            
            # Convert to dict
            return {
                "direction": cached.direction,
                "confidence": cached.confidence,
                "reasoning": cached.reasoning,
                "patterns_found": json.loads(cached.patterns_found) if cached.patterns_found else [],
                "suggested_stop_loss": cached.suggested_stop_loss,
                "suggested_take_profit": cached.suggested_take_profit,
                "suggested_position_size": cached.suggested_position_size,
                "current_price": cached.current_price,
                "cache_valid_until": cached.cache_valid_until,
                "model_used": cached.model_used,
            }
        except Exception as e:
            logger.warning(f"Error fetching cached analysis: {e}")
            return None
    
    def cache_analysis(self, analysis: Dict, lookback_days: int, model: str):
        """
        Cache analysis results in database
        
        Args:
            analysis: Analysis results to cache
            lookback_days: Lookback period used for analysis
            model: LLM model used for analysis
        """
        if not self.db_manager:
            return
        
        try:
            cache_valid_until = datetime.utcnow() + timedelta(minutes=self.cache_minutes)
            
            analysis_data = {
                "timestamp": datetime.utcnow(),
                "analysis_period_days": lookback_days,
                "num_trades_analyzed": analysis.get("num_trades_analyzed", 0),
                "direction": analysis["direction"],
                "confidence": analysis["confidence"],
                "reasoning": analysis["reasoning"],
                "patterns_found": analysis["patterns_found"],  # Already JSON string
                "suggested_stop_loss": analysis["suggested_stop_loss"],
                "suggested_take_profit": analysis["suggested_take_profit"],
                "suggested_position_size": analysis["suggested_position_size"],
                "current_price": analysis["current_price"],
                "recent_win_rate": analysis.get("recent_win_rate", 0.0),
                "recent_pnl": analysis.get("recent_pnl", 0.0),
                "model_used": model,
                "analysis_duration_ms": analysis.get("analysis_duration_ms", 0),
                "cache_valid_until": cache_valid_until,
            }
            
            self.db_manager.add_llm_analysis(analysis_data)
            logger.info(f"Analysis cached until {cache_valid_until}")
            
        except Exception as e:
            logger.warning(f"Failed to cache analysis: {e}")
