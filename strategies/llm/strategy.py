"""
LLM Market Analysis Strategy - Refactored

Uses local LLM (via Ollama) to analyze market data and generate trading signals.
This refactored version delegates responsibilities to focused modules for better maintainability.
"""

import json
import logging
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from ..base_strategy import BaseStrategy, StrategySignal
from ..constants import StrategyNames
from .market_data import MarketDataFetcher
from .llm_client import OllamaClient
from .prompt_builder import PromptBuilder
from .response_parser import ResponseParser
from .cache_manager import AnalysisCache

logger = logging.getLogger(__name__)


class LLMPatternStrategy(BaseStrategy):
    """LLM-powered pattern analysis strategy using Ollama"""
    
    def __init__(self, config: dict, db_manager=None, progress_callback=None):
        super().__init__(StrategyNames.LLM_PATTERN, config)
        
        # Configuration
        self.lookback_days = config.get("llm_lookback_days", 7)
        self.backtest_sample_interval = config.get("llm_backtest_sample_interval", 12)
        
        # RAG configuration
        self.use_rag = config.get("llm_use_rag", True)
        self.rag_num_results = config.get("llm_rag_num_results", 10)
        self.rag_min_trades = config.get("llm_rag_min_trades", 5)
        self.rag_persist_dir = config.get("llm_rag_persist_dir", "./data/chroma_db")
        
        # Database manager for trade history and caching
        self.db_manager = db_manager
        
        # Backtest state tracking
        self._backtest_candle_count = 0
        self._last_backtest_analysis = None
        self._backtest_total_candles = 0
        self._backtest_total_analyses = 0
        self._backtest_current_analysis = 0
        self._backtest_analysis_times = []
        self._backtest_started = False
        self._progress_callback = progress_callback
        
        # Initialize modules
        self.llm_client = OllamaClient(
            ollama_url=config.get("llm_ollama_url", "http://localhost:11434"),
            model=config.get("llm_ollama_model", "mistral"),
            temperature=config.get("llm_temperature", 0.3),
            num_predict=config.get("llm_num_predict", 1000),
            timeout_seconds=config.get("llm_timeout_seconds", 60)
        )
        
        self.response_parser = ResponseParser(
            require_patterns=config.get("llm_require_patterns", False),
            stop_loss_pct=config.get("stop_loss_pct", 0.025),
            take_profit_pct=config.get("take_profit_pct", 0.04),
            min_position_size=config.get("min_position_size", 0.15),
            max_position_size=config.get("max_position_size", 0.35)
        )
        
        self.cache = AnalysisCache(
            db_manager=db_manager,
            cache_minutes=config.get("llm_cache_minutes", 15)
        )
        
        # Risk management defaults (used by response parser)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.025)
        self.take_profit_pct = config.get("take_profit_pct", 0.04)
        self.min_position_size = config.get("min_position_size", 0.15)
        self.max_position_size = config.get("max_position_size", 0.35)
        
        # Initialize RAG if enabled
        self.rag_db = None
        if self.use_rag and db_manager:
            try:
                from trade_rag import TradeVectorDB, is_rag_available
                
                if is_rag_available():
                    logger.info(
                        f"{self.name}: Initializing RAG "
                        f"(retrieving top {self.rag_num_results} similar trades)"
                    )
                    self.rag_db = TradeVectorDB(db_manager, persist_directory=self.rag_persist_dir)
                    logger.info(f"{self.name}: RAG enabled - {self.rag_db.collection.count()} trades indexed")
                else:
                    logger.warning(
                        f"{self.name}: RAG enabled but dependencies not installed. "
                        f"Install with: pip install chromadb sentence-transformers"
                    )
                    self.use_rag = False
            except Exception as e:
                logger.warning(f"{self.name}: Failed to initialize RAG: {e}. Falling back to non-RAG mode")
                self.use_rag = False
                self.rag_db = None
    
    def compute_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        """
        Compute LLM-based signal by analyzing market data and technical indicators.
        
        This method:
        1. Checks for cached analysis (within cache_minutes)
        2. If no valid cache, fetches recent market data (candles)
        3. Calculates technical indicators (RSI, MACD, support/resistance, etc.)
        4. Optionally includes trade history for context
        5. Sends market data to LLM for analysis
        6. Generates signal based on LLM's recommendation
        7. Caches the result for future use
        """
        # Get current price
        if candle_data and len(candle_data) > 0:
            current_price = float(candle_data[-1][4])  # Close price of last candle
            is_backtest_mode = True
        else:
            current_price = MarketDataFetcher.get_current_price(exchange, symbol)
            is_backtest_mode = False
        
        # Handle backtest sampling
        if is_backtest_mode:
            should_analyze = self._handle_backtest_sampling(candle_data)
            if not should_analyze:
                # Either not a sample point or not enough candles
                if self._last_backtest_analysis:
                    # Reuse last analysis
                    return self._signal_from_analysis(
                        self._last_backtest_analysis, exchange, symbol, current_price
                    )
                else:
                    # No analysis yet - return neutral
                    return self._neutral_signal(exchange, symbol, current_price)
        
        # Check cache (skip in backtest mode)
        if not is_backtest_mode and self.cache.cache_minutes > 0:
            cached = self.cache.get_cached_analysis()
            if cached:
                logger.info(
                    f"{self.name}: Using cached analysis "
                    f"(valid until {cached['cache_valid_until']})"
                )
                return self._signal_from_analysis(cached, exchange, symbol, current_price)
        
        # Fetch and analyze market data
        try:
            market_data = MarketDataFetcher.fetch_market_data(
                exchange, symbol, timeframe, candle_data
            )
            
            # Optionally fetch trade context (skip in backtest mode)
            trade_context = None
            if self.db_manager and not is_backtest_mode:
                trade_context = self._get_trade_context(market_data)
            
            # Perform LLM analysis
            analysis = self._analyze_with_llm(market_data, trade_context, current_price, symbol)
            
            # Cache the analysis (only in live mode)
            if analysis and not is_backtest_mode and self.cache.cache_minutes > 0:
                self.cache.cache_analysis(analysis, self.lookback_days, self.llm_client.model)
            
            signal = self._signal_from_analysis(analysis, exchange, symbol, current_price)
            
            # Log signal details for debugging
            logger.info(
                f"{self.name}: Generated signal - {signal.direction.upper()} "
                f"(confidence: {signal.confidence:.1%}, position: {signal.position_size:.1%})"
            )
            if signal.direction != "neutral":
                logger.info(
                    f"{self.name}: Trade details - Entry: ${current_price:.2f}, "
                    f"Stop: ${signal.stop_loss:.2f}, Target: ${signal.take_profit:.2f}"
                )
            
        except ConnectionError:
            logger.error(f"{self.name}: Cannot connect to Ollama - returning neutral signal")
            return self._neutral_signal(exchange, symbol, current_price)
        except TimeoutError:
            logger.error(f"{self.name}: Ollama request timed out - returning neutral signal")
            return self._neutral_signal(exchange, symbol, current_price)
        except Exception as e:
            logger.error(f"{self.name}: LLM analysis failed: {e}", exc_info=True)
            return self._neutral_signal(exchange, symbol, current_price)
        
        # Track backtest progress and store last analysis AFTER the try block so that
        # a failing progress callback cannot discard a valid LLM analysis result.
        if is_backtest_mode and analysis:
            self._last_backtest_analysis = analysis
            try:
                self._track_backtest_progress(analysis)
            except Exception as cb_err:
                logger.warning(f"{self.name}: Progress tracking error: {cb_err}")
        
        return signal
    
    def set_backtest_total_candles(self, total_candles: int):
        """
        Set the total number of candles for the backtest upfront (before the loop starts).
        Call this from the backtest runner after all candles are loaded, so progress
        tracking uses the real total instead of the first sliding-window size.
        """
        self._backtest_total_candles = total_candles
        self._backtest_total_analyses = max(
            1, total_candles // self.backtest_sample_interval
        )
        
        # Calculate when first analysis will occur (need 50+ candles minimum)
        first_valid_candle = 50
        first_analysis_candle = ((first_valid_candle // self.backtest_sample_interval) + 1) * self.backtest_sample_interval
        
        logger.info(
            f"{self.name}: 📊 Backtest configured - {total_candles} total candles, "
            f"sampling every {self.backtest_sample_interval} = {self._backtest_total_analyses} analyses"
        )
        if total_candles < first_valid_candle:
            logger.warning(
                f"{self.name}: ⚠️  Only {total_candles} candles available. "
                f"LLM analysis requires 50+ candles for technical indicators. "
                f"No LLM signals will be generated in this backtest."
            )
        else:
            logger.info(
                f"{self.name}: First analysis will occur at candle {first_analysis_candle} "
                f"(need 50+ candles for indicators)"
            )

    def _handle_backtest_sampling(self, candle_data: list) -> bool:
        """
        Handle backtest sampling to speed up backtests
        
        Returns:
            True if should analyze this candle, False if should skip
        """
        # Initialize backtest tracking on first candle (only if not already set via set_backtest_total_candles)
        if not self._backtest_started:
            self._backtest_started = True
            
            # Test Ollama connection before starting backtest (quick mode - just checks server/model availability)
            logger.info(f"{self.name}: Testing Ollama connection before starting backtest...")
            if not self.llm_client.test_connection(quick=True):
                logger.warning(
                    f"{self.name}: ⚠️  Ollama connection test failed! "
                    f"Make sure Ollama is running and the model is available. "
                    f"Run: ollama serve && ollama pull {self.llm_client.model}"
                )
                logger.warning(f"{self.name}: Continuing with backtest - will handle errors per-analysis")
                # Don't abort the backtest - let it continue and handle timeouts per analysis
            
            if self._backtest_total_candles == 0:
                # Fallback: set_backtest_total_candles was not called — use window size as approximation
                self._backtest_total_candles = len(candle_data) if candle_data else 0
                self._backtest_total_analyses = max(
                    1, self._backtest_total_candles // self.backtest_sample_interval
                )
            self._backtest_current_analysis = 0
            self._backtest_analysis_times = []
            
            logger.info(
                f"{self.name}: 📊 Starting backtest - {self._backtest_total_candles} candles, "
                f"analyzing every {self.backtest_sample_interval} = {self._backtest_total_analyses} analyses"
            )
            
            if self._progress_callback:
                try:
                    self._progress_callback(
                        total_analyses=self._backtest_total_analyses,
                        total_candles=self._backtest_total_candles,
                        completed_analyses=0,
                        current_candle=0
                    )
                except Exception as cb_err:
                    logger.warning(f"{self.name}: Progress callback error on init: {cb_err}")
        
        self._backtest_candle_count += 1
        
        # Check if it's time to sample (every Nth candle)
        is_sample_candle = (self._backtest_candle_count % self.backtest_sample_interval == 0)
        
        # CRITICAL FIX: Only analyze if we have enough candles in the window
        # This prevents attempting analysis before we have sufficient data for technical indicators
        has_enough_candles = candle_data and len(candle_data) >= 50
        
        should_analyze = is_sample_candle and has_enough_candles
        
        if is_sample_candle:
            if has_enough_candles:
                # We have enough data - proceed with analysis
                self._backtest_current_analysis += 1
                progress_pct = (
                    (self._backtest_current_analysis / self._backtest_total_analyses * 100)
                    if self._backtest_total_analyses > 0 else 0
                )
                
                # Calculate ETA
                eta_str = ""
                if len(self._backtest_analysis_times) > 0:
                    avg_time = sum(self._backtest_analysis_times) / len(self._backtest_analysis_times)
                    remaining = self._backtest_total_analyses - self._backtest_current_analysis
                    eta_seconds = remaining * avg_time
                    eta_minutes = eta_seconds / 60
                    eta_str = f" - Est. {eta_minutes:.0f} min remaining (avg: {avg_time:.1f}s/analysis)"
                
                logger.info(
                    f"{self.name}: 🔍 Analysis {self._backtest_current_analysis}/"
                    f"{self._backtest_total_analyses} ({progress_pct:.0f}%) - "
                    f"Candle {self._backtest_candle_count} (window: {len(candle_data)} candles){eta_str}"
                )
            else:
                # Not enough candles yet - skip this analysis point
                logger.debug(
                    f"{self.name}: Skipping candle {self._backtest_candle_count} "
                    f"(sample point but only {len(candle_data) if candle_data else 0}/50 candles available)"
                )
        else:
            logger.debug(
                f"{self.name}: Skipping candle {self._backtest_candle_count} "
                f"(sampling every {self.backtest_sample_interval})"
            )
        
        return should_analyze
    
    def _track_backtest_progress(self, analysis: Dict):
        """Track backtest progress and notify UI"""
        if "analysis_duration_ms" in analysis:
            analysis_time_seconds = analysis["analysis_duration_ms"] / 1000
            self._backtest_analysis_times.append(analysis_time_seconds)
            
            # Keep only last 10 analyses for moving average
            if len(self._backtest_analysis_times) > 10:
                self._backtest_analysis_times.pop(0)
            
            # Calculate ETA and notify UI
            if self._progress_callback:
                avg_time = sum(self._backtest_analysis_times) / len(self._backtest_analysis_times)
                remaining = self._backtest_total_analyses - self._backtest_current_analysis
                eta_seconds = remaining * avg_time
                
                self._progress_callback(
                    completed_analyses=self._backtest_current_analysis,
                    current_candle=self._backtest_candle_count,
                    eta_seconds=int(eta_seconds),
                    avg_time_per_analysis=avg_time
                )
            
            # Log completion
            if self._backtest_current_analysis >= self._backtest_total_analyses:
                avg_time = sum(self._backtest_analysis_times) / len(self._backtest_analysis_times)
                total_time = sum(self._backtest_analysis_times)
                logger.info(
                    f"{self.name}: ✅ All {self._backtest_total_analyses} analyses complete! "
                    f"Total LLM time: {total_time/60:.1f} min (avg: {avg_time:.1f}s/analysis)"
                )
    
    def _get_trade_context(self, market_data: Dict) -> Optional[Dict]:
        """Get trade context using RAG or simple history fetch"""
        try:
            # Use RAG if enabled
            if self.use_rag and self.rag_db:
                trade_context = self._prepare_trade_context_with_rag(market_data)
                if trade_context:
                    logger.info(
                        f"{self.name}: RAG context - {trade_context['total_trades']} similar trades "
                        f"({trade_context['win_rate']:.0f}% win rate)"
                    )
                return trade_context
            else:
                # Fallback: fetch all recent trades
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=self.lookback_days)
                trades = self.db_manager.get_trades(
                    limit=100,
                    start_date=start_date,
                    end_date=end_date
                )
                if len(trades) >= 3:
                    trade_context = self._prepare_trade_context(trades)
                    logger.info(f"{self.name}: Including {len(trades)} trades as context (RAG disabled)")
                    return trade_context
        except Exception as e:
            logger.debug(f"{self.name}: Could not fetch trade history for context: {e}")
        
        return None
    
    def _prepare_trade_context(self, trades: list) -> Dict:
        """Prepare trade history as context (original method)"""
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl < 0]
        total_pnl = sum(t.pnl for t in trades if t.pnl) if trades else 0.0
        
        return {
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / len(trades) * 100) if trades else 0.0,
            "total_pnl": total_pnl,
        }
    
    def _prepare_trade_context_with_rag(self, market_data: Dict) -> Optional[Dict]:
        """Use RAG to get only relevant trades similar to current market conditions"""
        if not self.use_rag or not self.rag_db:
            return None
        
        try:
            # Check if we have enough indexed trades
            if self.rag_db.collection.count() < self.rag_min_trades:
                logger.warning(
                    f"{self.name}: Only {self.rag_db.collection.count()} trades indexed, "
                    f"need at least {self.rag_min_trades}. Run: python3 index_trades_rag.py"
                )
                return None
            
            # Retrieve similar trades
            similar_trades = self.rag_db.retrieve_similar_trades(
                market_data=market_data,
                n_results=self.rag_num_results
            )
            
            if len(similar_trades) < 3:
                logger.warning(
                    f"{self.name}: RAG returned only {len(similar_trades)} trades, need at least 3"
                )
                return None
            
            # Calculate statistics
            winning = [t for t in similar_trades if t.pnl and t.pnl > 0]
            losing = [t for t in similar_trades if t.pnl and t.pnl <= 0]
            total_pnl = sum(t.pnl for t in similar_trades if t.pnl)
            avg_winning_pnl = np.mean([t.pnl for t in winning]) if winning else 0.0
            avg_losing_pnl = np.mean([t.pnl for t in losing]) if losing else 0.0
            
            # Build detailed context
            trade_details = []
            for trade in similar_trades[:5]:  # Top 5 most similar
                detail = {
                    "side": trade.side,
                    "entry_price": trade.price,
                    "pnl": trade.pnl if trade.pnl else 0,
                    "pnl_pct": (
                        (trade.pnl / trade.notional * 100)
                        if (trade.pnl and trade.notional) else 0
                    ),
                    "exit_reason": trade.exit_reason if hasattr(trade, 'exit_reason') else "unknown",
                    "strategy": trade.strategy_name if hasattr(trade, 'strategy_name') else "unknown"
                }
                trade_details.append(detail)
            
            logger.info(
                f"{self.name}: RAG retrieved {len(similar_trades)} similar trades "
                f"({len(winning)} wins, {len(losing)} losses, "
                f"{len(winning)/len(similar_trades)*100:.0f}% win rate)"
            )
            
            return {
                "total_trades": len(similar_trades),
                "winning_trades": len(winning),
                "losing_trades": len(losing),
                "win_rate": (len(winning) / len(similar_trades) * 100) if similar_trades else 0.0,
                "total_pnl": total_pnl,
                "avg_winning_pnl": avg_winning_pnl,
                "avg_losing_pnl": avg_losing_pnl,
                "similar_trades_detail": trade_details,
                "rag_enabled": True,
            }
            
        except Exception as e:
            logger.error(f"{self.name}: Error in RAG retrieval: {e}")
            return None
    
    def _analyze_with_llm(
        self,
        market_data: Dict,
        trade_context: Optional[Dict],
        current_price: float,
        symbol: str
    ) -> Dict:
        """Send market data to LLM for analysis"""
        # Create prompt
        prompt = PromptBuilder.create_market_analysis_prompt(market_data, trade_context, symbol)
        
        # Call LLM
        response = self.llm_client.analyze(prompt)
        
        # Parse response
        analysis = self.response_parser.parse(response["response"], current_price)
        
        # Add metadata
        analysis["analysis_duration_ms"] = response["duration_ms"]
        analysis["model_used"] = self.llm_client.model
        analysis["num_trades_analyzed"] = trade_context["total_trades"] if trade_context else 0
        analysis["analysis_period_days"] = self.lookback_days
        
        # Include market indicators
        analysis["rsi"] = market_data["rsi"]
        analysis["macd_histogram"] = market_data["macd_histogram"]
        analysis["trend"] = market_data["trend"]
        
        # Include trade context stats
        if trade_context:
            analysis["recent_win_rate"] = trade_context["win_rate"] / 100
            analysis["recent_pnl"] = trade_context["total_pnl"]
        else:
            analysis["recent_win_rate"] = 0.0
            analysis["recent_pnl"] = 0.0
        
        return analysis
    
    def _signal_from_analysis(
        self,
        analysis: Dict,
        exchange,
        symbol: str,
        override_price: float = None
    ) -> StrategySignal:
        """Convert LLM analysis to StrategySignal"""
        # Determine price to use
        if override_price and override_price > 0:
            current_price = override_price
        else:
            current_price = analysis.get("current_price", 0.0)
            if current_price <= 0:
                current_price = MarketDataFetcher.get_current_price(exchange, symbol)
        
        # Safety check
        if current_price <= 0:
            logger.warning(f"{self.name}: Cannot determine valid price, returning neutral")
            return StrategySignal(
                direction="neutral",
                price=1.0,
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
                strategy_name=self.name,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                indicators={},
                info={"reason": "Invalid price data"},
            )
        
        # Parse patterns
        patterns_list = []
        if isinstance(analysis.get("patterns_found"), str):
            try:
                patterns_list = json.loads(analysis["patterns_found"])
            except:
                pass
        elif isinstance(analysis.get("patterns_found"), list):
            patterns_list = analysis["patterns_found"]
        
        # Build indicators dict
        indicators = {
            "patterns_count": len(patterns_list),
            "rsi": analysis.get("rsi", 50.0),
            "confidence_pct": analysis["confidence"] * 100,
        }
        
        # Build info dict
        info = {
            "reasoning": analysis.get("reasoning", "No reasoning provided"),
            "patterns": patterns_list,
            "model": analysis.get("model_used", self.llm_client.model),
            "cached": "cache_valid_until" in analysis,
        }
        
        # Recalculate stop loss and take profit based on current price
        direction = analysis["direction"]
        stop_loss_pct = analysis.get("stop_loss_pct", self.stop_loss_pct)
        take_profit_pct = analysis.get("take_profit_pct", self.take_profit_pct)
        
        if direction == "bullish":
            stop_loss = current_price * (1 - stop_loss_pct)
            take_profit = current_price * (1 + take_profit_pct)
        elif direction == "bearish":
            stop_loss = current_price * (1 + stop_loss_pct)
            take_profit = current_price * (1 - take_profit_pct)
        else:
            stop_loss = 0.0
            take_profit = 0.0
        
        return StrategySignal(
            direction=direction,
            price=current_price,
            confidence=analysis["confidence"],
            timestamp=datetime.now(timezone.utc),
            strategy_name=self.name,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=analysis.get("suggested_position_size", 0.2),
            indicators=indicators,
            info=info,
        )
    
    def _neutral_signal(self, exchange, symbol: str, override_price: float = None) -> StrategySignal:
        """Return a neutral signal (no trade)"""
        if override_price and override_price > 0:
            current_price = override_price
        else:
            current_price = MarketDataFetcher.get_current_price(exchange, symbol)
        
        if current_price <= 0:
            current_price = 1.0
        
        return StrategySignal(
            direction="neutral",
            price=current_price,
            confidence=0.0,
            timestamp=datetime.now(timezone.utc),
            strategy_name=self.name,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
            indicators={},
            info={"reason": "Insufficient data or LLM unavailable"},
        )
    
    def get_description(self) -> str:
        rag_status = (
            f", RAG: {self.rag_db.collection.count()} trades"
            if self.use_rag and self.rag_db else ""
        )
        return (
            f"LLM Market Analysis using {self.llm_client.model} "
            f"(cache: {self.cache.cache_minutes}min{rag_status})"
        )
    
    def get_parameters(self) -> Dict[str, object]:
        return {
            "ollama_url": self.llm_client.ollama_url,
            "model": self.llm_client.model,
            "lookback_days": self.lookback_days,
            "cache_minutes": self.cache.cache_minutes,
            "timeout_seconds": self.llm_client.timeout_seconds,
            "temperature": self.llm_client.temperature,
            "num_predict": self.llm_client.num_predict,
            "require_patterns": self.response_parser.require_patterns,
            "backtest_sample_interval": self.backtest_sample_interval,
            "use_rag": self.use_rag,
            "rag_num_results": self.rag_num_results,
            "rag_min_trades": self.rag_min_trades,
            "rag_persist_dir": self.rag_persist_dir,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "min_position_size": self.min_position_size,
            "max_position_size": self.max_position_size,
        }
