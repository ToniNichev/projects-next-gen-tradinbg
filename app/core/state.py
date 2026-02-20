"""
Application state management module.

This module provides thread-safe state management for trading and backtest operations.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional


@dataclass
class TradingState:
    """Current trading state snapshot with validation."""
    
    usdt_balance: float = 0.0
    base_balance: float = 0.0
    current_price: float = 0.0
    position_open: bool = False
    position_entry_price: float = 0.0
    position_amount: float = 0.0
    position_side: str = 'none'  # 'long', 'short', or 'none'
    stop_loss: float = 0.0
    take_profit: float = 0.0
    trailing_stop: float = 0.0
    trading_enabled: bool = False
    emergency_stop: bool = False
    last_update: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Validate trading state fields after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate all trading state constraints."""
        # Validate balances are non-negative
        if self.usdt_balance < 0:
            raise ValueError(f"usdt_balance must be >= 0, got {self.usdt_balance}")
        
        if self.base_balance < 0:
            raise ValueError(f"base_balance must be >= 0, got {self.base_balance}")
        
        # Validate current price is positive (only if set to non-zero)
        if self.current_price < 0:
            raise ValueError(f"current_price must be > 0, got {self.current_price}")
        
        # Validate position side
        valid_sides = ['long', 'short', 'none']
        if self.position_side not in valid_sides:
            raise ValueError(f"position_side must be in {valid_sides}, got {self.position_side}")
        
        # Validate stop loss and take profit when position is open
        if self.position_open:
            if self.stop_loss <= 0:
                raise ValueError(f"stop_loss must be > 0 when position_open is True, got {self.stop_loss}")
            
            if self.take_profit <= 0:
                raise ValueError(f"take_profit must be > 0 when position_open is True, got {self.take_profit}")


@dataclass
class BacktestState:
    """Backtest execution state with progress tracking."""
    
    running: bool = False
    progress: float = 0.0
    total_analyses: int = 0
    completed_analyses: int = 0
    current_strategy: str = ""
    results: List[Dict[str, Any]] = field(default_factory=list)


class ApplicationState:
    """
    Thread-safe application state manager.
    
    This class provides centralized state management for trading and backtest operations
    with thread-safe access using locks. It implements the singleton pattern to ensure
    a single instance across the application.
    
    Features:
    - Thread-safe state getters and setters
    - Trader instance management
    - History management with rolling window (max 250 records)
    - Backtest result storage with size limits (max 50 results)
    - Atomic operations (all-or-nothing updates)
    """
    
    def __init__(self):
        """Initialize application state with thread-safe locks."""
        self._lock = threading.Lock()
        self._trading_state = TradingState()
        self._backtest_state = BacktestState()
        self._history: List[Dict[str, Any]] = []
        self._backtest_results: List[Dict[str, Any]] = []
        self._trader_instance = None
        self._trader_lock = None
        self._exchange = None
        self._strategy_manager = None
        
        # Configuration constants
        self._max_history_size = 250
        self._max_backtest_results = 50
    
    # Trading State Methods
    
    def get_trading_state(self) -> TradingState:
        """
        Get current trading state (thread-safe).
        
        Returns:
            TradingState: A copy of the current trading state
        """
        with self._lock:
            # Return a copy to prevent external modification
            return TradingState(
                usdt_balance=self._trading_state.usdt_balance,
                base_balance=self._trading_state.base_balance,
                current_price=self._trading_state.current_price,
                position_open=self._trading_state.position_open,
                position_entry_price=self._trading_state.position_entry_price,
                position_amount=self._trading_state.position_amount,
                position_side=self._trading_state.position_side,
                stop_loss=self._trading_state.stop_loss,
                take_profit=self._trading_state.take_profit,
                trailing_stop=self._trading_state.trailing_stop,
                trading_enabled=self._trading_state.trading_enabled,
                emergency_stop=self._trading_state.emergency_stop,
                last_update=self._trading_state.last_update
            )
    
    def update_trading_state(self, **kwargs) -> None:
        """
        Update trading state fields atomically (thread-safe).
        
        All fields are updated atomically - either all succeed or none are applied.
        The last_update timestamp is automatically set to the current time.
        
        Args:
            **kwargs: Field names and values to update
            
        Raises:
            ValueError: If validation fails for any field
            AttributeError: If an invalid field name is provided
        """
        with self._lock:
            # Create a copy of current state for atomic update
            new_state_dict = {
                'usdt_balance': self._trading_state.usdt_balance,
                'base_balance': self._trading_state.base_balance,
                'current_price': self._trading_state.current_price,
                'position_open': self._trading_state.position_open,
                'position_entry_price': self._trading_state.position_entry_price,
                'position_amount': self._trading_state.position_amount,
                'position_side': self._trading_state.position_side,
                'stop_loss': self._trading_state.stop_loss,
                'take_profit': self._trading_state.take_profit,
                'trailing_stop': self._trading_state.trailing_stop,
                'trading_enabled': self._trading_state.trading_enabled,
                'emergency_stop': self._trading_state.emergency_stop,
                'last_update': datetime.utcnow()
            }
            
            # Apply updates to the copy
            for key, value in kwargs.items():
                if key not in new_state_dict:
                    raise AttributeError(f"Invalid field name: {key}")
                new_state_dict[key] = value
            
            # Validate the new state (will raise ValueError if invalid)
            new_state = TradingState(**new_state_dict)
            
            # If validation passes, apply the new state
            self._trading_state = new_state
    
    # Trader Instance Management
    
    def set_trader(self, trader, lock, exchange=None, strategy_manager=None) -> None:
        """
        Set trader instance and related objects atomically (thread-safe).
        
        Args:
            trader: Trader instance (LiveTrader or PaperTrader)
            lock: Threading lock for trader operations
            exchange: Optional exchange instance
            strategy_manager: Optional strategy manager instance
        """
        with self._lock:
            self._trader_instance = trader
            self._trader_lock = lock
            self._exchange = exchange
            self._strategy_manager = strategy_manager
    
    def get_trader(self):
        """
        Get trader instance (thread-safe).
        
        Returns:
            Trader instance or None if not set
        """
        with self._lock:
            return self._trader_instance
    
    def get_trader_lock(self):
        """
        Get trader lock (thread-safe).
        
        Returns:
            Threading lock or None if not set
        """
        with self._lock:
            return self._trader_lock
    
    def get_exchange(self):
        """
        Get exchange instance (thread-safe).
        
        Returns:
            Exchange instance or None if not set
        """
        with self._lock:
            return self._exchange
    
    def get_strategy_manager(self):
        """
        Get strategy manager instance (thread-safe).
        
        Returns:
            Strategy manager instance or None if not set
        """
        with self._lock:
            return self._strategy_manager
    
    # Backtest State Methods
    
    def get_backtest_state(self) -> BacktestState:
        """
        Get current backtest state (thread-safe).
        
        Returns:
            BacktestState: A copy of the current backtest state
        """
        with self._lock:
            # Return a copy to prevent external modification
            return BacktestState(
                running=self._backtest_state.running,
                progress=self._backtest_state.progress,
                total_analyses=self._backtest_state.total_analyses,
                completed_analyses=self._backtest_state.completed_analyses,
                current_strategy=self._backtest_state.current_strategy,
                results=self._backtest_state.results.copy()
            )
    
    def update_backtest_progress(self, **kwargs) -> None:
        """
        Update backtest progress atomically (thread-safe).
        
        Args:
            **kwargs: Field names and values to update
            
        Raises:
            AttributeError: If an invalid field name is provided
        """
        with self._lock:
            # Create a copy of current state
            new_state_dict = {
                'running': self._backtest_state.running,
                'progress': self._backtest_state.progress,
                'total_analyses': self._backtest_state.total_analyses,
                'completed_analyses': self._backtest_state.completed_analyses,
                'current_strategy': self._backtest_state.current_strategy,
                'results': self._backtest_state.results
            }
            
            # Apply updates
            for key, value in kwargs.items():
                if key not in new_state_dict:
                    raise AttributeError(f"Invalid field name: {key}")
                new_state_dict[key] = value
            
            # Create and apply new state
            self._backtest_state = BacktestState(**new_state_dict)
    
    def add_backtest_result(self, result: Dict[str, Any]) -> None:
        """
        Add backtest result with size limit enforcement (thread-safe).
        
        Maintains a maximum of 50 backtest results. When the limit is reached,
        the oldest result is removed.
        
        Args:
            result: Backtest result dictionary
        """
        with self._lock:
            self._backtest_results.append(result)
            
            # Enforce size limit - remove oldest results if exceeded
            if len(self._backtest_results) > self._max_backtest_results:
                self._backtest_results = self._backtest_results[-self._max_backtest_results:]
    
    def get_backtest_results(self) -> List[Dict[str, Any]]:
        """
        Get all backtest results (thread-safe).
        
        Returns:
            List[Dict[str, Any]]: Copy of backtest results list
        """
        with self._lock:
            return self._backtest_results.copy()
    
    def clear_backtest_results(self) -> None:
        """
        Clear all backtest results (thread-safe).
        """
        with self._lock:
            self._backtest_results.clear()
    
    # History Management Methods
    
    def add_history_record(self, record: Dict[str, Any]) -> None:
        """
        Add history record with rolling window (thread-safe).
        
        Maintains a maximum of 250 history records. When the limit is reached,
        the oldest record is removed (rolling window).
        
        Args:
            record: History record dictionary
        """
        with self._lock:
            # Add timestamp if not present
            if 'timestamp' not in record:
                record['timestamp'] = datetime.utcnow().isoformat()
            
            self._history.append(record)
            
            # Enforce rolling window - remove oldest records if exceeded
            if len(self._history) > self._max_history_size:
                self._history = self._history[-self._max_history_size:]
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get history records in reverse chronological order (thread-safe).
        
        Args:
            limit: Maximum number of records to return (default: 100)
            
        Returns:
            List[Dict[str, Any]]: Copy of history records (most recent first)
        """
        with self._lock:
            # Return most recent records up to limit, in reverse chronological order
            return list(reversed(self._history[-limit:]))
    
    def clear_history(self) -> None:
        """
        Clear all history records (thread-safe).
        """
        with self._lock:
            self._history.clear()


# Global singleton instance
_app_state: Optional[ApplicationState] = None
_app_state_lock = threading.Lock()


def get_app_state() -> ApplicationState:
    """
    Get or create application state singleton (thread-safe).
    
    This function implements the singleton pattern to ensure only one
    ApplicationState instance exists across the application.
    
    Returns:
        ApplicationState: The singleton application state instance
    """
    global _app_state
    
    # Double-checked locking pattern for thread-safe singleton
    if _app_state is None:
        with _app_state_lock:
            if _app_state is None:
                _app_state = ApplicationState()
    
    return _app_state
