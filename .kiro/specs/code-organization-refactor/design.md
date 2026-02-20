# Design Document: Code Organization Refactor

## Overview

This design addresses the critical maintainability issues in the trading bot codebase by establishing clear module boundaries, proper separation of concerns, and organized file structure. The refactoring will transform a monolithic 2600+ line dashboard.py into a well-structured, testable, and maintainable codebase while maintaining backward compatibility with existing API endpoints and external integrations.

The refactoring focuses on five key areas: splitting the monolithic dashboard module, eliminating global mutable state, organizing test files, removing legacy code, and establishing clear architectural boundaries between presentation, business logic, and data access layers.

## Architecture

The refactored architecture follows a layered approach with clear separation between API routes, UI routes, business logic, state management, and data access.

```mermaid
graph TB
    subgraph "Presentation Layer"
        API[API Routes Module]
        UI[UI Routes Module]
    end
    
    subgraph "Business Logic Layer"
        BT[Backtest Manager]
        TM[Trading Manager]
        SM[Strategy Manager]
        LLM[LLM Validator]
    end
    
    subgraph "State Management Layer"
        AS[Application State]
        CS[Config Service]
    end
    
    subgraph "Data Access Layer"
        DB[Database Manager]
        FS[File System]
    end
    
    API --> BT
    API --> TM
    API --> SM
    API --> LLM
    API --> AS
    API --> CS
    
    UI --> AS
    UI --> CS
    
    BT --> AS
    BT --> DB
    TM --> AS
    TM --> DB
    SM --> CS
    SM --> DB
    LLM --> DB
    
    AS --> DB
    CS --> DB
    CS --> FS


## Main Workflow

```mermaid
sequenceDiagram
    participant Client
    participant APIRoutes
    participant TradingManager
    participant AppState
    participant Database
    
    Client->>APIRoutes: POST /api/manual/buy
    APIRoutes->>TradingManager: execute_manual_trade(side, amount)
    TradingManager->>AppState: get_trader_instance()
    AppState-->>TradingManager: trader
    TradingManager->>trader: execute_market_buy(amount)
    trader->>Database: add_trade(trade_data)
    Database-->>trader: trade_record
    trader-->>TradingManager: trade_result
    TradingManager->>AppState: update_state(trade_result)
    TradingManager-->>APIRoutes: success_response
    APIRoutes-->>Client: JSON response
```

## Components and Interfaces

### Component 1: API Routes Module

**Purpose**: Handle all REST API endpoints for trading operations, configuration, and data retrieval

**File**: `app/api/routes.py`

**Interface**:
```python
from flask import Blueprint, jsonify, request
from typing import Dict, Any

api_bp = Blueprint('api', __name__, url_prefix='/api')

# Health & Status
@api_bp.route('/health', methods=['GET'])
def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    pass

@api_bp.route('/state', methods=['GET'])
def get_state() -> Dict[str, Any]:
    """Get current trading state"""
    pass

# Trading Operations
@api_bp.route('/manual/buy', methods=['POST'])
def manual_buy() -> Dict[str, Any]:
    """Execute manual buy order"""
    pass

@api_bp.route('/manual/sell', methods=['POST'])
def manual_sell() -> Dict[str, Any]:
    """Execute manual sell order"""
    pass

@api_bp.route('/trading/enable', methods=['POST'])
def enable_trading() -> Dict[str, Any]:
    """Enable automated trading"""
    pass

@api_bp.route('/trading/disable', methods=['POST'])
def disable_trading() -> Dict[str, Any]:
    """Disable automated trading"""
    pass

# Configuration
@api_bp.route('/config', methods=['GET'])
def get_config() -> Dict[str, Any]:
    """Get current configuration"""
    pass

@api_bp.route('/config/strategy', methods=['GET', 'POST'])
def strategy_config() -> Dict[str, Any]:
    """Get or update strategy configuration"""
    pass

# Backtest Operations
@api_bp.route('/backtest/run', methods=['POST'])
def run_backtest() -> Dict[str, Any]:
    """Run backtest with parameters"""
    pass

@api_bp.route('/backtest/status', methods=['GET'])
def get_backtest_status() -> Dict[str, Any]:
    """Get backtest progress status"""
    pass

@api_bp.route('/backtest/results', methods=['GET'])
def get_backtest_results() -> Dict[str, Any]:
    """Get all backtest results"""
    pass
```

**Responsibilities**:
- Request validation and parsing
- Authentication/authorization checks
- Delegate to business logic layer
- Format and return JSON responses
- Error handling and logging


### Component 2: UI Routes Module

**Purpose**: Handle HTML page rendering and template-based routes

**File**: `app/ui/routes.py`

**Interface**:
```python
from flask import Blueprint, render_template, redirect, url_for
from typing import Any

ui_bp = Blueprint('ui', __name__)

@ui_bp.route('/')
def home() -> str:
    """Redirect to main UI"""
    pass

@ui_bp.route('/ui')
def get_ui() -> str:
    """Render main trading dashboard"""
    pass

@ui_bp.route('/backtest')
def backtest_page() -> str:
    """Render backtest page"""
    pass

@ui_bp.route('/strategies')
def strategies_page() -> str:
    """Render strategies configuration page"""
    pass

@ui_bp.route('/settings')
def settings_page() -> str:
    """Render settings page"""
    pass

@ui_bp.route('/logout')
def logout() -> Any:
    """Handle user logout"""
    pass
```

**Responsibilities**:
- Render HTML templates
- Handle page navigation
- Session management
- Redirect logic

### Component 3: Application State Manager

**Purpose**: Centralized state management replacing global variables

**File**: `app/core/state.py`

**Interface**:
```python
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Dict, List, Optional, Any

@dataclass
class TradingState:
    """Current trading state"""
    usdt_balance: float = 0.0
    base_balance: float = 0.0
    current_price: float = 0.0
    position_open: bool = False
    position_entry_price: float = 0.0
    position_amount: float = 0.0
    trading_enabled: bool = False
    last_update: datetime = field(default_factory=datetime.utcnow)

@dataclass
class BacktestState:
    """Backtest execution state"""
    running: bool = False
    progress: float = 0.0
    total_analyses: int = 0
    completed_analyses: int = 0
    current_strategy: str = ""
    results: List[Dict[str, Any]] = field(default_factory=list)

class ApplicationState:
    """Thread-safe application state manager"""
    
    def __init__(self):
        self._lock = Lock()
        self._trading_state = TradingState()
        self._backtest_state = BacktestState()
        self._history: List[Dict[str, Any]] = []
        self._trader_instance = None
        self._trader_lock = None
        self._exchange = None
        self._strategy_manager = None
    
    # Trading State Methods
    def get_trading_state(self) -> TradingState:
        """Get current trading state (thread-safe)"""
        pass
    
    def update_trading_state(self, **kwargs) -> None:
        """Update trading state fields (thread-safe)"""
        pass
    
    def set_trader(self, trader, lock, exchange=None, strategy_manager=None) -> None:
        """Set trader instance and related objects"""
        pass
    
    def get_trader(self):
        """Get trader instance"""
        pass
    
    # Backtest State Methods
    def get_backtest_state(self) -> BacktestState:
        """Get current backtest state"""
        pass
    
    def update_backtest_progress(self, **kwargs) -> None:
        """Update backtest progress"""
        pass
    
    def add_backtest_result(self, result: Dict[str, Any]) -> None:
        """Add backtest result"""
        pass
    
    def clear_backtest_results(self) -> None:
        """Clear all backtest results"""
        pass
    
    # History Methods
    def add_history_record(self, record: Dict[str, Any]) -> None:
        """Add history record"""
        pass
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get history records"""
        pass
    
    def clear_history(self) -> None:
        """Clear history"""
        pass

# Global singleton instance
_app_state: Optional[ApplicationState] = None

def get_app_state() -> ApplicationState:
    """Get or create application state singleton"""
    global _app_state
    if _app_state is None:
        _app_state = ApplicationState()
    return _app_state
```

**Responsibilities**:
- Thread-safe state access
- State mutation tracking
- History management
- Trader instance lifecycle


### Component 4: Trading Manager

**Purpose**: Business logic for trading operations

**File**: `app/services/trading_manager.py`

**Interface**:
```python
from typing import Dict, Optional, Any
from config import BotConfig

class TradingManager:
    """Manages trading operations and business logic"""
    
    def __init__(self, app_state, config: BotConfig):
        self.app_state = app_state
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def execute_manual_buy(self, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute manual buy order
        
        Args:
            amount: Amount to buy (in base currency or percentage)
            price: Optional limit price
            
        Returns:
            Trade result dictionary
        """
        pass
    
    def execute_manual_sell(self, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute manual sell order
        
        Args:
            amount: Amount to sell (in base currency or percentage)
            price: Optional limit price
            
        Returns:
            Trade result dictionary
        """
        pass
    
    def enable_trading(self) -> Dict[str, bool]:
        """Enable automated trading"""
        pass
    
    def disable_trading(self) -> Dict[str, bool]:
        """Disable automated trading"""
        pass
    
    def trigger_emergency_stop(self) -> Dict[str, Any]:
        """Trigger emergency stop and close all positions"""
        pass
    
    def sync_exchange_state(self) -> Dict[str, Any]:
        """Sync state with exchange (balances, positions)"""
        pass
    
    def get_current_price(self) -> float:
        """Get current market price"""
        pass
    
    def create_manual_signal(self, direction: str, amount: float) -> Any:
        """Create manual trading signal"""
        pass

# Preconditions:
# - app_state must be initialized
# - config must be valid
# - trader instance must be set in app_state

# Postconditions:
# - All operations update app_state
# - All trades are logged to database
# - All errors are logged and returned as structured responses
```

**Responsibilities**:
- Execute trading operations
- Validate trade parameters
- Update application state
- Log trades to database
- Handle trading errors

### Component 5: Backtest Manager

**Purpose**: Business logic for backtesting operations

**File**: `app/services/backtest_manager.py`

**Interface**:
```python
from typing import Dict, Optional, Callable, Any
from config import BotConfig

class BacktestManager:
    """Manages backtest execution and results"""
    
    def __init__(self, app_state, config: BotConfig):
        self.app_state = app_state
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def run_backtest(
        self,
        days_back: int = 30,
        config_overrides: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Run backtest with parameters
        
        Args:
            days_back: Number of days to backtest
            config_overrides: Configuration overrides
            progress_callback: Progress update callback
            
        Returns:
            Backtest results dictionary
        """
        pass
    
    def get_backtest_status(self) -> Dict[str, Any]:
        """Get current backtest execution status"""
        pass
    
    def get_backtest_results(self) -> List[Dict[str, Any]]:
        """Get all backtest results"""
        pass
    
    def get_backtest_result(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """Get specific backtest result by ID"""
        pass
    
    def clear_backtest_results(self) -> Dict[str, int]:
        """Clear all backtest results"""
        pass
    
    def update_progress(self, **kwargs) -> None:
        """Update backtest progress in app state"""
        pass

# Preconditions:
# - app_state must be initialized
# - config must be valid
# - Exchange connection must be available

# Postconditions:
# - Backtest results stored in app_state
# - Progress updates sent via callback
# - Results persisted to database if enabled
```

**Responsibilities**:
- Execute backtests
- Track backtest progress
- Store and retrieve results
- Handle backtest errors


### Component 6: Configuration Service

**Purpose**: Centralized configuration management

**File**: `app/services/config_service.py`

**Interface**:
```python
from typing import Dict, Any, Optional
from config import BotConfig

class ConfigService:
    """Manages configuration loading, validation, and updates"""
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self._config_cache: Optional[BotConfig] = None
    
    def load_config(self, force_reload: bool = False) -> BotConfig:
        """
        Load configuration from database with fallback to environment
        
        Args:
            force_reload: Force reload from database
            
        Returns:
            BotConfig instance
        """
        pass
    
    def get_strategy_config(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Get strategy configuration"""
        pass
    
    def update_strategy_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update strategy configuration"""
        pass
    
    def get_presets(self) -> List[Dict[str, Any]]:
        """Get all configuration presets"""
        pass
    
    def get_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """Get specific preset by name"""
        pass
    
    def save_preset(self, preset_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save configuration preset"""
        pass
    
    def delete_preset(self, preset_name: str) -> Dict[str, bool]:
        """Delete configuration preset"""
        pass
    
    def apply_preset(self, preset_name: str) -> Dict[str, Any]:
        """Apply configuration preset"""
        pass
    
    def validate_config(self, config_data: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate configuration data
        
        Returns:
            (is_valid, error_messages)
        """
        pass

# Preconditions:
# - Database manager must be initialized (optional)
# - Environment variables must be set

# Postconditions:
# - Configuration changes persisted to database
# - Config cache invalidated on updates
# - Validation errors returned as structured list
```

**Responsibilities**:
- Load configuration from multiple sources
- Validate configuration changes
- Manage configuration presets
- Cache configuration for performance

## Data Models

### Model 1: TradingState

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TradingState:
    """Current trading state snapshot"""
    usdt_balance: float
    base_balance: float
    current_price: float
    position_open: bool
    position_entry_price: float
    position_amount: float
    position_side: str  # 'long' or 'short'
    stop_loss: float
    take_profit: float
    trailing_stop: float
    trading_enabled: bool
    emergency_stop: bool
    last_update: datetime
```

**Validation Rules**:
- usdt_balance >= 0
- base_balance >= 0
- current_price > 0
- position_side in ['long', 'short', 'none']
- stop_loss > 0 if position_open
- take_profit > 0 if position_open

### Model 2: BacktestResult

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Any

@dataclass
class BacktestResult:
    """Backtest execution result"""
    id: str
    timestamp: datetime
    days_back: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    pnl_pct: float
    buy_hold_pct: float
    final_value: float
    strategies_used: List[str]
    aggregation_mode: str
    config_snapshot: Dict[str, Any]
    chart_data: Dict[str, Any]
```

**Validation Rules**:
- days_back > 0
- total_trades >= 0
- winning_trades + losing_trades == total_trades
- win_rate between 0 and 100
- strategies_used not empty
- aggregation_mode in ['voting', 'weighted_voting', 'unanimous', 'any', 'best']


### Model 3: APIResponse

```python
from dataclasses import dataclass
from typing import Any, Optional, Dict

@dataclass
class APIResponse:
    """Standardized API response format"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        if self.message is not None:
            result["message"] = self.message
        if self.metadata is not None:
            result["metadata"] = self.metadata
        return result
```

**Validation Rules**:
- If success is False, error must be provided
- If success is True, data should be provided
- message is optional for both success and error cases

## Algorithmic Pseudocode

### Main Trading Workflow

```pascal
ALGORITHM executeManualTrade(side, amount, price)
INPUT: side (buy/sell), amount (float), price (optional float)
OUTPUT: trade_result (APIResponse)

BEGIN
  ASSERT side IN ["buy", "sell"]
  ASSERT amount > 0
  
  // Step 1: Get trader instance
  trader ← app_state.get_trader()
  IF trader IS NULL THEN
    RETURN APIResponse(success=false, error="Trader not initialized")
  END IF
  
  // Step 2: Validate trading is enabled
  trading_state ← app_state.get_trading_state()
  IF NOT trading_state.trading_enabled THEN
    RETURN APIResponse(success=false, error="Trading is disabled")
  END IF
  
  // Step 3: Create manual signal
  signal ← create_manual_signal(side, amount, price)
  
  // Step 4: Execute trade
  TRY
    IF side = "buy" THEN
      trade ← trader.execute_market_buy(amount, signal)
    ELSE
      trade ← trader.execute_market_sell(amount, signal)
    END IF
    
    // Step 5: Update application state
    app_state.update_trading_state(
      usdt_balance=trader.usdt_balance,
      base_balance=trader.base_balance,
      position_open=trader.open_position IS NOT NULL
    )
    
    // Step 6: Add to history
    app_state.add_history_record(trade.to_dict())
    
    RETURN APIResponse(success=true, data=trade.to_dict())
    
  CATCH error
    LOG error
    RETURN APIResponse(success=false, error=error.message)
  END TRY
END
```

**Preconditions**:
- app_state is initialized
- trader instance is set in app_state
- trading is enabled
- amount is positive
- side is valid ('buy' or 'sell')

**Postconditions**:
- Trade is executed or error is returned
- Application state is updated
- Trade is logged to database
- History record is added

**Loop Invariants**: N/A (no loops in this algorithm)

### Backtest Execution Workflow

```pascal
ALGORITHM runBacktest(days_back, config_overrides, progress_callback)
INPUT: days_back (int), config_overrides (dict), progress_callback (function)
OUTPUT: backtest_result (BacktestResult)

BEGIN
  ASSERT days_back > 0
  
  // Step 1: Initialize backtest state
  app_state.update_backtest_progress(
    running=true,
    progress=0.0,
    total_analyses=0,
    completed_analyses=0
  )
  
  // Step 2: Load configuration
  config ← config_service.load_config()
  IF config_overrides IS NOT NULL THEN
    config ← apply_overrides(config, config_overrides)
  END IF
  
  // Step 3: Fetch historical data
  candles ← fetch_historical_candles(days_back, config.symbol, config.timeframe)
  total_candles ← LENGTH(candles)
  
  app_state.update_backtest_progress(total_analyses=total_candles)
  
  // Step 4: Initialize paper trader
  trader ← PaperTrader(config)
  
  // Step 5: Process candles with progress tracking
  FOR i FROM 0 TO total_candles - 1 DO
    ASSERT i < total_candles  // Loop invariant: valid index
    
    candle ← candles[i]
    
    // Compute signal
    signal ← strategy_manager.compute_aggregate_signal(candle)
    
    // Execute trade if signal triggers
    trade ← trader.handle_signal(signal)
    
    // Update progress
    progress ← (i + 1) / total_candles
    app_state.update_backtest_progress(
      progress=progress,
      completed_analyses=i + 1
    )
    
    // Call progress callback for UI updates
    IF progress_callback IS NOT NULL THEN
      progress_callback(progress, i + 1, total_candles)
    END IF
  END FOR
  
  // Step 6: Calculate results
  result ← calculate_backtest_metrics(trader, candles, config)
  
  // Step 7: Store result
  app_state.add_backtest_result(result)
  
  // Step 8: Mark backtest as complete
  app_state.update_backtest_progress(running=false, progress=1.0)
  
  RETURN result
END
```

**Preconditions**:
- days_back > 0
- config is valid
- Exchange connection is available
- app_state is initialized

**Postconditions**:
- Backtest result is stored in app_state
- Progress is updated throughout execution
- Final progress is 1.0 and running is false
- All trades are logged

**Loop Invariants**:
- 0 <= i < total_candles
- completed_analyses == i + 1
- progress == (i + 1) / total_candles
- All processed candles have valid signals computed


### Configuration Loading Algorithm

```pascal
ALGORITHM loadConfiguration(force_reload)
INPUT: force_reload (boolean)
OUTPUT: config (BotConfig)

BEGIN
  // Step 1: Check cache
  IF NOT force_reload AND config_cache IS NOT NULL THEN
    RETURN config_cache
  END IF
  
  // Step 2: Try loading from database
  db_configs ← EMPTY_DICT
  IF database_available THEN
    TRY
      db_configs ← database.get_all_strategy_configs()
    CATCH error
      LOG "Database unavailable, using environment variables"
    END TRY
  END IF
  
  // Step 3: Load from environment with database overrides
  config ← BotConfig.load()  // Loads from env with db overrides
  
  // Step 4: Validate configuration
  is_valid, errors ← validate_config(config)
  IF NOT is_valid THEN
    LOG errors
    RAISE ConfigurationError(errors)
  END IF
  
  // Step 5: Cache configuration
  config_cache ← config
  
  RETURN config
END
```

**Preconditions**:
- Environment variables are set
- Database connection is available (optional)

**Postconditions**:
- Valid configuration is returned
- Configuration is cached
- Invalid configuration raises error with details

**Loop Invariants**: N/A

## Key Functions with Formal Specifications

### Function 1: update_trading_state()

```python
def update_trading_state(self, **kwargs) -> None:
    """Update trading state fields atomically"""
    pass
```

**Preconditions:**
- self._lock is initialized
- kwargs contains valid TradingState field names
- Field values match expected types

**Postconditions:**
- Trading state is updated atomically
- last_update timestamp is set to current time
- No partial updates occur (all-or-nothing)
- Thread-safe access guaranteed

**Loop Invariants:** N/A

### Function 2: execute_manual_buy()

```python
def execute_manual_buy(self, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
    """Execute manual buy order"""
    pass
```

**Preconditions:**
- amount > 0
- trader instance is set in app_state
- trading is enabled
- sufficient USDT balance available

**Postconditions:**
- Trade is executed or error is returned
- If successful: usdt_balance decreased, base_balance increased
- Trade record added to database
- Application state updated
- History record added

**Loop Invariants:** N/A

### Function 3: run_backtest()

```python
def run_backtest(
    self,
    days_back: int = 30,
    config_overrides: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """Run backtest with parameters"""
    pass
```

**Preconditions:**
- days_back > 0
- config_overrides (if provided) contains valid config keys
- progress_callback (if provided) is callable
- Exchange connection is available

**Postconditions:**
- Backtest result is returned
- Result is stored in app_state
- Progress updates sent via callback
- Backtest state.running is false at completion
- All trades are logged

**Loop Invariants:**
- For candle processing loop: 0 <= i < total_candles
- completed_analyses == i + 1 after each iteration
- progress increases monotonically

### Function 4: get_app_state()

```python
def get_app_state() -> ApplicationState:
    """Get or create application state singleton"""
    pass
```

**Preconditions:**
- None (can be called anytime)

**Postconditions:**
- Returns ApplicationState instance
- Same instance returned on subsequent calls (singleton)
- Instance is fully initialized

**Loop Invariants:** N/A

## Example Usage

```python
# Example 1: Initialize application
from app.core.state import get_app_state
from app.services.config_service import ConfigService
from app.services.trading_manager import TradingManager

# Get application state
app_state = get_app_state()

# Load configuration
config_service = ConfigService(db_manager=db)
config = config_service.load_config()

# Initialize trading manager
trading_manager = TradingManager(app_state, config)

# Example 2: Execute manual trade
result = trading_manager.execute_manual_buy(amount=0.001)
if result["success"]:
    print(f"Trade executed: {result['data']}")
else:
    print(f"Trade failed: {result['error']}")

# Example 3: Run backtest
from app.services.backtest_manager import BacktestManager

backtest_manager = BacktestManager(app_state, config)

def progress_update(progress, completed, total):
    print(f"Progress: {progress*100:.1f}% ({completed}/{total})")

result = backtest_manager.run_backtest(
    days_back=30,
    config_overrides={"stop_loss_pct": 0.03},
    progress_callback=progress_update
)

print(f"Backtest complete: {result['total_trades']} trades, {result['pnl_pct']:.2f}% return")

# Example 4: Update configuration
updates = {
    "strategy_ema_enabled": True,
    "strategy_ema_weight": 1.5,
    "stop_loss_pct": 0.025
}

result = config_service.update_strategy_config(updates)
if result["success"]:
    print("Configuration updated successfully")
```


## Correctness Properties

### Property 1: State Consistency
**Universal Quantification**: For all state updates, the application state remains consistent across all threads.

**Validates: Requirements 2.2, 2.3, 2.4, 8.10, 8.11**

```python
# Property: Thread-safe state updates
∀ thread₁, thread₂ ∈ Threads:
  update_trading_state(thread₁, field=value₁) ∧
  update_trading_state(thread₂, field=value₂)
  ⟹ final_state is consistent (no race conditions)

# Test: Concurrent state updates
def test_concurrent_state_updates():
    app_state = get_app_state()
    
    def update_balance(amount):
        for _ in range(100):
            state = app_state.get_trading_state()
            app_state.update_trading_state(usdt_balance=state.usdt_balance + amount)
    
    threads = [
        threading.Thread(target=update_balance, args=(1.0,)),
        threading.Thread(target=update_balance, args=(2.0,))
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Final balance should be exactly 300.0 (no lost updates)
    assert app_state.get_trading_state().usdt_balance == 300.0
```

### Property 2: API Response Consistency
**Universal Quantification**: All API endpoints return responses in the standardized APIResponse format.

**Validates: Requirements 3.12, 3.13, 3.14, 7.13, 7.14, 7.15**

```python
# Property: Consistent API responses
∀ endpoint ∈ APIEndpoints:
  response = endpoint(request)
  ⟹ response has fields {success, data?, error?, message?, metadata?}

# Test: API response format
def test_api_response_format():
    endpoints = [
        ('/api/health', 'GET'),
        ('/api/state', 'GET'),
        ('/api/manual/buy', 'POST'),
        ('/api/config', 'GET'),
    ]
    
    for path, method in endpoints:
        response = client.request(method, path)
        data = response.get_json()
        
        assert 'success' in data
        if not data['success']:
            assert 'error' in data
```

### Property 3: Configuration Validation
**Universal Quantification**: All configuration updates are validated before being applied.

**Validates: Requirements 6.5, 6.6, 6.9, 6.10, 6.11**

```python
# Property: Configuration validation
∀ config_update ∈ ConfigUpdates:
  apply_config(config_update)
  ⟹ validate_config(config_update) = (True, [])

# Test: Invalid configuration rejected
def test_invalid_config_rejected():
    config_service = ConfigService()
    
    invalid_updates = {
        "stop_loss_pct": -0.1,  # Negative value
        "order_pct": 1.5,  # > 1.0
        "unknown_field": "value"  # Unknown field
    }
    
    with pytest.raises(ValidationError):
        config_service.update_strategy_config(invalid_updates)
```

### Property 4: Trade Execution Atomicity
**Universal Quantification**: Trade execution is atomic - either fully succeeds or fully fails with no partial state.

**Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.7, 8.7, 8.8**

```python
# Property: Atomic trade execution
∀ trade ∈ Trades:
  execute_trade(trade)
  ⟹ (trade_in_database ∧ state_updated ∧ history_recorded) ∨
     (¬trade_in_database ∧ ¬state_updated ∧ ¬history_recorded)

# Test: Trade atomicity
def test_trade_atomicity():
    app_state = get_app_state()
    trading_manager = TradingManager(app_state, config)
    
    initial_state = app_state.get_trading_state()
    initial_history_len = len(app_state.get_history())
    
    # Simulate database failure
    with mock.patch('database.add_trade', side_effect=Exception("DB Error")):
        result = trading_manager.execute_manual_buy(amount=0.001)
        
        assert not result["success"]
        
        # State should be unchanged
        current_state = app_state.get_trading_state()
        assert current_state.usdt_balance == initial_state.usdt_balance
        assert current_state.base_balance == initial_state.base_balance
        
        # History should be unchanged
        assert len(app_state.get_history()) == initial_history_len
```

### Property 5: Module Boundary Enforcement
**Universal Quantification**: Presentation layer never directly accesses data layer - must go through business logic.

**Validates: Requirements 1.8, 1.9**

```python
# Property: Layered architecture
∀ route ∈ Routes:
  route.handler()
  ⟹ ¬directly_accesses(route, Database) ∧
     uses(route, BusinessLogicLayer)

# Test: No direct database access from routes
def test_routes_use_business_logic():
    # Static analysis check
    import ast
    
    with open('app/api/routes.py') as f:
        tree = ast.parse(f.read())
    
    # Check that routes don't import database directly
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
    import_froms = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    
    for imp in imports + import_froms:
        module = getattr(imp, 'module', None) or imp.names[0].name
        assert 'database' not in module.lower()
```

### Property 6: Backtest Progress Monotonicity
**Universal Quantification**: Backtest progress always increases monotonically from 0.0 to 1.0.

**Validates: Requirements 5.3, 5.4, 5.5, 5.6**

```python
# Property: Monotonic progress
∀ backtest ∈ Backtests:
  progress_sequence = [p₀, p₁, p₂, ..., pₙ]
  ⟹ p₀ = 0.0 ∧ pₙ = 1.0 ∧ ∀i: pᵢ ≤ pᵢ₊₁

# Test: Progress monotonicity
def test_backtest_progress_monotonic():
    app_state = get_app_state()
    backtest_manager = BacktestManager(app_state, config)
    
    progress_values = []
    
    def track_progress(progress, completed, total):
        progress_values.append(progress)
    
    backtest_manager.run_backtest(
        days_back=7,
        progress_callback=track_progress
    )
    
    # Check monotonicity
    for i in range(len(progress_values) - 1):
        assert progress_values[i] <= progress_values[i + 1]
    
    # Check bounds
    assert progress_values[0] >= 0.0
    assert progress_values[-1] == 1.0
```

## Error Handling

### Error Scenario 1: Database Connection Failure

**Condition**: Database becomes unavailable during operation
**Response**: 
- Log error with full context
- Return structured error response to client
- Fall back to environment configuration
- Continue operation with degraded functionality

**Recovery**: 
- Retry database connection on next operation
- Queue writes for later persistence
- Alert monitoring system

### Error Scenario 2: Invalid Configuration Update

**Condition**: User submits invalid configuration values
**Response**:
- Validate all fields before applying
- Return detailed validation errors
- Do not apply partial updates
- Keep existing configuration unchanged

**Recovery**:
- User corrects invalid values
- Resubmit configuration
- Validation passes and update succeeds

### Error Scenario 3: Trade Execution Failure

**Condition**: Exchange API call fails during trade execution
**Response**:
- Catch exception and log details
- Rollback any partial state changes
- Return error to user with reason
- Do not record failed trade in database

**Recovery**:
- User retries trade
- Check exchange connectivity
- Verify account status
- Attempt trade again

### Error Scenario 4: Concurrent State Modification

**Condition**: Multiple threads attempt to modify state simultaneously
**Response**:
- Use locks to serialize access
- Ensure atomic updates
- Prevent race conditions
- Maintain state consistency

**Recovery**:
- Automatic - locking mechanism handles this
- No user intervention required
- All updates applied in order

## Testing Strategy

### Unit Testing Approach

Each module will have comprehensive unit tests covering:

1. **State Management Tests** (`tests/unit/core/test_state.py`)
   - Thread-safe state updates
   - Singleton pattern enforcement
   - State consistency across operations
   - History management

2. **Trading Manager Tests** (`tests/unit/services/test_trading_manager.py`)
   - Manual trade execution
   - Trade validation
   - Error handling
   - State updates after trades

3. **Backtest Manager Tests** (`tests/unit/services/test_backtest_manager.py`)
   - Backtest execution
   - Progress tracking
   - Result storage
   - Configuration overrides

4. **Configuration Service Tests** (`tests/unit/services/test_config_service.py`)
   - Configuration loading
   - Validation logic
   - Preset management
   - Database fallback

5. **API Routes Tests** (`tests/unit/api/test_routes.py`)
   - Request validation
   - Response format
   - Authentication
   - Error responses

**Coverage Goals**: Minimum 80% code coverage for all modules

### Property-Based Testing Approach

Use property-based testing for critical invariants:

**Property Test Library**: pytest with hypothesis

1. **State Consistency Properties**
   - Generate random sequences of state updates
   - Verify state remains consistent
   - Check thread-safety under concurrent access

2. **Configuration Validation Properties**
   - Generate random configuration values
   - Verify validation catches all invalid inputs
   - Ensure valid configs always pass

3. **Trade Execution Properties**
   - Generate random trade parameters
   - Verify atomicity (all-or-nothing)
   - Check balance conservation

### Integration Testing Approach

Integration tests will verify module interactions:

1. **API to Business Logic Integration** (`tests/integration/test_api_integration.py`)
   - End-to-end API request flow
   - Verify data flows through layers correctly
   - Check database persistence

2. **Backtest Integration** (`tests/integration/test_backtest_integration.py`)
   - Full backtest execution
   - Progress callback integration
   - Result persistence

3. **Configuration Integration** (`tests/integration/test_config_integration.py`)
   - Configuration updates propagate to all components
   - Preset application affects trading behavior
   - Database and environment variable interaction

## Performance Considerations

1. **State Access Optimization**
   - Use read-write locks for state access
   - Cache frequently accessed state
   - Minimize lock contention

2. **Configuration Caching**
   - Cache loaded configuration
   - Invalidate cache only on updates
   - Reduce database queries

3. **API Response Time**
   - Target < 100ms for simple endpoints
   - Target < 500ms for complex operations
   - Use async operations for long-running tasks

4. **Memory Management**
   - Limit history size (rolling window)
   - Limit backtest result storage
   - Clean up old data periodically

## Security Considerations

1. **Authentication**
   - Maintain existing auth decorator
   - Apply to all sensitive endpoints
   - Session management unchanged

2. **Input Validation**
   - Validate all user inputs
   - Sanitize configuration values
   - Prevent injection attacks

3. **State Protection**
   - Thread-safe state access
   - Prevent unauthorized state modification
   - Audit log for state changes

4. **API Security**
   - Rate limiting (existing)
   - CORS configuration (existing)
   - API key validation (existing)

## Dependencies

### Internal Dependencies
- `config.py` - Configuration management
- `database.py` - Database access layer
- `live_trader.py` - Live trading execution
- `paper_trader.py` - Paper trading simulation
- `backtest.py` - Backtesting engine
- `strategies/` - Strategy implementations
- `auth.py` - Authentication

### External Dependencies
- Flask - Web framework
- SQLAlchemy - Database ORM
- ccxt - Exchange connectivity
- pandas - Data analysis
- pytest - Testing framework
- hypothesis - Property-based testing

### New Dependencies
None - refactoring uses existing dependencies

## Migration Strategy

### Phase 1: Create New Structure (No Breaking Changes)
1. Create new directory structure
2. Implement new modules alongside existing code
3. Add comprehensive tests
4. Verify all tests pass

### Phase 2: Gradual Migration
1. Update main.py to use new modules
2. Keep dashboard.py as fallback
3. Run both systems in parallel
4. Monitor for issues

### Phase 3: Complete Migration
1. Remove dashboard.py
2. Remove legacy strategy.py
3. Move tests to new structure
4. Update documentation

### Phase 4: Cleanup
1. Remove deprecated code
2. Optimize imports
3. Final testing
4. Deploy to production

## Backward Compatibility

All existing API endpoints will maintain the same:
- URL paths
- Request formats
- Response formats
- Authentication requirements

This ensures no breaking changes for external integrations.
