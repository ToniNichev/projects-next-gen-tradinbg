"""
API Routes Module

Provides REST API endpoints for trading operations, configuration, and data retrieval.
All endpoints use standardized APIResponse format and require authentication.

Endpoints:
- Health & Status: /api/health, /api/state
- Trading Operations: /api/manual/buy, /api/manual/sell, /api/trading/enable, /api/trading/disable
- Configuration: /api/config, /api/config/strategy
- Backtest Operations: /api/backtest/run, /api/backtest/status, /api/backtest/results
"""

import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from typing import Dict, Any

# Import authentication decorator
try:
    from auth import require_auth
    AUTH_AVAILABLE = True
except ImportError:
    # Create a no-op decorator if auth is not available
    def require_auth(f):
        return f
    AUTH_AVAILABLE = False

# Import business logic services
from app.core.state import get_app_state
from app.services.trading_manager import TradingManager
from app.services.config_service import ConfigService
from app.services.backtest_manager import BacktestManager
from config import BotConfig

# Initialize logger
logger = logging.getLogger(__name__)

# Create Flask blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api')

# Initialize services (will be set by main application)
_trading_manager = None
_config_service = None
_backtest_manager = None


def init_api_services(trading_manager: TradingManager, config_service: ConfigService, backtest_manager: BacktestManager):
    """
    Initialize API services.
    
    This function should be called by the main application to inject service dependencies.
    
    Args:
        trading_manager: TradingManager instance
        config_service: ConfigService instance
        backtest_manager: BacktestManager instance
    """
    global _trading_manager, _config_service, _backtest_manager
    _trading_manager = trading_manager
    _config_service = config_service
    _backtest_manager = backtest_manager
    logger.info("API services initialized")


def create_response(success: bool, data: Any = None, error: str = None, message: str = None) -> Dict[str, Any]:
    """
    Create standardized API response.
    
    Args:
        success: Whether the operation succeeded
        data: Response data (for successful operations)
        error: Error message (for failed operations)
        message: Optional human-readable message
        
    Returns:
        Dictionary with standardized response format
    """
    response = {"success": success}
    
    if data is not None:
        response["data"] = data
    
    if error is not None:
        response["error"] = error
    
    if message is not None:
        response["message"] = message
    
    return response


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@api_bp.route('/health', methods=['GET'])
@require_auth
def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.
    
    Returns system status and timestamp.
    
    Returns:
        JSON response with health status
        
    Validates: Requirement 3.1
    """
    try:
        app_state = get_app_state()
        trading_state = app_state.get_trading_state()
        
        health_data = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "trading_enabled": trading_state.trading_enabled,
            "emergency_stop": trading_state.emergency_stop,
            "services": {
                "trading_manager": _trading_manager is not None,
                "config_service": _config_service is not None,
                "backtest_manager": _backtest_manager is not None,
            }
        }
        
        return jsonify(create_response(success=True, data=health_data))
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Health check failed"
        )), 500


@api_bp.route('/state', methods=['GET'])
@require_auth
def get_state() -> Dict[str, Any]:
    """
    Get current trading state.
    
    Returns current balances, positions, and trading status from ApplicationState.
    
    Returns:
        JSON response with current trading state
        
    Validates: Requirement 3.2
    """
    try:
        app_state = get_app_state()
        trading_state = app_state.get_trading_state()
        
        state_data = {
            "usdt_balance": trading_state.usdt_balance,
            "base_balance": trading_state.base_balance,
            "current_price": trading_state.current_price,
            "position_open": trading_state.position_open,
            "position_entry_price": trading_state.position_entry_price,
            "position_amount": trading_state.position_amount,
            "position_side": trading_state.position_side,
            "stop_loss": trading_state.stop_loss,
            "take_profit": trading_state.take_profit,
            "trailing_stop": trading_state.trailing_stop,
            "trading_enabled": trading_state.trading_enabled,
            "emergency_stop": trading_state.emergency_stop,
            "last_update": trading_state.last_update.isoformat()
        }
        
        return jsonify(create_response(success=True, data=state_data))
    
    except Exception as e:
        logger.error(f"Failed to get state: {e}")
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Failed to retrieve state"
        )), 500


# ============================================================================
# Manual Trading Endpoints
# ============================================================================

@api_bp.route('/manual/buy', methods=['POST'])
@require_auth
def manual_buy() -> Dict[str, Any]:
    """
    Execute manual buy order.
    
    Request body:
        {
            "amount": float (required) - Amount to buy in base currency or percentage
            "price": float (optional) - Limit price (not currently used)
        }
    
    Returns:
        JSON response with trade execution result
        
    Validates: Requirement 3.3
    """
    if _trading_manager is None:
        return jsonify(create_response(
            success=False,
            error="Trading manager not initialized",
            message="Service not available"
        )), 503
    
    try:
        # Parse request data
        data = request.get_json()
        
        if not data:
            return jsonify(create_response(
                success=False,
                error="No data provided",
                message="Request body is required"
            )), 400
        
        # Validate required fields
        if 'amount' not in data:
            return jsonify(create_response(
                success=False,
                error="Missing required field: amount",
                message="Amount is required"
            )), 400
        
        amount = float(data['amount'])
        price = float(data.get('price')) if data.get('price') else None
        
        # Execute trade via trading manager
        result = _trading_manager.execute_manual_buy(amount=amount, price=price)
        
        # Return result with appropriate status code
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
    
    except ValueError as e:
        logger.warning(f"Invalid input for manual buy: {e}")
        return jsonify(create_response(
            success=False,
            error=f"Invalid input: {str(e)}",
            message="Invalid request data"
        )), 400
    
    except Exception as e:
        logger.error(f"Manual buy endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Internal server error"
        )), 500


@api_bp.route('/manual/sell', methods=['POST'])
@require_auth
def manual_sell() -> Dict[str, Any]:
    """
    Execute manual sell order.
    
    Request body:
        {
            "amount": float (required) - Amount to sell in base currency or percentage
            "price": float (optional) - Limit price (not currently used)
        }
    
    Returns:
        JSON response with trade execution result
        
    Validates: Requirement 3.4
    """
    if _trading_manager is None:
        return jsonify(create_response(
            success=False,
            error="Trading manager not initialized",
            message="Service not available"
        )), 503
    
    try:
        # Parse request data
        data = request.get_json()
        
        if not data:
            return jsonify(create_response(
                success=False,
                error="No data provided",
                message="Request body is required"
            )), 400
        
        # Validate required fields
        if 'amount' not in data:
            return jsonify(create_response(
                success=False,
                error="Missing required field: amount",
                message="Amount is required"
            )), 400
        
        amount = float(data['amount'])
        price = float(data.get('price')) if data.get('price') else None
        
        # Execute trade via trading manager
        result = _trading_manager.execute_manual_sell(amount=amount, price=price)
        
        # Return result with appropriate status code
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
    
    except ValueError as e:
        logger.warning(f"Invalid input for manual sell: {e}")
        return jsonify(create_response(
            success=False,
            error=f"Invalid input: {str(e)}",
            message="Invalid request data"
        )), 400
    
    except Exception as e:
        logger.error(f"Manual sell endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Internal server error"
        )), 500


# ============================================================================
# Trading Control Endpoints
# ============================================================================

@api_bp.route('/trading/enable', methods=['POST'])
@require_auth
def enable_trading() -> Dict[str, Any]:
    """
    Enable automated trading.
    
    Sets trading_enabled flag to true in ApplicationState.
    
    Returns:
        JSON response with trading status
        
    Validates: Requirement 3.5
    """
    if _trading_manager is None:
        return jsonify(create_response(
            success=False,
            error="Trading manager not initialized",
            message="Service not available"
        )), 503
    
    try:
        result = _trading_manager.enable_trading()
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
    
    except Exception as e:
        logger.error(f"Enable trading endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Failed to enable trading"
        )), 500


@api_bp.route('/trading/disable', methods=['POST'])
@require_auth
def disable_trading() -> Dict[str, Any]:
    """
    Disable automated trading.
    
    Sets trading_enabled flag to false in ApplicationState.
    
    Returns:
        JSON response with trading status
        
    Validates: Requirement 3.6
    """
    if _trading_manager is None:
        return jsonify(create_response(
            success=False,
            error="Trading manager not initialized",
            message="Service not available"
        )), 503
    
    try:
        result = _trading_manager.disable_trading()
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
    
    except Exception as e:
        logger.error(f"Disable trading endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Failed to disable trading"
        )), 500


# ============================================================================
# Configuration Endpoints
# ============================================================================

@api_bp.route('/config', methods=['GET'])
@require_auth
def get_config() -> Dict[str, Any]:
    """
    Get current configuration.
    
    Returns current bot configuration from ConfigService.
    
    Returns:
        JSON response with configuration data
        
    Validates: Requirement 3.7
    """
    if _config_service is None:
        return jsonify(create_response(
            success=False,
            error="Config service not initialized",
            message="Service not available"
        )), 503
    
    try:
        config = _config_service.load_config()
        
        # Convert config to dictionary
        config_data = {
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "stop_loss_pct": config.stop_loss_pct,
            "take_profit_pct": config.take_profit_pct,
            "trailing_stop_pct": config.trailing_stop_pct,
            "order_pct": config.order_pct,
            "use_multi_strategy": config.use_multi_strategy,
            "strategy_aggregation_mode": config.strategy_aggregation_mode,
            "min_signal_confidence": config.min_signal_confidence,
        }
        
        return jsonify(create_response(success=True, data=config_data))
    
    except Exception as e:
        logger.error(f"Failed to get config: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Failed to retrieve configuration"
        )), 500


@api_bp.route('/config/strategy', methods=['GET', 'POST'])
@require_auth
def strategy_config() -> Dict[str, Any]:
    """
    Get or update strategy configuration.
    
    GET: Returns current strategy configuration
    POST: Updates strategy configuration with validation
    
    Request body (POST):
        {
            "field_name": value,
            ...
        }
    
    Returns:
        JSON response with strategy configuration or update result
        
    Validates: Requirement 3.8
    """
    if _config_service is None:
        return jsonify(create_response(
            success=False,
            error="Config service not initialized",
            message="Service not available"
        )), 503
    
    try:
        if request.method == 'GET':
            # Get strategy configuration
            strategy_config_data = _config_service.get_strategy_config()
            return jsonify(create_response(success=True, data=strategy_config_data))
        
        else:  # POST
            # Update strategy configuration
            data = request.get_json()
            
            if not data:
                return jsonify(create_response(
                    success=False,
                    error="No data provided",
                    message="Request body is required"
                )), 400
            
            result = _config_service.update_strategy_config(data)
            status_code = 200 if result["success"] else 400
            return jsonify(result), status_code
    
    except Exception as e:
        logger.error(f"Strategy config endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Failed to process strategy configuration"
        )), 500


# ============================================================================
# Backtest Endpoints
# ============================================================================

@api_bp.route('/backtest/run', methods=['POST'])
@require_auth
def run_backtest() -> Dict[str, Any]:
    """
    Run backtest with parameters.
    
    Request body:
        {
            "days_back": int (optional, default: 30) - Number of days to backtest
            "config_overrides": dict (optional) - Configuration overrides
        }
    
    Returns:
        JSON response with backtest execution result
        
    Validates: Requirement 3.9
    """
    if _backtest_manager is None:
        return jsonify(create_response(
            success=False,
            error="Backtest manager not initialized",
            message="Service not available"
        )), 503
    
    try:
        # Parse request data
        data = request.get_json() or {}
        
        days_back = int(data.get('days_back', 30))
        config_overrides = data.get('config_overrides')
        
        # Validate days_back
        if days_back <= 0:
            return jsonify(create_response(
                success=False,
                error="days_back must be greater than 0",
                message="Invalid backtest parameters"
            )), 400
        
        # Execute backtest via backtest manager
        result = _backtest_manager.run_backtest(
            days_back=days_back,
            config_overrides=config_overrides
        )
        
        status_code = 200 if result["success"] else 400
        return jsonify(result), status_code
    
    except ValueError as e:
        logger.warning(f"Invalid input for backtest: {e}")
        return jsonify(create_response(
            success=False,
            error=f"Invalid input: {str(e)}",
            message="Invalid request data"
        )), 400
    
    except Exception as e:
        logger.error(f"Backtest run endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Backtest execution failed"
        )), 500


@api_bp.route('/backtest/status', methods=['GET'])
@require_auth
def get_backtest_status() -> Dict[str, Any]:
    """
    Get backtest progress status.
    
    Returns current backtest execution status including progress and running state.
    
    Returns:
        JSON response with backtest status
        
    Validates: Requirement 3.10
    """
    if _backtest_manager is None:
        return jsonify(create_response(
            success=False,
            error="Backtest manager not initialized",
            message="Service not available"
        )), 503
    
    try:
        result = _backtest_manager.get_backtest_status()
        return jsonify(create_response(success=True, data=result))
    
    except Exception as e:
        logger.error(f"Backtest status endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Failed to retrieve backtest status"
        )), 500


@api_bp.route('/backtest/results', methods=['GET'])
@require_auth
def get_backtest_results() -> Dict[str, Any]:
    """
    Get all backtest results.
    
    Returns all stored backtest results from ApplicationState.
    
    Returns:
        JSON response with backtest results list
        
    Validates: Requirement 3.11
    """
    if _backtest_manager is None:
        return jsonify(create_response(
            success=False,
            error="Backtest manager not initialized",
            message="Service not available"
        )), 503
    
    try:
        results = _backtest_manager.get_backtest_results()
        return jsonify(create_response(success=True, data=results))
    
    except Exception as e:
        logger.error(f"Backtest results endpoint failed: {e}", exc_info=True)
        return jsonify(create_response(
            success=False,
            error=str(e),
            message="Failed to retrieve backtest results"
        )), 500
