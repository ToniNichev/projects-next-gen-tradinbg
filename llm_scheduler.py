"""
LLM Scheduler - Background thread for periodic LLM pattern analysis.

This module runs independently of the main trading loop to avoid blocking
signal generation with slow LLM inference.
"""

import logging
import threading
import time
from datetime import datetime, timezone


class LLMScheduler:
    """
    Background thread that triggers LLM analysis at configurable intervals.
    
    Features:
    - Non-blocking: Runs in daemon thread
    - Configurable interval
    - Immediate first analysis on startup
    - Graceful error handling
    - Clean shutdown support
    """
    
    def __init__(
        self,
        llm_strategy,
        exchange=None,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        interval_minutes: int = 15,
    ):
        """
        Initialize LLM scheduler.
        
        Args:
            llm_strategy: LLMPatternStrategy instance
            exchange: Optional CCXT exchange instance for current price
            symbol: Trading symbol for price lookup
            interval_minutes: Minutes between analysis runs
        """
        self.llm_strategy = llm_strategy
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.interval_seconds = interval_minutes * 60
        self.running = False
        self.thread = None
        self.logger = logging.getLogger(__name__)
    
    def start(self):
        """Start background scheduler thread"""
        if self.running:
            self.logger.warning("LLM scheduler already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="LLMScheduler")
        self.thread.start()
        
        self.logger.info(
            f"LLM scheduler started (interval: {self.interval_seconds/60:.1f} min, "
            f"model: {self.llm_strategy.llm_client.model})"
        )
        
        # Trigger initial analysis immediately in background
        threading.Thread(
            target=self._safe_analyze,
            daemon=True,
            name="LLMInitialAnalysis"
        ).start()
    
    def stop(self):
        """Stop scheduler gracefully"""
        if not self.running:
            return
        
        self.logger.info("Stopping LLM scheduler...")
        self.running = False
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        
        self.logger.info("LLM scheduler stopped")
    
    def trigger_now(self):
        """Manually trigger analysis immediately (non-blocking)"""
        if not self.running:
            self.logger.warning("Cannot trigger analysis: scheduler not running")
            return False
        
        self.logger.info("Manual LLM analysis triggered")
        threading.Thread(
            target=self._safe_analyze,
            kwargs={"force": True},
            daemon=True,
            name="LLMManualAnalysis"
        ).start()
        return True
    
    def _run_loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                # Sleep in small intervals to allow quick shutdown
                for _ in range(self.interval_seconds):
                    if not self.running:
                        break
                    time.sleep(1)
                
                # Trigger analysis if still running
                if self.running:
                    self._safe_analyze()
                    
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                # Continue running even on error
    
    def _safe_analyze(self, force: bool = False):
        """
        Run analysis with comprehensive error handling.
        
        Args:
            force: Force new analysis even if cache is valid
        """
        try:
            start_time = time.time()
            self.logger.info("Starting scheduled LLM pattern analysis...")
            
            # Run analysis via compute_signal.
            # If force=True, temporarily bypass the cache by zeroing its TTL.
            # The try/finally guarantees the original TTL is always restored.
            original_cache = None
            if force and hasattr(self.llm_strategy, 'cache'):
                original_cache = self.llm_strategy.cache.cache_minutes
                self.llm_strategy.cache.cache_minutes = 0

            try:
                signal = self.llm_strategy.compute_signal(
                    exchange=self.exchange,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    candle_data=None,
                )
            finally:
                if original_cache is not None and hasattr(self.llm_strategy, 'cache'):
                    self.llm_strategy.cache.cache_minutes = original_cache
            
            duration = time.time() - start_time
            
            # Log results
            if signal:
                patterns = []
                if signal.info and 'patterns' in signal.info:
                    patterns = signal.info['patterns']
                
                self.logger.info(
                    f"LLM analysis complete: {signal.direction} "
                    f"(confidence: {signal.confidence:.2f}, "
                    f"patterns: {len(patterns)}, "
                    f"duration: {duration:.1f}s)"
                )
                
                # Log patterns found
                if patterns:
                    self.logger.info(f"Patterns identified: {', '.join(patterns)}")
                
                # Log reasoning (truncated)
                reasoning = signal.info.get('reasoning', '') if signal.info else ''
                if reasoning:
                    reasoning_preview = reasoning[:150] + "..." if len(reasoning) > 150 else reasoning
                    self.logger.debug(f"LLM reasoning: {reasoning_preview}")
            else:
                self.logger.warning("LLM analysis returned no result")
                
        except Exception as e:
            self.logger.error(f"LLM analysis failed: {e}", exc_info=True)
            
            # Check for common issues and provide helpful error messages
            if "ConnectionError" in str(type(e)) or "connect" in str(e).lower():
                self.logger.error(
                    "Cannot connect to Ollama. Make sure:\n"
                    "  1. Ollama is installed (https://ollama.ai)\n"
                    "  2. Ollama service is running: ollama serve\n"
                    f"  3. Model is pulled: ollama pull {self.llm_strategy.llm_client.model}"
                )
            elif "timeout" in str(e).lower():
                self.logger.error(
                    f"LLM request timed out. Try:\n"
                    "  1. Using a smaller/faster model (mistral, llama2:7b)\n"
                    "  2. Increasing timeout in config\n"
                    "  3. Reducing lookback period"
                )
    
    def get_status(self) -> dict:
        """Get scheduler status information"""
        # Check for valid cached analysis
        cache_valid = False
        last_analysis_time = None
        
        if hasattr(self.llm_strategy, 'db_manager') and self.llm_strategy.db_manager:
            try:
                cached = self.llm_strategy.db_manager.get_valid_cached_analysis()
                cache_valid = cached is not None
                
                if cache_valid:
                    last_analysis_time = cached.timestamp.isoformat()
            except:
                pass
        
        return {
            "running": self.running,
            "interval_minutes": self.interval_seconds / 60,
            "model": self.llm_strategy.llm_client.model,
            "cache_valid": cache_valid,
            "last_analysis": last_analysis_time,
        }
