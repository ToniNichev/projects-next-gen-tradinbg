"""
Backtest Manager Service

This module provides business logic for backtesting operations, including:
- Running backtests with progress tracking
- Managing backtest results
- Querying backtest status
- Integration with the existing backtest.py module
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Callable, Any, List

from config import BotConfig


class BacktestManager:
    """
    Manages backtest execution and results.
    
    This service handles backtesting operations by executing historical strategy tests
    with progress tracking. It integrates with the existing backtest.py module and
    manages results in ApplicationState.
    
    Attributes:
        app_state: ApplicationState instance for state management
        config: BotConfig instance for configuration
        logger: Logger instance for logging
    """
    
    def __init__(self, app_state, config: BotConfig):
        """
        Initialize BacktestManager.
        
        Args:
            app_state: ApplicationState instance
            config: BotConfig instance
        """
        self.app_state = app_state
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._cancel_requested = False
    
    def run_backtest(
        self,
        days_back: int = 30,
        config_overrides: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None,
        backtest_id: Optional[str] = None,
        skip_llm: bool = True,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Run backtest with parameters and progress tracking.

        This method executes a backtest for the specified period with optional
        configuration overrides. Progress updates are sent via callback if provided.
        Results are stored in ApplicationState with a unique ID and timestamp.

        Args:
            days_back: Number of days to backtest (default: 30)
            config_overrides: Optional configuration overrides
            progress_callback: Optional callback for progress updates
                             Signature: callback(progress: float, completed: int, total: int)
            end_date: Optional UTC datetime anchoring the days_back window in
                the past instead of ending now — enables walk-forward testing
                across non-overlapping historical windows (see backtest.py's
                own end_date parameter, which this forwards to).
        
        Returns:
            Dict containing:
                - success: bool indicating if backtest completed successfully
                - data: Backtest result dictionary (if successful)
                - error: Error message (if failed)
        
        Preconditions:
            - days_back > 0
            - app_state is initialized
            - config is valid
        
        Postconditions:
            - Backtest result is stored in app_state
            - Progress updates sent via callback
            - Backtest state.running is false at completion
            - All trades are logged
        """
        try:
            # Validate input
            if days_back <= 0:
                return {
                    "success": False,
                    "error": "days_back must be greater than 0"
                }
            
            self.logger.info(f"Starting backtest for {days_back} days")
            
            # Initialize backtest state
            self._cancel_requested = False
            import time as _time
            self.update_progress(
                running=True,
                progress=0.0,
                total_analyses=0,
                completed_analyses=0,
                started_at=_time.time()
            )
            
            # Import backtest module
            try:
                from backtest import run_backtest as execute_backtest
            except ImportError as e:
                self.logger.error(f"Failed to import backtest module: {e}")
                self.update_progress(running=False, progress=0.0)
                return {
                    "success": False,
                    "error": f"Backtest module not available: {str(e)}"
                }
            
            # Create progress wrapper to update app state.
            # Uses **kwargs to match the keyword-argument signature that LLMPatternStrategy
            # uses when calling the progress callback:
            #   _progress_callback(total_analyses=..., total_candles=..., completed_analyses=...,
            #                      current_candle=..., eta_seconds=..., avg_time_per_analysis=...)
            def wrapped_progress_callback(**kwargs):
                """Wrapper to update app state and call user callback."""
                total_analyses = kwargs.get('total_analyses') or 0
                completed_analyses = kwargs.get('completed_analyses') or 0
                total_candles = kwargs.get('total_candles') or 0
                current_candle = kwargs.get('current_candle') or 0
                eta_seconds = kwargs.get('eta_seconds') or 0

                progress = completed_analyses / total_analyses if total_analyses > 0 else 0.0

                # Update app state
                self.update_progress(
                    progress=progress,
                    completed_analyses=completed_analyses,
                    total_analyses=total_analyses,
                    current_candle=current_candle,
                    total_candles=total_candles,
                    eta_seconds=eta_seconds,
                )

                # Abort if cancellation was requested
                if self._cancel_requested:
                    raise InterruptedError("Backtest cancelled by user")

                # Call user callback if provided
                if progress_callback:
                    try:
                        progress_callback(
                            progress=progress,
                            completed=completed_analyses,
                            total=total_analyses,
                        )
                    except Exception as e:
                        self.logger.warning(f"Progress callback error: {e}")
            
            # Execute backtest with wrapped callback
            # Build config overrides, disabling LLM strategy if skip_llm=True
            effective_overrides = dict(config_overrides or {})
            if skip_llm:
                effective_overrides["strategy_llm_enabled"] = False

            result = execute_backtest(
                days_back=days_back,
                use_database=False,
                config_overrides=effective_overrides if effective_overrides else None,
                progress_callback=wrapped_progress_callback,
                end_date=end_date,
            )

            # Use pre-generated ID if provided, otherwise generate new one
            if backtest_id is None:
                backtest_id = str(uuid.uuid4())
            timestamp = datetime.utcnow()

            # Create configuration snapshot
            config_snapshot = self._create_config_snapshot(config_overrides)

            # Surface the walk-forward window in the result's "parameters" so
            # it shows up in the dashboard's existing "Custom Parameters"
            # display without needing new UI plumbing. Only added when an
            # explicit anchor was used — a plain "last N days" run doesn't
            # need a window echoed back to it.
            display_parameters = dict(config_overrides or {})
            if end_date is not None:
                window_end = end_date
                window_start = window_end - timedelta(days=days_back)
                display_parameters["window_start"] = window_start.strftime("%Y-%m-%d")
                display_parameters["window_end"] = window_end.strftime("%Y-%m-%d")
            
            # Extract strategy information
            strategies_used = self._extract_strategies_used()
            aggregation_mode = self.config.strategy_aggregation_mode
            
            # Calculate trade statistics
            total_trades = result.get("trades", 0)
            winning_trades = 0
            losing_trades = 0
            
            # Parse chart data to count winning/losing trades
            chart_data = result.get("chart_data", {})
            
            # Ensure chart_data has required structure
            if not isinstance(chart_data, dict):
                self.logger.warning(f"chart_data is not a dict: {type(chart_data)}")
                chart_data = {}
            if "candles" not in chart_data:
                self.logger.warning("chart_data missing 'candles' field, initializing empty")
                chart_data["candles"] = []
            if "trades" not in chart_data:
                self.logger.warning("chart_data missing 'trades' field, initializing empty")
                chart_data["trades"] = []
            if "portfolio_values" not in chart_data:
                self.logger.warning("chart_data missing 'portfolio_values' field, initializing empty")
                chart_data["portfolio_values"] = []
            
            self.logger.info(f"Chart data summary: {len(chart_data.get('candles', []))} candles, "
                           f"{len(chart_data.get('trades', []))} trades, "
                           f"{len(chart_data.get('portfolio_values', []))} portfolio values")
            
            trades = chart_data.get("trades", [])
            
            for trade in trades:
                pnl = trade.get("pnl")
                if pnl is not None:  # Only count exit trades
                    if pnl > 0:
                        winning_trades += 1
                    elif pnl < 0:
                        losing_trades += 1
            
            # Calculate win rate
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
            
            # Build complete backtest result in format expected by frontend
            backtest_result = {
                "id": backtest_id,
                "timestamp": timestamp.isoformat() + "Z",
                "days_back": days_back,
                "status": "completed",
                "parameters": display_parameters,
                "result": {
                    "trades": total_trades,
                    "winning_trades": winning_trades,
                    "losing_trades": losing_trades,
                    "win_rate": win_rate,
                    "pnl": result.get("pnl", 0.0),
                    "pnl_pct": result.get("pnl_pct", 0.0),
                    "buy_hold_pct": result.get("buy_hold_pct", 0.0),
                    "final_value": result.get("final_value", 0.0),
                    "strategies_used": strategies_used,
                    "aggregation_mode": aggregation_mode,
                    "config_snapshot": config_snapshot,
                    "chart_data": chart_data
                }
            }
            
            # Store result in app state
            self.app_state.add_backtest_result(backtest_result)
            
            # Mark backtest as complete
            self.update_progress(running=False, progress=1.0)
            
            self.logger.info(f"Backtest completed successfully: {total_trades} trades, "
                           f"{result.get('pnl_pct', 0):.2f}% return")
            
            return {
                "success": True,
                "data": backtest_result
            }
            
        except InterruptedError:
            self.logger.info("Backtest cancelled by user")
            self.update_progress(running=False, progress=0.0)
            return {"success": False, "error": "cancelled"}
        except Exception as e:
            self.logger.error(f"Backtest execution failed: {e}", exc_info=True)
            
            # Mark backtest as failed
            self.update_progress(running=False, progress=0.0)
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_backtest_status(self) -> Dict[str, Any]:
        """
        Get current backtest execution status.
        
        Returns:
            Dict containing:
                - running: bool indicating if backtest is running
                - progress: float between 0.0 and 1.0
                - completed_analyses: int number of completed analyses
                - total_analyses: int total number of analyses
                - current_strategy: str name of current strategy
        
        Preconditions:
            - app_state is initialized
        
        Postconditions:
            - Returns current backtest state snapshot
        """
        backtest_state = self.app_state.get_backtest_state()

        return {
            "running": backtest_state.running,
            # progress is a nested object so the frontend can do statusData.progress.total_analyses etc.
            "progress": {
                "progress_pct": backtest_state.progress,
                "total_analyses": backtest_state.total_analyses,
                "completed_analyses": backtest_state.completed_analyses,
                "current_candle": backtest_state.current_candle,
                "total_candles": backtest_state.total_candles,
                "eta_seconds": backtest_state.eta_seconds,
            },
            "current_strategy": backtest_state.current_strategy,
        }
    
    def get_backtest_results(self) -> List[Dict[str, Any]]:
        """
        Get all stored backtest results.
        
        Returns:
            List of backtest result dictionaries sorted by timestamp (newest first)
        
        Preconditions:
            - app_state is initialized
        
        Postconditions:
            - Returns all stored results from ApplicationState
        """
        results = self.app_state.get_backtest_results()
        
        # Sort by timestamp (newest first)
        sorted_results = sorted(
            results,
            key=lambda r: r.get("timestamp", ""),
            reverse=True
        )
        
        return sorted_results
    
    def get_backtest_result(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get specific backtest result by ID.
        
        Args:
            backtest_id: Unique identifier of the backtest result
        
        Returns:
            Backtest result dictionary or None if not found
        
        Preconditions:
            - app_state is initialized
            - backtest_id is a valid string
        
        Postconditions:
            - Returns matching result or None
        """
        results = self.app_state.get_backtest_results()
        
        for result in results:
            if result.get("id") == backtest_id:
                return result
        
        return None
    
    def clear_backtest_results(self) -> Dict[str, int]:
        """
        Clear all backtest results from storage.
        
        Returns:
            Dict containing:
                - cleared: int number of results cleared
        
        Preconditions:
            - app_state is initialized
        
        Postconditions:
            - All results removed from ApplicationState
        """
        results = self.app_state.get_backtest_results()
        count = len(results)
        
        self.app_state.clear_backtest_results()
        
        self.logger.info(f"Cleared {count} backtest results")
        
        return {
            "cleared": count
        }
    

    def cancel_backtest(self) -> bool:
        """Signal the running backtest to stop at the next progress checkpoint."""
        if not self.app_state.get_backtest_state().running:
            return False
        self._cancel_requested = True
        self.logger.info("Backtest cancellation requested")
        return True

    def update_progress(self, **kwargs) -> None:
        """
        Update backtest progress in application state.
        
        This method provides a convenient way to update backtest progress fields
        in the application state. All updates are atomic and thread-safe.
        
        Args:
            **kwargs: Field names and values to update
                     Valid fields: running, progress, total_analyses,
                                  completed_analyses, current_strategy
        
        Preconditions:
            - app_state is initialized
            - kwargs contains valid BacktestState field names
        
        Postconditions:
            - Backtest state is updated atomically in app_state
        """
        try:
            self.app_state.update_backtest_progress(**kwargs)
        except Exception as e:
            self.logger.error(f"Failed to update backtest progress: {e}")
    
    def _create_config_snapshot(self, config_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create a snapshot of current configuration.
        
        Args:
            config_overrides: Optional configuration overrides applied
        
        Returns:
            Dict containing configuration snapshot
        """
        snapshot = {
            "symbol": self.config.symbol,
            "timeframe": self.config.timeframe,
            "stop_loss_pct": self.config.stop_loss_pct,
            "take_profit_pct": self.config.take_profit_pct,
            "order_pct": self.config.order_pct,
            "use_trailing_stop": self.config.use_trailing_stop,
            "trailing_stop_pct": self.config.trailing_stop_pct,
            "use_multi_strategy": self.config.use_multi_strategy,
            "strategy_aggregation_mode": self.config.strategy_aggregation_mode,
            "min_signal_confidence": self.config.min_signal_confidence,
            "strategy_ema_enabled": self.config.strategy_ema_enabled,
            "strategy_ema_weight": self.config.strategy_ema_weight,
            "strategy_rsi_bb_enabled": self.config.strategy_rsi_bb_enabled,
            "strategy_rsi_bb_weight": self.config.strategy_rsi_bb_weight,
            "strategy_macd_enabled": self.config.strategy_macd_enabled,
            "strategy_macd_weight": self.config.strategy_macd_weight,
        }
        
        # Include overrides if provided
        if config_overrides:
            snapshot["overrides"] = config_overrides
        
        return snapshot
    
    def _extract_strategies_used(self) -> List[str]:
        """
        Extract list of enabled strategies from configuration.
        
        Returns:
            List of strategy names that are enabled
        """
        strategies = []
        
        if self.config.use_multi_strategy:
            if self.config.strategy_ema_enabled:
                strategies.append("EMA Crossover")
            
            if self.config.strategy_rsi_bb_enabled:
                strategies.append("RSI + Bollinger Bands")
            
            if self.config.strategy_macd_enabled:
                strategies.append("MACD + Volume")
            
            # Check for LLM strategy
            try:
                from strategies import LLM_AVAILABLE
                if LLM_AVAILABLE and hasattr(self.config, 'strategy_llm_enabled'):
                    if self.config.strategy_llm_enabled:
                        strategies.append("LLM Pattern Analysis")
            except ImportError:
                pass
        else:
            strategies.append("Legacy Single Strategy")
        
        return strategies if strategies else ["No strategies enabled"]
