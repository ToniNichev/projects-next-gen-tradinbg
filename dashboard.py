import logging
import logging as flask_logging
import os
import threading
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

try:
    from database import get_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

try:
    from auth import require_auth, is_auth_enabled, get_auth_config
    AUTH_AVAILABLE = True
except ImportError:
    AUTH_AVAILABLE = False
    flask_logging.warning("Authentication module not available. Dashboard will be unsecured!")
    
    # Create a no-op decorator if auth is not available
    def require_auth(f):
        return f

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "templates"))

# Reduce Flask logging noise - only show errors
log = flask_logging.getLogger('werkzeug')
log.setLevel(flask_logging.ERROR)

# Initialize rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["60 per minute"],  # Default rate limit
    storage_uri="memory://",
)

# Initialize CORS - will be configured on startup
cors = None

_state = {
    "balances": {"USDT": 0.0, "BASE": 0.0},
    "last_signal": None,
    "last_trade": None,
    "updated_at": None,
}
_history = []
_max_history = 250

# Backtest results storage
_backtest_results = []
_max_backtest_results = 50

# Backtest running state
_backtest_running = False
_current_backtest_id = None

# Manual trading - trader instance reference
_trader_instance = None
_trader_lock = None
_exchange_instance = None
_strategy_manager = None


@app.route("/")
@require_auth
def home():
    """Homepage - redirects to main dashboard UI"""
    from flask import redirect
    return redirect("/ui", code=302)


@app.route("/health")
def health_check():
    """Health check endpoint - no authentication required"""
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/state")
@require_auth
def get_state():
    return jsonify(_state)


@app.route("/history")
@require_auth
def get_history():
    return jsonify(
        {
            "history": list(_history),
            "last_signal": _state.get("last_signal"),
            "last_trade": _state.get("last_trade"),
        }
    )


@app.route("/api/candles/<timeframe>")
@require_auth
@limiter.limit("30 per minute")
def get_candles(timeframe):
    """Fetch historical candles for a specific timeframe"""
    try:
        import ccxt
        from config import BotConfig
        
        config = BotConfig.load()
        
        # Validate timeframe
        valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']
        if timeframe not in valid_timeframes:
            return jsonify({"error": f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes)}"}), 400
        
        # Get limit from query params (default 100, max 500)
        limit = min(int(request.args.get("limit", 100)), 500)
        
        # Build exchange connection
        exchange = ccxt.binanceus({
            "apiKey": config.binance_api_key,
            "secret": config.binance_api_secret,
            "enableRateLimit": True,
        })
        
        # Fetch OHLCV data
        ohlcv = exchange.fetch_ohlcv(config.symbol, timeframe, limit=limit)
        
        # Convert to format expected by frontend
        candles = [
            {
                "timestamp": datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc).isoformat(),
                "open": candle[1],
                "high": candle[2],
                "low": candle[3],
                "close": candle[4],
                "volume": candle[5],
            }
            for candle in ohlcv
        ]
        
        return jsonify({
            "timeframe": timeframe,
            "symbol": config.symbol,
            "candles": candles,
            "count": len(candles)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/ui")
@require_auth
def get_ui():
    return render_template("ui.html")


@app.route("/api/trades")
@require_auth
@limiter.limit("30 per minute")
def get_trades():
    """Get filtered trade history from database"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        
        # Parse query parameters
        limit = int(request.args.get("limit", 100))
        side = request.args.get("side")  # buy, sell
        exit_reason = request.args.get("exit_reason")  # stop_loss, take_profit, etc.
        days_back = request.args.get("days_back")  # Filter by days back
        
        # Build filters
        filters = {}
        if side:
            filters["side"] = side
        if exit_reason:
            filters["exit_reason"] = exit_reason
        if days_back:
            start_date = datetime.now(timezone.utc) - timedelta(days=int(days_back))
            filters["start_date"] = start_date
        
        # Query trades
        trades = db.get_trades(limit=limit, **filters)
        
        # Convert to JSON-serializable format IMMEDIATELY while objects are still in session
        # Access all attributes NOW to avoid detached instance errors
        trades_data = []
        for t in trades:
            try:
                # Ensure timestamp has timezone info (assume UTC if not specified)
                timestamp = t.timestamp
                if timestamp:
                    # If timestamp is naive (no timezone), assume it's UTC
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)
                    timestamp_str = timestamp.isoformat()
                else:
                    timestamp_str = None
                
                trade_dict = {
                    "id": t.id,
                    "timestamp": timestamp_str,
                    "side": t.side,
                    "price": float(t.price) if t.price else 0.0,
                    "amount": float(t.amount) if t.amount else 0.0,
                    "notional": float(t.notional) if t.notional else 0.0,
                    "fee": float(t.fee) if t.fee else 0.0,
                    "pnl": float(t.pnl) if t.pnl is not None else None,
                    "exit_reason": t.exit_reason,
                    "usdt_balance": float(t.usdt_balance) if t.usdt_balance else 0.0,
                    "base_balance": float(t.base_balance) if t.base_balance else 0.0,
                    "signal_direction": t.signal_direction,
                    "rsi": float(t.rsi) if t.rsi is not None else None,
                    "atr": float(t.atr) if t.atr is not None else None,
                }
                trades_data.append(trade_dict)
            except Exception as e:
                logging.error(f"Error serializing trade {t.id}: {e}")
                continue
        
        return jsonify({"trades": trades_data, "count": len(trades_data)})
    except Exception as e:
        logging.error(f"Error in /api/trades: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
@require_auth
@limiter.limit("30 per minute")
def get_stats():
    """Get trading statistics from database"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        stats = db.get_trade_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/positions")
@require_auth
@limiter.limit("30 per minute")
def get_positions():
    """Get open positions from database"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        positions = db.get_open_positions()
        
        positions_data = [
            {
                "id": p.id,
                "side": p.side,
                "entry_price": p.entry_price,
                "entry_time": p.entry_time.isoformat(),
                "amount": p.amount,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "trailing_stop": p.trailing_stop,
            }
            for p in positions
        ]
        
        return jsonify({"positions": positions_data, "count": len(positions_data)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/performance")
@require_auth
@limiter.limit("30 per minute")
def get_performance():
    """Get performance metrics"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        
        # Get basic stats
        stats = db.get_trade_stats()
        
        # Get recent trades for additional metrics
        recent_trades = db.get_trades(limit=100)
        
        # Calculate additional metrics
        if recent_trades:
            profitable_trades = [t for t in recent_trades if t.pnl and t.pnl > 0]
            losing_trades = [t for t in recent_trades if t.pnl and t.pnl < 0]
            
            avg_win = sum(t.pnl for t in profitable_trades) / len(profitable_trades) if profitable_trades else 0
            avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            # Profit factor
            total_wins = sum(t.pnl for t in profitable_trades)
            total_losses = abs(sum(t.pnl for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
            
            stats.update({
                "avg_win": float(avg_win),
                "avg_loss": float(avg_loss),
                "profit_factor": float(profit_factor),
                "recent_trades_count": len(recent_trades),
            })
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config")
@require_auth
@limiter.limit("30 per minute")
def get_config():
    """Get current bot configuration (reads from database if available, falls back to env vars)"""
    try:
        from config import BotConfig
        config = BotConfig.load()
        
        # Convert to dict (excluding sensitive data)
        config_dict = {
            "symbol": config.symbol,
            "timeframe": config.timeframe,
            "short_window": config.short_window,
            "long_window": config.long_window,
            "order_pct": config.order_pct,
            "initial_usdt": config.initial_usdt,
            "fee_rate": config.fee_rate,
            "slippage": config.slippage,
            "min_trend_strength": config.min_trend_strength,
            "rsi_period": config.rsi_period,
            "rsi_oversold": config.rsi_oversold,
            "rsi_overbought": config.rsi_overbought,
            "stop_loss_pct": config.stop_loss_pct,
            "take_profit_pct": config.take_profit_pct,
            "trailing_stop_pct": config.trailing_stop_pct,
            "use_trailing_stop": config.use_trailing_stop,
            "max_position_size": config.max_position_size,
            "min_position_size": config.min_position_size,
            "use_dynamic_sizing": config.use_dynamic_sizing,
            "atr_period": config.atr_period,
            "atr_stop_multiplier": config.atr_stop_multiplier,
            "use_atr_stops": config.use_atr_stops,
            "macd_fast": config.macd_fast,
            "macd_slow": config.macd_slow,
            "macd_signal": config.macd_signal,
            "require_macd_confirmation": config.require_macd_confirmation,
            "require_volume_confirmation": config.require_volume_confirmation,
            "volume_threshold": config.volume_threshold,
            "max_trades_per_day": config.max_trades_per_day,
            "use_multi_strategy": config.use_multi_strategy,
            "strategy_aggregation_mode": config.strategy_aggregation_mode,
            "min_signal_confidence": config.min_signal_confidence,
            "strategy_ema_enabled": config.strategy_ema_enabled,
            "strategy_ema_weight": config.strategy_ema_weight,
            "strategy_rsi_bb_enabled": config.strategy_rsi_bb_enabled,
            "strategy_rsi_bb_weight": config.strategy_rsi_bb_weight,
            "strategy_rsi_bb_rsi_oversold": config.strategy_rsi_bb_rsi_oversold,
            "strategy_rsi_bb_rsi_overbought": config.strategy_rsi_bb_rsi_overbought,
            "strategy_rsi_bb_bb_period": config.strategy_rsi_bb_bb_period,
            "strategy_rsi_bb_bb_std_dev": config.strategy_rsi_bb_bb_std_dev,
            "strategy_rsi_bb_stop_loss_pct": config.strategy_rsi_bb_stop_loss_pct,
            "strategy_rsi_bb_take_profit_pct": config.strategy_rsi_bb_take_profit_pct,
        }
        
        return jsonify(config_dict)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/config/debug", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def debug_config():
    """Debug endpoint to see what configuration is currently loaded"""
    try:
        from config import BotConfig
        config = BotConfig.load()
        
        # Get database configs if available
        db_configs = {}
        db_count = 0
        if DATABASE_AVAILABLE:
            try:
                db = get_database()
                db_configs = db.get_all_strategy_configs()
                db_count = len(db_configs)
            except:
                pass
        
        return jsonify({
            "success": True,
            "database_configs_count": db_count,
            "has_database": DATABASE_AVAILABLE,
            "config_summary": {
                "stop_loss_pct": config.stop_loss_pct,
                "take_profit_pct": config.take_profit_pct,
                "order_pct": config.order_pct,
                "strategy_aggregation_mode": config.strategy_aggregation_mode,
                "min_signal_confidence": config.min_signal_confidence,
                "strategy_ema_enabled": config.strategy_ema_enabled,
                "strategy_ema_weight": config.strategy_ema_weight,
                "strategy_rsi_bb_enabled": config.strategy_rsi_bb_enabled,
                "strategy_rsi_bb_weight": config.strategy_rsi_bb_weight,
                "strategy_macd_enabled": config.strategy_macd_enabled,
                "strategy_macd_weight": config.strategy_macd_weight,
            },
            "sample_db_keys": list(db_configs.keys())[:10] if db_configs else []
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategy-config", methods=["GET"])
@require_auth
@limiter.limit("30 per minute")
def get_strategy_config():
    """Get all strategy configurations from database"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        configs = db.get_all_strategy_configs()
        
        # If database is empty, return current env-based config
        if not configs:
            from config import BotConfig
            config = BotConfig.load()
            configs = {
                # Trading parameters
                "symbol": config.symbol,
                "timeframe": config.timeframe,
                "initial_usdt": config.initial_usdt,
                "order_pct": config.order_pct,
                
                # Indicators
                "rsi_period": config.rsi_period,
                "rsi_oversold": config.rsi_oversold,
                "rsi_overbought": config.rsi_overbought,
                "atr_period": config.atr_period,
                "atr_stop_multiplier": config.atr_stop_multiplier,
                "use_atr_stops": config.use_atr_stops,
                
                # Risk Management
                "stop_loss_pct": config.stop_loss_pct,
                "take_profit_pct": config.take_profit_pct,
                "trailing_stop_pct": config.trailing_stop_pct,
                "use_trailing_stop": config.use_trailing_stop,
                
                # Position Sizing
                "min_position_size": config.min_position_size,
                "max_position_size": config.max_position_size,
                "use_dynamic_sizing": config.use_dynamic_sizing,
                
                # Signal Filters
                "volume_threshold": config.volume_threshold,
                "require_volume_confirmation": config.require_volume_confirmation,
                "require_macd_confirmation": config.require_macd_confirmation,
                "max_trades_per_day": config.max_trades_per_day,
                
                # Multi-Strategy
                "strategy_aggregation_mode": config.strategy_aggregation_mode,
                "min_signal_confidence": config.min_signal_confidence,
                
                # EMA Strategy
                "strategy_ema_enabled": config.strategy_ema_enabled,
                "strategy_ema_weight": config.strategy_ema_weight,
                "short_window": config.short_window,
                "long_window": config.long_window,
                "min_trend_strength": config.min_trend_strength,
                
                # RSI+BB Strategy
                "strategy_rsi_bb_enabled": config.strategy_rsi_bb_enabled,
                "strategy_rsi_bb_weight": config.strategy_rsi_bb_weight,
                "strategy_rsi_bb_rsi_oversold": config.strategy_rsi_bb_rsi_oversold,
                "strategy_rsi_bb_rsi_overbought": config.strategy_rsi_bb_rsi_overbought,
                "strategy_rsi_bb_bb_period": config.strategy_rsi_bb_bb_period,
                "strategy_rsi_bb_bb_std_dev": config.strategy_rsi_bb_bb_std_dev,
                "strategy_rsi_bb_stop_loss_pct": config.strategy_rsi_bb_stop_loss_pct,
                "strategy_rsi_bb_take_profit_pct": config.strategy_rsi_bb_take_profit_pct,
                
                # MACD+Volume Strategy
                "strategy_macd_enabled": config.strategy_macd_enabled,
                "strategy_macd_weight": config.strategy_macd_weight,
                "strategy_macd_fast_period": config.strategy_macd_fast_period,
                "strategy_macd_slow_period": config.strategy_macd_slow_period,
                "strategy_macd_signal_period": config.strategy_macd_signal_period,
                "strategy_macd_volume_multiplier": config.strategy_macd_volume_multiplier,
                "strategy_macd_require_zero_cross": config.strategy_macd_require_zero_cross,
                "strategy_macd_stop_loss_pct": config.strategy_macd_stop_loss_pct,
                "strategy_macd_take_profit_pct": config.strategy_macd_take_profit_pct,
                
                # LLM Pattern Strategy
                "strategy_llm_enabled": config.strategy_llm_enabled,
                "strategy_llm_weight": config.strategy_llm_weight,
                "llm_ollama_model": config.llm_ollama_model,
                "llm_ollama_url": config.llm_ollama_url,
                "llm_lookback_days": config.llm_lookback_days,
                "llm_cache_minutes": config.llm_cache_minutes,
                "llm_timeout_seconds": config.llm_timeout_seconds,
                "llm_require_patterns": config.llm_require_patterns,
                "llm_backtest_sample_interval": config.llm_backtest_sample_interval,
            }
        
        return jsonify({
            "success": True,
            "config": configs,
            "source": "database" if configs else "env"
        })
    except Exception as e:
        logging.error(f"Error fetching strategy config: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategy-config/update", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")  # Increased for frequent config testing
def update_strategy_config():
    """Update strategy configurations in database"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        db = get_database()
        
        # Map of config keys to their types and categories
        config_mapping = {
            # Trading parameters
            "symbol": {"type": "str", "category": "trading"},
            "timeframe": {"type": "str", "category": "trading"},
            "initial_usdt": {"type": "float", "category": "trading"},
            "order_pct": {"type": "float", "category": "trading"},
            
            # Indicators
            "rsi_period": {"type": "int", "category": "indicators"},
            "rsi_oversold": {"type": "float", "category": "indicators"},
            "rsi_overbought": {"type": "float", "category": "indicators"},
            "atr_period": {"type": "int", "category": "indicators"},
            "atr_stop_multiplier": {"type": "float", "category": "indicators"},
            "use_atr_stops": {"type": "bool", "category": "indicators"},
            
            # Risk Management
            "stop_loss_pct": {"type": "float", "category": "risk"},
            "take_profit_pct": {"type": "float", "category": "risk"},
            "trailing_stop_pct": {"type": "float", "category": "risk"},
            "use_trailing_stop": {"type": "bool", "category": "risk"},
            
            # Position Sizing
            "min_position_size": {"type": "float", "category": "position"},
            "max_position_size": {"type": "float", "category": "position"},
            "use_dynamic_sizing": {"type": "bool", "category": "position"},
            
            # Signal Filters
            "volume_threshold": {"type": "float", "category": "filters"},
            "require_volume_confirmation": {"type": "bool", "category": "filters"},
            "require_macd_confirmation": {"type": "bool", "category": "filters"},
            "max_trades_per_day": {"type": "int", "category": "filters"},
            
            # Multi-Strategy
            "strategy_aggregation_mode": {"type": "str", "category": "multi_strategy"},
            "min_signal_confidence": {"type": "float", "category": "multi_strategy"},
            
            # EMA Strategy
            "strategy_ema_enabled": {"type": "bool", "category": "ema"},
            "strategy_ema_weight": {"type": "float", "category": "ema"},
            "short_window": {"type": "int", "category": "ema"},
            "long_window": {"type": "int", "category": "ema"},
            "min_trend_strength": {"type": "float", "category": "ema"},
            
            # RSI+BB Strategy
            "strategy_rsi_bb_enabled": {"type": "bool", "category": "rsi_bb"},
            "strategy_rsi_bb_weight": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_rsi_oversold": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_rsi_overbought": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_bb_period": {"type": "int", "category": "rsi_bb"},
            "strategy_rsi_bb_bb_std_dev": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_stop_loss_pct": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_take_profit_pct": {"type": "float", "category": "rsi_bb"},
            
            # MACD+Volume Strategy
            "strategy_macd_enabled": {"type": "bool", "category": "macd"},
            "strategy_macd_weight": {"type": "float", "category": "macd"},
            "strategy_macd_fast_period": {"type": "int", "category": "macd"},
            "strategy_macd_slow_period": {"type": "int", "category": "macd"},
            "strategy_macd_signal_period": {"type": "int", "category": "macd"},
            "strategy_macd_volume_multiplier": {"type": "float", "category": "macd"},
            "strategy_macd_require_zero_cross": {"type": "bool", "category": "macd"},
            "strategy_macd_stop_loss_pct": {"type": "float", "category": "macd"},
            "strategy_macd_take_profit_pct": {"type": "float", "category": "macd"},
            
            # LLM Pattern Strategy
            "strategy_llm_enabled": {"type": "bool", "category": "llm"},
            "strategy_llm_weight": {"type": "float", "category": "llm"},
            "llm_ollama_model": {"type": "str", "category": "llm"},
            "llm_ollama_url": {"type": "str", "category": "llm"},
            "llm_lookback_days": {"type": "int", "category": "llm"},
            "llm_cache_minutes": {"type": "int", "category": "llm"},
            "llm_timeout_seconds": {"type": "int", "category": "llm"},
            "llm_require_patterns": {"type": "bool", "category": "llm"},
            "llm_backtest_sample_interval": {"type": "int", "category": "llm"},
        }
        
        # Prepare configs for batch update
        configs_to_save = {}
        for key, value in data.items():
            if key in config_mapping:
                configs_to_save[key] = {
                    "value": value,
                    "type": config_mapping[key]["type"],
                    "category": config_mapping[key]["category"],
                    "description": f"Strategy parameter: {key}"
                }
        
        # Save to database
        count = db.set_multiple_strategy_configs(configs_to_save)
        
        return jsonify({
            "success": True,
            "message": f"Updated {count} configuration parameters",
            "updated_keys": list(configs_to_save.keys())
        })
    except Exception as e:
        logging.error(f"Error updating strategy config: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/presets", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_presets():
    """Get all strategy presets"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        presets = db.get_all_presets()
        
        return jsonify({
            "success": True,
            "presets": presets,
            "count": len(presets)
        })
    except Exception as e:
        logging.error(f"Error fetching presets: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/presets/<preset_name>", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_preset(preset_name):
    """Get a specific preset by name"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        preset = db.get_preset(preset_name)
        
        if not preset:
            return jsonify({"error": "Preset not found"}), 404
        
        return jsonify({
            "success": True,
            "preset": preset
        })
    except Exception as e:
        logging.error(f"Error fetching preset: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/presets", methods=["POST"])
@require_auth
@limiter.limit("20 per minute")
def save_preset_api():
    """Save a new preset or update existing"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        name = data.get("name")
        display_name = data.get("display_name")
        description = data.get("description", "")
        config = data.get("config")
        category = data.get("category", "custom")
        
        if not name or not display_name or not config:
            return jsonify({"error": "Missing required fields: name, display_name, config"}), 400
        
        db = get_database()
        preset = db.save_preset(
            name=name,
            display_name=display_name,
            description=description,
            config=config,
            category=category,
            is_builtin=False,
            is_default=False
        )
        
        return jsonify({
            "success": True,
            "message": f"Preset '{display_name}' saved successfully",
            "preset": preset
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Error saving preset: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/presets/<preset_name>", methods=["DELETE"])
@require_auth
@limiter.limit("20 per minute")
def delete_preset_api(preset_name):
    """Delete a preset"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        deleted = db.delete_preset(preset_name)
        
        if not deleted:
            return jsonify({"error": "Preset not found or cannot be deleted (built-in presets cannot be deleted)"}), 404
        
        return jsonify({
            "success": True,
            "message": f"Preset '{preset_name}' deleted successfully"
        })
    except Exception as e:
        logging.error(f"Error deleting preset: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/presets/<preset_name>/apply", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")
def apply_preset_api(preset_name):
    """Load a preset and apply its configuration"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        preset = db.get_preset(preset_name)
        
        if not preset:
            return jsonify({"error": "Preset not found"}), 404
        
        # Get the config from the preset
        config = preset["config"]
        
        # Map of config keys to their types and categories (reuse from update_strategy_config)
        config_mapping = {
            # Trading parameters
            "symbol": {"type": "str", "category": "trading"},
            "timeframe": {"type": "str", "category": "trading"},
            "initial_usdt": {"type": "float", "category": "trading"},
            "order_pct": {"type": "float", "category": "trading"},
            
            # Indicators
            "rsi_period": {"type": "int", "category": "indicators"},
            "rsi_oversold": {"type": "float", "category": "indicators"},
            "rsi_overbought": {"type": "float", "category": "indicators"},
            "atr_period": {"type": "int", "category": "indicators"},
            "atr_stop_multiplier": {"type": "float", "category": "indicators"},
            "use_atr_stops": {"type": "bool", "category": "indicators"},
            
            # Risk Management
            "stop_loss_pct": {"type": "float", "category": "risk"},
            "take_profit_pct": {"type": "float", "category": "risk"},
            "trailing_stop_pct": {"type": "float", "category": "risk"},
            "use_trailing_stop": {"type": "bool", "category": "risk"},
            
            # Position Sizing
            "min_position_size": {"type": "float", "category": "position"},
            "max_position_size": {"type": "float", "category": "position"},
            "use_dynamic_sizing": {"type": "bool", "category": "position"},
            
            # Signal Filters
            "volume_threshold": {"type": "float", "category": "filters"},
            "require_volume_confirmation": {"type": "bool", "category": "filters"},
            "require_macd_confirmation": {"type": "bool", "category": "filters"},
            "max_trades_per_day": {"type": "int", "category": "filters"},
            
            # Multi-Strategy
            "strategy_aggregation_mode": {"type": "str", "category": "multi_strategy"},
            "min_signal_confidence": {"type": "float", "category": "multi_strategy"},
            
            # EMA Strategy
            "strategy_ema_enabled": {"type": "bool", "category": "ema"},
            "strategy_ema_weight": {"type": "float", "category": "ema"},
            "short_window": {"type": "int", "category": "ema"},
            "long_window": {"type": "int", "category": "ema"},
            "min_trend_strength": {"type": "float", "category": "ema"},
            
            # RSI+BB Strategy
            "strategy_rsi_bb_enabled": {"type": "bool", "category": "rsi_bb"},
            "strategy_rsi_bb_weight": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_rsi_oversold": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_rsi_overbought": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_bb_period": {"type": "int", "category": "rsi_bb"},
            "strategy_rsi_bb_bb_std_dev": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_stop_loss_pct": {"type": "float", "category": "rsi_bb"},
            "strategy_rsi_bb_take_profit_pct": {"type": "float", "category": "rsi_bb"},
            
            # MACD+Volume Strategy
            "strategy_macd_enabled": {"type": "bool", "category": "macd"},
            "strategy_macd_weight": {"type": "float", "category": "macd"},
            "strategy_macd_fast_period": {"type": "int", "category": "macd"},
            "strategy_macd_slow_period": {"type": "int", "category": "macd"},
            "strategy_macd_signal_period": {"type": "int", "category": "macd"},
            "strategy_macd_volume_multiplier": {"type": "float", "category": "macd"},
            "strategy_macd_require_zero_cross": {"type": "bool", "category": "macd"},
            "strategy_macd_stop_loss_pct": {"type": "float", "category": "macd"},
            "strategy_macd_take_profit_pct": {"type": "float", "category": "macd"},
            
            # LLM Pattern Strategy
            "strategy_llm_enabled": {"type": "bool", "category": "llm"},
            "strategy_llm_weight": {"type": "float", "category": "llm"},
            "llm_ollama_model": {"type": "str", "category": "llm"},
            "llm_ollama_url": {"type": "str", "category": "llm"},
            "llm_lookback_days": {"type": "int", "category": "llm"},
            "llm_cache_minutes": {"type": "int", "category": "llm"},
            "llm_timeout_seconds": {"type": "int", "category": "llm"},
            "llm_require_patterns": {"type": "bool", "category": "llm"},
            "llm_backtest_sample_interval": {"type": "int", "category": "llm"},
        }
        
        # Prepare configs for batch update
        configs_to_save = {}
        for key, value in config.items():
            if key in config_mapping:
                configs_to_save[key] = {
                    "value": value,
                    "type": config_mapping[key]["type"],
                    "category": config_mapping[key]["category"],
                    "description": f"Strategy parameter: {key}"
                }
        
        # Save to database
        count = db.set_multiple_strategy_configs(configs_to_save)
        
        # Apply to running strategies (if strategy manager is available)
        applied_to_runtime = False
        if _strategy_manager:
            try:
                from config import BotConfig
                updated_config = BotConfig.load()
                _strategy_manager.reload_config(updated_config)
                applied_to_runtime = True
                logging.info(f"Preset '{preset_name}' applied to running strategies")
            except Exception as e:
                logging.warning(f"Failed to apply preset to runtime: {e}")
        
        return jsonify({
            "success": True,
            "message": f"Preset '{preset['display_name']}' applied successfully",
            "preset": preset,
            "configs_updated": count,
            "applied_to_runtime": applied_to_runtime,
            "requires_restart": "timeframe" in config or "symbol" in config
        })
        
    except Exception as e:
        logging.error(f"Error applying preset: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategy-config/apply", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")  # Increased for frequent config testing
def apply_strategy_config():
    """Apply configuration changes to running strategies (hot reload)"""
    global _strategy_manager
    
    if not _strategy_manager:
        return jsonify({
            "success": False,
            "message": "Multi-strategy system not enabled"
        }), 400
    
    try:
        # Reload strategy manager with new config
        from config import BotConfig
        config = BotConfig.load()
        
        # Update strategy manager
        _strategy_manager.reload_config(config)
        
        logging.info("Strategy configuration reloaded successfully")
        
        return jsonify({
            "success": True,
            "message": "Configuration applied successfully",
            "strategies_reloaded": len(_strategy_manager.strategies)
        })
    except Exception as e:
        logging.error(f"Error applying strategy config: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies")
@require_auth
@limiter.limit("30 per minute")
def get_strategies():
    """Get list of available strategies and their status"""
    if not _strategy_manager:
        return jsonify({
            "multi_strategy_enabled": False,
            "strategies": [],
            "message": "Multi-strategy system not enabled"
        })
    
    try:
        strategies_info = []
        for strategy in _strategy_manager.strategies:
            strategies_info.append({
                "name": strategy.name,
                "description": strategy.get_description(),
                "enabled": strategy.is_enabled(),
                "weight": strategy.get_weight(),
                "parameters": strategy.get_parameters(),
            })
        
        return jsonify({
            "multi_strategy_enabled": True,
            "aggregation_mode": _strategy_manager.aggregation_mode.value,
            "min_confidence": _strategy_manager.min_confidence,
            "strategies": strategies_info,
            "count": len(strategies_info),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies/stats")
@require_auth
@limiter.limit("30 per minute")
def get_strategy_stats():
    """Get performance statistics for each strategy"""
    if not _strategy_manager:
        return jsonify({
            "multi_strategy_enabled": False,
            "stats": {},
            "message": "Multi-strategy system not enabled"
        })
    
    try:
        stats = _strategy_manager.get_strategy_stats()
        
        # Add usage percentage
        total_signals_generated = sum(s["signals_generated"] for s in stats.values())
        total_signals_used = sum(s["signals_used"] for s in stats.values())
        
        for strategy_name, strategy_stats in stats.items():
            if total_signals_generated > 0:
                strategy_stats["generation_rate"] = (
                    strategy_stats["signals_generated"] / total_signals_generated * 100
                )
            else:
                strategy_stats["generation_rate"] = 0.0
            
            if total_signals_used > 0:
                strategy_stats["usage_rate"] = (
                    strategy_stats["signals_used"] / total_signals_used * 100
                )
            else:
                strategy_stats["usage_rate"] = 0.0
            
            if strategy_stats["signals_generated"] > 0:
                strategy_stats["acceptance_rate"] = (
                    strategy_stats["signals_used"] / strategy_stats["signals_generated"] * 100
                )
            else:
                strategy_stats["acceptance_rate"] = 0.0
        
        return jsonify({
            "multi_strategy_enabled": True,
            "total_signals_generated": total_signals_generated,
            "total_signals_used": total_signals_used,
            "stats": stats,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies/<strategy_name>/enable", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def enable_strategy(strategy_name):
    """Enable a strategy dynamically (no restart required)"""
    if not _strategy_manager:
        return jsonify({
            "error": "Multi-strategy system not enabled"
        }), 503
    
    try:
        _strategy_manager.enable_strategy(strategy_name)
        return jsonify({
            "success": True,
            "message": f"Strategy '{strategy_name}' enabled",
            "strategy": strategy_name,
            "enabled": True
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies/<strategy_name>/disable", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def disable_strategy(strategy_name):
    """Disable a strategy dynamically (no restart required)"""
    if not _strategy_manager:
        return jsonify({
            "error": "Multi-strategy system not enabled"
        }), 503
    
    try:
        # Prevent disabling all strategies
        enabled_strategies = _strategy_manager.get_enabled_strategies()
        if len(enabled_strategies) <= 1:
            return jsonify({
                "error": "Cannot disable the last active strategy. At least one strategy must remain enabled."
            }), 400
        
        _strategy_manager.disable_strategy(strategy_name)
        return jsonify({
            "success": True,
            "message": f"Strategy '{strategy_name}' disabled",
            "strategy": strategy_name,
            "enabled": False
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/strategies/<strategy_name>/toggle", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def toggle_strategy(strategy_name):
    """Toggle a strategy on/off dynamically - persists to database for backtests"""
    if not _strategy_manager:
        return jsonify({
            "error": "Multi-strategy system not enabled"
        }), 503
    
    # Import constants for strategy name mapping
    from strategies.constants import StrategyNames
    
    # Validate strategy name
    if not StrategyNames.is_valid_strategy(strategy_name):
        return jsonify({
            "error": f"Invalid strategy name: {strategy_name}"
        }), 400
    
    try:
        # Find the strategy
        strategy = None
        for s in _strategy_manager.strategies:
            if s.name == strategy_name:
                strategy = s
                break
        
        if not strategy:
            return jsonify({"error": f"Strategy '{strategy_name}' not found"}), 404
        
        # Check if currently enabled
        is_enabled = strategy.is_enabled()
        
        if is_enabled:
            # Check if this is the last enabled strategy
            enabled_strategies = _strategy_manager.get_enabled_strategies()
            if len(enabled_strategies) <= 1:
                return jsonify({
                    "error": "Cannot disable the last active strategy"
                }), 400
            _strategy_manager.disable_strategy(strategy_name)
            new_state = False
        else:
            _strategy_manager.enable_strategy(strategy_name)
            new_state = True
        
        # Persist to database so backtests also respect this setting
        config_key = StrategyNames.get_config_key(strategy_name)
        display_name = StrategyNames.get_display_name(strategy_name)
        
        if config_key:
            try:
                db = get_database()
                db.set_strategy_config(
                    key=config_key,
                    value=new_state,
                    value_type="bool",
                    category="strategy",
                    description=f"Enable/disable {display_name} strategy"
                )
                persisted = True
            except Exception as db_err:
                logging.warning(f"Failed to persist strategy toggle to database: {db_err}")
                persisted = False
        else:
            logging.warning(f"No config key found for strategy: {strategy_name}")
            persisted = False
        
        return jsonify({
            "success": True,
            "message": f"Strategy '{strategy_name}' {'enabled' if new_state else 'disabled'}",
            "strategy": strategy_name,
            "enabled": new_state,
            "persisted": persisted,
            "affects_backtest": persisted
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/backtest/run", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def run_backtest_api():
    """Run a backtest with custom parameters"""
    global _backtest_running, _current_backtest_id
    
    if _backtest_running:
        return jsonify({"error": "Backtest already running"}), 409
    
    try:
        params = request.get_json() or {}
        days_back = params.get("days_back", 30)
        preset_name = params.get("preset_name")  # Track preset if provided
        
        # Override config with custom parameters
        config_overrides = {}
        for key in ["short_window", "long_window", "order_pct", "initial_usdt",
                    "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
                    "use_trailing_stop", "min_position_size", "max_position_size",
                    "use_dynamic_sizing", "atr_stop_multiplier", "use_atr_stops",
                    "require_macd_confirmation", "require_volume_confirmation",
                    "volume_threshold", "min_trend_strength", "rsi_oversold",
                    "rsi_overbought"]:
            if key in params:
                config_overrides[key] = params[key]
        
        # Run backtest in background thread
        backtest_id = datetime.now(timezone.utc).isoformat()
        _current_backtest_id = backtest_id
        _backtest_running = True
        
        def run_backtest_thread():
            global _backtest_running, _backtest_results
            import time
            start_time = time.time()  # Track start time
            
            try:
                import logging
                from backtest import run_backtest
                
                # Run backtest with config overrides passed directly
                result = run_backtest(
                    days_back=days_back,
                    use_database=False,
                    config_overrides=config_overrides  # Pass overrides directly!
                )
                
                # Calculate duration
                duration_seconds = time.time() - start_time
                
                # Store result
                result_entry = {
                    "id": backtest_id,
                    "timestamp": backtest_id,
                    "days_back": days_back,
                    "duration_seconds": duration_seconds,  # NEW: Track duration
                    "start_time": start_time,  # NEW: Track start time
                    "parameters": config_overrides,
                    "preset_name": preset_name,  # Store preset name if provided
                    "result": result,
                    "status": "completed"
                }
                
                _backtest_results.insert(0, result_entry)
                if len(_backtest_results) > _max_backtest_results:
                    _backtest_results.pop()
                
            except Exception as e:
                logging.error(f"Backtest failed: {e}")
                duration_seconds = time.time() - start_time
                result_entry = {
                    "id": backtest_id,
                    "timestamp": backtest_id,
                    "days_back": days_back,
                    "duration_seconds": duration_seconds,  # NEW: Track duration even on failure
                    "parameters": config_overrides,
                    "error": str(e),
                    "status": "failed"
                }
                _backtest_results.insert(0, result_entry)
            finally:
                _backtest_running = False
        
        thread = threading.Thread(target=run_backtest_thread, daemon=True)
        thread.start()
        
        return jsonify({
            "message": "Backtest started",
            "backtest_id": backtest_id
        }), 202
        
    except Exception as e:
        _backtest_running = False
        return jsonify({"error": str(e)}), 500


@app.route("/api/backtest/status")
@require_auth
@limiter.limit("30 per minute")
def get_backtest_status():
    """Get current backtest status"""
    return jsonify({
        "running": _backtest_running,
        "current_id": _current_backtest_id
    })


@app.route("/api/backtest/results")
@require_auth
@limiter.limit("30 per minute")
def get_backtest_results():
    """Get all backtest results"""
    return jsonify({
        "results": _backtest_results,
        "count": len(_backtest_results)
    })


@app.route("/api/backtest/results/<backtest_id>")
@require_auth
@limiter.limit("30 per minute")
def get_backtest_result(backtest_id):
    """Get specific backtest result"""
    result = next((r for r in _backtest_results if r["id"] == backtest_id), None)
    if result:
        return jsonify(result)
    return jsonify({"error": "Backtest not found"}), 404


@app.route("/api/backtest/clear", methods=["POST", "DELETE"])
@require_auth
@limiter.limit("10 per minute")
def clear_backtest_results():
    """Clear all backtest results"""
    global _backtest_results
    count = len(_backtest_results)
    _backtest_results.clear()
    return jsonify({
        "message": f"Cleared {count} backtest result(s)",
        "count": count
    }), 200


@app.route("/api/backtest/timing-history")
@require_auth
@limiter.limit("30 per minute")
def get_timing_history():
    """Get historical backtest run times for progress estimation"""
    # Return last 20 backtest durations grouped by days_back
    history = {}
    for result in _backtest_results[:20]:
        if "duration_seconds" in result and result.get("status") == "completed":
            days = result["days_back"]
            if days not in history:
                history[days] = []
            history[days].append(result["duration_seconds"])
    
    # Calculate averages
    averages = {}
    for days, times in history.items():
        if times:
            averages[days] = sum(times) / len(times)
    
    return jsonify({
        "averages": averages,
        "raw_data": history
    })


# =============================================================================
# LLM VALIDATION API - Quick direction prediction testing
# =============================================================================

# Store validation results
_validation_results = []
_validation_running = False

@app.route("/api/llm/validate", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def run_llm_validation():
    """
    Run LLM direction validation tests.
    
    This is a quick test that validates if the LLM can predict market direction
    without the overhead of full per-candle backtesting.
    
    Request body:
        num_tests: Number of validation periods to test (default: 5)
        model: Ollama model to use (default: from config)
        quick: If true, run single quick test (default: false)
    """
    global _validation_running, _validation_results
    
    if _validation_running:
        return jsonify({"error": "Validation already running"}), 409
    
    try:
        data = request.get_json() or {}
        num_tests = data.get("num_tests", 5)
        quick_mode = data.get("quick", False)
        
        # Get model from config or request
        from config import BotConfig
        config = BotConfig.load()
        model = data.get("model", config.llm_ollama_model)
        
        # Import validator
        try:
            from llm_validator import LLMValidator
        except ImportError:
            return jsonify({"error": "LLM validator not available"}), 500
        
        _validation_running = True
        
        # Run validation
        validator = LLMValidator(
            ollama_url=config.llm_ollama_url,
            model=model,
            symbol=config.symbol,
        )
        
        if quick_mode:
            results = validator.quick_test()
        else:
            results = validator.run_validation(num_tests=num_tests)
        
        # Store results
        results["id"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        results["timestamp"] = datetime.now(timezone.utc).isoformat()
        _validation_results.insert(0, results)
        
        # Keep only last 20 results
        if len(_validation_results) > 20:
            _validation_results = _validation_results[:20]
        
        _validation_running = False
        
        return jsonify(results), 200
        
    except Exception as e:
        _validation_running = False
        logging.error(f"LLM validation failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/llm/validate/quick", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def run_quick_validation():
    """Run a single quick validation test (~15 seconds)."""
    global _validation_running
    
    if _validation_running:
        return jsonify({"error": "Validation already running"}), 409
    
    try:
        from config import BotConfig
        from llm_validator import LLMValidator
        
        config = BotConfig.load()
        _validation_running = True
        
        validator = LLMValidator(
            ollama_url=config.llm_ollama_url,
            model=config.llm_ollama_model,
            symbol=config.symbol,
        )
        
        results = validator.quick_test()
        results["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        _validation_running = False
        return jsonify(results), 200
        
    except Exception as e:
        _validation_running = False
        logging.error(f"Quick validation failed: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/llm/validate/results")
@require_auth
@limiter.limit("30 per minute")
def get_validation_results():
    """Get all validation results."""
    return jsonify({
        "results": _validation_results,
        "running": _validation_running,
    })


@app.route("/api/llm/validate/status")
@require_auth
@limiter.limit("30 per minute")
def get_validation_status():
    """Get current validation status."""
    return jsonify({
        "running": _validation_running,
        "last_result": _validation_results[0] if _validation_results else None,
    })


@app.route("/api/manual/status")
@require_auth
@limiter.limit("30 per minute")
def get_manual_status():
    """Get current status for manual trading"""
    if not _trader_instance:
        return jsonify({"error": "Manual trading not available", "available": False}), 503
    
    try:
        with _trader_lock:
            current_price = get_current_price()
            balances = _trader_instance.get_balances()
            portfolio_value = _trader_instance.get_portfolio_value(current_price)
            
            position_info = None
            if _trader_instance.open_position:
                pos = _trader_instance.open_position
                unrealized_pnl = 0.0
                if pos.side == "long":
                    unrealized_pnl = (current_price - pos.entry_price) * pos.amount
                else:  # short
                    unrealized_pnl = (pos.entry_price - current_price) * pos.amount
                
                position_info = {
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "amount": pos.amount,
                    "current_price": current_price,
                    "unrealized_pnl": unrealized_pnl,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "trailing_stop": pos.trailing_stop,
                    "entry_time": pos.entry_time,
                }
            
            return jsonify({
                "available": True,
                "current_price": current_price,
                "balances": balances,
                "portfolio_value": portfolio_value,
                "position": position_info,
                "can_buy": balances["USDT"] > 0 and (not _trader_instance.open_position or _trader_instance.open_position.side == "short"),
                "can_sell": _trader_instance.open_position is not None,
            })
    except Exception as e:
        return jsonify({"error": str(e), "available": False}), 500


@app.route("/api/manual/buy", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def manual_buy():
    """Execute manual buy order"""
    if not _trader_instance:
        return jsonify({"error": "Trader not available"}), 503
    
    try:
        from config import BotConfig
        config = BotConfig.load()
        
        params = request.get_json() or {}
        position_size = float(params.get("position_size", config.order_pct))
        
        # Validate position size
        if position_size < config.min_position_size:
            return jsonify({"error": f"Position size too small (min: {config.min_position_size*100}%)"}), 400
        if position_size > config.max_position_size:
            return jsonify({"error": f"Position size too large (max: {config.max_position_size*100}%)"}), 400
        
        with _trader_lock:
            # Check if already in long position
            if _trader_instance.open_position and _trader_instance.open_position.side == "long":
                return jsonify({"error": "Already in long position"}), 400
            
            # Check balance
            if _trader_instance.usdt_balance <= 0:
                return jsonify({"error": "Insufficient USDT balance"}), 400
            
            # Get current price
            current_price = get_current_price()
            
            # Create synthetic bullish signal
            signal = create_manual_signal("bullish", current_price, position_size, config)
            
            # Execute trade
            trade = _trader_instance.handle_signal(signal)
            
            if trade:
                # Update dashboard state
                update_state(
                    balances=_trader_instance.get_balances(),
                    last_trade=trade.to_dict(),
                    price=current_price,
                    signal_direction="bullish",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    trade_side="buy",
                )
                
                return jsonify({
                    "success": True,
                    "trade": trade.to_dict(),
                    "message": "Buy order executed successfully",
                    "balances": _trader_instance.get_balances(),
                })
            else:
                return jsonify({"error": "Trade execution failed"}), 400
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/sell", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def manual_sell():
    """Execute manual sell order"""
    if not _trader_instance:
        return jsonify({"error": "Trader not available"}), 503
    
    try:
        from config import BotConfig
        config = BotConfig.load()
        
        params = request.get_json() or {}
        position_size = float(params.get("position_size", config.order_pct))
        force_close = params.get("force_close", False)  # Force close current position
        
        with _trader_lock:
            current_price = get_current_price()
            
            # If we have a long position, close it
            if _trader_instance.open_position and _trader_instance.open_position.side == "long":
                trade = _trader_instance._close_position(current_price, "manual")
                
                if trade:
                    update_state(
                        balances=_trader_instance.get_balances(),
                        last_trade=trade.to_dict(),
                        price=current_price,
                        signal_direction="bearish",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        trade_side="sell",
                    )
                    
                    return jsonify({
                        "success": True,
                        "trade": trade.to_dict(),
                        "message": "Position closed successfully",
                        "balances": _trader_instance.get_balances(),
                    })
            
            # If no position or in short, open new short position
            elif not _trader_instance.open_position or force_close:
                # Validate position size
                if position_size < config.min_position_size:
                    return jsonify({"error": f"Position size too small (min: {config.min_position_size*100}%)"}), 400
                if position_size > config.max_position_size:
                    return jsonify({"error": f"Position size too large (max: {config.max_position_size*100}%)"}), 400
                
                # Create synthetic bearish signal
                signal = create_manual_signal("bearish", current_price, position_size, config)
                
                # Execute trade
                trade = _trader_instance.handle_signal(signal)
                
                if trade:
                    update_state(
                        balances=_trader_instance.get_balances(),
                        last_trade=trade.to_dict(),
                        price=current_price,
                        signal_direction="bearish",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        trade_side="sell",
                    )
                    
                    return jsonify({
                        "success": True,
                        "trade": trade.to_dict(),
                        "message": "Sell order executed successfully",
                        "balances": _trader_instance.get_balances(),
                    })
                else:
                    return jsonify({"error": "Trade execution failed"}), 400
            else:
                return jsonify({"error": "No position to close"}), 400
                
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/trading/mode")
@require_auth
@limiter.limit("30 per minute")
def get_trading_mode():
    """Get current trading mode and status"""
    try:
        from config import BotConfig
        config = BotConfig.load()
        
        # Check if we have a live trader
        is_live_trader = hasattr(_trader_instance, 'mode') if _trader_instance else False
        
        response = {
            "configured_mode": config.trading_mode,
            "live_trading_enabled": config.live_trading_enabled,
            "is_live_trader": is_live_trader,
        }
        
        if is_live_trader and _trader_instance:
            response.update({
                "actual_mode": _trader_instance.mode.value,
                "trading_enabled": _trader_instance.trading_enabled,
                "emergency_stop": _trader_instance.emergency_stop,
                "daily_trades": _trader_instance.daily_trades,
                "daily_pnl": _trader_instance.daily_pnl,
                "total_pnl": _trader_instance.total_pnl,
            })
        else:
            response.update({
                "actual_mode": "paper",
                "trading_enabled": True,
                "emergency_stop": False,
            })
        
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trading/emergency-stop", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def trigger_emergency_stop():
    """Trigger emergency stop - closes all positions and disables trading"""
    if not _trader_instance:
        return jsonify({"error": "Trader not available"}), 503
    
    # Check if this is a live trader with emergency stop capability
    if not hasattr(_trader_instance, 'trigger_emergency_stop'):
        return jsonify({
            "error": "Emergency stop not available in paper trading mode",
            "mode": "paper"
        }), 400
    
    try:
        params = request.get_json() or {}
        close_positions = params.get("close_positions", True)
        
        with _trader_lock:
            _trader_instance.trigger_emergency_stop(close_positions=close_positions)
        
        return jsonify({
            "success": True,
            "message": "🚨 EMERGENCY STOP TRIGGERED",
            "positions_closed": close_positions,
            "trading_enabled": False,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trading/enable", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def enable_trading():
    """Re-enable trading after emergency stop"""
    if not _trader_instance:
        return jsonify({"error": "Trader not available"}), 503
    
    if not hasattr(_trader_instance, 'enable_trading'):
        return jsonify({"error": "Not available in paper trading mode"}), 400
    
    try:
        with _trader_lock:
            # Reset emergency stop first if active
            if hasattr(_trader_instance, 'emergency_stop') and _trader_instance.emergency_stop:
                _trader_instance.reset_emergency_stop()
            _trader_instance.enable_trading()
        
        return jsonify({
            "success": True,
            "message": "Trading enabled",
            "trading_enabled": True,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trading/disable", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def disable_trading():
    """Disable trading (softer than emergency stop - doesn't close positions)"""
    if not _trader_instance:
        return jsonify({"error": "Trader not available"}), 503
    
    if not hasattr(_trader_instance, 'disable_trading'):
        return jsonify({"error": "Not available in paper trading mode"}), 400
    
    try:
        with _trader_lock:
            _trader_instance.disable_trading()
        
        return jsonify({
            "success": True,
            "message": "Trading disabled",
            "trading_enabled": False,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/trading/sync", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def sync_exchange():
    """Sync balances and positions from exchange"""
    if not _trader_instance:
        return jsonify({"error": "Trader not available"}), 503
    
    if not hasattr(_trader_instance, 'sync_balances'):
        return jsonify({"error": "Not available in paper trading mode"}), 400
    
    try:
        with _trader_lock:
            balances = _trader_instance.sync_balances()
            position = _trader_instance.sync_positions()
        
        return jsonify({
            "success": True,
            "balances": balances,
            "position": {
                "side": position.side,
                "amount": position.amount,
                "entry_price": position.entry_price,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
            } if position else None,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/manual/clear-trades", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")  # Lower limit for destructive operations
def clear_all_trades():
    """Clear all trade records from the database"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503

    try:
        db = get_database()

        # Get trade count before clearing for confirmation
        stats_before = db.get_trade_stats()
        count_before = stats_before["total_trades"]

        # Clear all trades
        deleted_count = db.clear_all_trades()

        # Verify the operation
        if deleted_count != count_before:
            return jsonify({
                "error": f"Clear operation inconsistent: expected {count_before}, deleted {deleted_count}"
            }), 500

        return jsonify({
            "success": True,
            "message": f"Cleared {deleted_count} trade records from database",
            "count": deleted_count
        }), 200

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# =====================================================================
# LLM PATTERN ANALYSIS ENDPOINTS
# =====================================================================

@app.route("/api/llm/latest")
@require_auth
@limiter.limit("30 per minute")
def get_latest_llm_analysis():
    """Get most recent LLM pattern analysis"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        db = get_database()
        analysis = db.get_latest_llm_analysis()
        
        if not analysis:
            return jsonify({"error": "No LLM analysis available yet"}), 404
        
        return jsonify({
            "timestamp": analysis.timestamp.isoformat(),
            "direction": analysis.direction,
            "confidence": analysis.confidence,
            "reasoning": analysis.reasoning,
            "patterns_found": json.loads(analysis.patterns_found),
            "suggested_stop_loss": analysis.suggested_stop_loss,
            "suggested_take_profit": analysis.suggested_take_profit,
            "suggested_position_size": analysis.suggested_position_size,
            "current_price": analysis.current_price,
            "recent_win_rate": analysis.recent_win_rate,
            "recent_pnl": analysis.recent_pnl,
            "cache_valid_until": analysis.cache_valid_until.isoformat(),
            "model_used": analysis.model_used,
            "analysis_duration_ms": analysis.analysis_duration_ms,
            "num_trades_analyzed": analysis.num_trades_analyzed,
            "analysis_period_days": analysis.analysis_period_days,
        })
    except Exception as e:
        logging.error(f"Error fetching LLM analysis: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/llm/history")
@require_auth
@limiter.limit("30 per minute")
def get_llm_analysis_history():
    """Get historical LLM analyses"""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        db = get_database()
        analyses = db.get_llm_analysis_history(limit=limit)
        
        return jsonify({
            "analyses": [{
                "timestamp": a.timestamp.isoformat(),
                "direction": a.direction,
                "confidence": a.confidence,
                "patterns_found": json.loads(a.patterns_found),
                "patterns_count": len(json.loads(a.patterns_found)) if a.patterns_found else 0,
                "current_price": a.current_price,
                "reasoning": a.reasoning[:100] + "..." if len(a.reasoning) > 100 else a.reasoning,
            } for a in analyses],
            "count": len(analyses)
        })
    except Exception as e:
        logging.error(f"Error fetching LLM history: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/llm/trigger", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")  # Lower limit for manual triggers
def trigger_llm_analysis():
    """Manually trigger LLM analysis (bypass cache)"""
    try:
        # Check if strategy manager is available
        if not _strategy_manager:
            return jsonify({"error": "Strategy manager not available"}), 503
        
        # Find LLM strategy in the manager
        from strategies.constants import StrategyNames
        llm_strategy = None
        for strategy in _strategy_manager.strategies:
            if strategy.name == StrategyNames.LLM_PATTERN:
                llm_strategy = strategy
                break
        
        if not llm_strategy:
            return jsonify({"error": "LLM strategy not configured"}), 503
        
        # Trigger analysis in background thread
        def run_analysis():
            try:
                # Clear cached analysis to force new analysis (but keep cache_minutes > 0 so results get saved)
                if llm_strategy.db_manager:
                    try:
                        from database import LLMAnalysis
                        with llm_strategy.db_manager.get_session() as session:
                            # Delete old cache entries to force fresh analysis
                            session.query(LLMAnalysis).delete()
                            session.commit()
                        logging.info("Cleared LLM analysis cache to force fresh analysis")
                    except Exception as e:
                        logging.warning(f"Could not clear cache, proceeding anyway: {e}")
                
                signal = llm_strategy.compute_signal(
                    exchange=_exchange_instance,
                    symbol="BTC/USDT",  # TODO: Get from config
                    timeframe="1h",
                    candle_data=None
                )
                
                logging.info(f"Manual LLM analysis completed: {signal.direction} (confidence: {signal.confidence:.2f})")
            except Exception as e:
                logging.error(f"Manual LLM analysis failed: {e}", exc_info=True)
        
        threading.Thread(target=run_analysis, daemon=True, name="ManualLLMAnalysis").start()
        
        return jsonify({
            "status": "triggered",
            "message": "LLM analysis started. Results will be available in 10-30 seconds."
        })
        
    except Exception as e:
        logging.error(f"Error triggering LLM analysis: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/llm/clear-cache", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def clear_llm_cache():
    """Clear all cached LLM analyses"""
    try:
        if not DATABASE_AVAILABLE:
            return jsonify({"error": "Database not available"}), 503
        
        from database import LLMAnalysis
        db = get_database()
        
        # Clear all LLM analyses from cache using proper session query
        with db.get_session() as session:
            count = session.query(LLMAnalysis).delete()
        
        logging.info(f"Cleared {count} LLM analysis cache entries")
        
        return jsonify({
            "status": "success",
            "message": f"Cleared {count} cached analysis entries",
            "count": count
        })
        
    except Exception as e:
        logging.error(f"Error clearing LLM cache: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/llm/test-connection", methods=["POST"])
@require_auth
@limiter.limit("20 per minute")
def test_llm_connection():
    """
    Test Ollama connection server-side.
    
    This endpoint tests the Ollama connection from the server, which works for
    remote deployments where the browser cannot directly access localhost:11434.
    
    Request body (optional):
        {
            "url": "http://localhost:11434",
            "model": "phi3"
        }
    
    Returns:
        {
            "success": true/false,
            "version": "0.1.x",
            "model_exists": true/false,
            "available_models": ["model1", "model2", ...],
            "url": "http://localhost:11434",
            "model": "phi3",
            "error": "error message if failed"
        }
    """
    try:
        # Get configuration
        config = BotConfig.load()
        data = request.get_json() or {}
        
        # Use provided URL/model or fall back to config
        ollama_url = data.get('url', config.llm_ollama_url)
        model_name = data.get('model', config.llm_ollama_model)
        
        logging.info(f"Testing Ollama connection: url={ollama_url}, model={model_name}")
        
        # Test 1: Check if Ollama service is running
        try:
            version_response = requests.get(
                f"{ollama_url}/api/version",
                timeout=5
            )
            version_response.raise_for_status()
            version_data = version_response.json()
            ollama_version = version_data.get('version', 'unknown')
        except requests.exceptions.ConnectionError:
            return jsonify({
                "success": False,
                "error": f"Cannot connect to Ollama at {ollama_url}. Is Ollama running?",
                "url": ollama_url,
                "model": model_name,
                "suggestion": "Run 'ollama serve' on the server"
            }), 503
        except requests.exceptions.Timeout:
            return jsonify({
                "success": False,
                "error": f"Connection to Ollama at {ollama_url} timed out",
                "url": ollama_url,
                "model": model_name
            }), 504
        except Exception as e:
            return jsonify({
                "success": False,
                "error": f"Failed to check Ollama version: {str(e)}",
                "url": ollama_url,
                "model": model_name
            }), 500
        
        # Test 2: Get list of available models
        try:
            models_response = requests.get(
                f"{ollama_url}/api/tags",
                timeout=5
            )
            models_response.raise_for_status()
            models_data = models_response.json()
            available_models = [m['name'] for m in models_data.get('models', [])]
            
            # Check if requested model exists (match by prefix)
            model_exists = any(m.startswith(model_name) for m in available_models)
            
        except Exception as e:
            logging.warning(f"Failed to get Ollama models list: {e}")
            available_models = []
            model_exists = False
        
        # Success response
        return jsonify({
            "success": True,
            "version": ollama_version,
            "model_exists": model_exists,
            "available_models": available_models,
            "url": ollama_url,
            "model": model_name
        })
        
    except Exception as e:
        logging.error(f"Error testing Ollama connection: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e),
            "url": ollama_url if 'ollama_url' in locals() else "unknown",
            "model": model_name if 'model_name' in locals() else "unknown"
        }), 500


# Settings page removed - merged into /strategy-config
# Old route kept for backwards compatibility, redirects to new page
@app.route("/settings")
@require_auth
def settings_page():
    """Redirect old settings page to new unified configuration page"""
    from flask import redirect, url_for
    return redirect(url_for('strategy_config_page'))


@app.route("/backtest")
@require_auth
def backtest_page():
    """Backtest runner page"""
    return render_template("backtest.html")


@app.route("/strategies")
@require_auth
def strategies_page():
    """Redirect to unified Strategy Center page"""
    from flask import redirect
    return redirect("/strategy-config")


@app.route("/strategy-config")
@require_auth
def strategy_config_page():
    """Strategy configuration and parameter adjustment page"""
    return render_template("strategy_config.html")


@app.route("/logout")
def logout():
    """
    Logout endpoint - displays logout page and instructions.
    Note: HTTP Basic Auth credentials are cached by the browser,
    so complete logout requires closing all browser windows.
    """
    from flask import make_response
    
    # If this is an API request (JSON), return JSON response
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({
            "message": "Logged out successfully",
            "note": "For API key auth, simply stop sending the key. For Basic Auth, close all browser windows."
        }), 200
    
    # For browser requests, show the logout page
    response = make_response(render_template("logout.html"))
    
    # Add headers to prevent caching of the logout page
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response


@app.route("/logout/clear")
def logout_clear():
    """
    Endpoint that returns 401 to force browser to clear Basic Auth credentials.
    This is called by JavaScript from the logout page.
    """
    from flask import Response
    
    # Return 401 with WWW-Authenticate to clear browser auth cache
    response = Response(
        'Authentication cleared. Please close all browser windows for complete logout.',
        401,
        {'WWW-Authenticate': 'Basic realm="Dashboard Login Required"'}
    )
    return response


def _record_history(timestamp, price, signal_direction, trade_side, ohlc=None):
    candle = {
        "open": price,
        "high": price,
        "low": price,
        "close": price,
    }
    if ohlc:
        candle.update(ohlc)
    entry = {
        "timestamp": timestamp,
        "price": candle["close"],
        "signal_direction": signal_direction,
        "trade_side": trade_side,
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
    }
    _history.append(entry)
    if len(_history) > _max_history:
        _history.pop(0)


def update_state(
    balances=None,
    last_signal=None,
    last_trade=None,
    price=None,
    signal_direction=None,
    timestamp=None,
    trade_side=None,
    ohlc=None,
    updated_at=None,
):
    if balances is not None:
        _state["balances"] = balances
    if last_signal is not None:
        _state["last_signal"] = last_signal
    if last_trade is not None:
        _state["last_trade"] = last_trade
    _state["updated_at"] = (
        updated_at or datetime.now(timezone.utc).isoformat()
    )
    if price is not None and signal_direction is not None:
        _record_history(
            timestamp or datetime.now(timezone.utc).isoformat(),
            price,
            signal_direction,
            trade_side,
            ohlc=ohlc,
        )


def set_trader(trader, lock, exchange=None, strategy_manager=None):
    """
    Set the trader instance for manual trading.
    
    Args:
        trader: PaperTrader instance
        lock: Threading lock for trader access
        exchange: CCXT exchange instance (optional, for live price)
        strategy_manager: StrategyManager instance (optional, for multi-strategy)
    """
    global _trader_instance, _trader_lock, _exchange_instance, _strategy_manager
    _trader_instance = trader
    _trader_lock = lock
    _exchange_instance = exchange
    _strategy_manager = strategy_manager
    logging.getLogger(__name__).info("Manual trading enabled - trader instance registered")
    if strategy_manager:
        logging.getLogger(__name__).info("Strategy manager registered for dashboard integration")


def get_current_price():
    """Get current market price from exchange or latest history"""
    try:
        # Try to get from exchange if available
        if _exchange_instance:
            from config import BotConfig
            config = BotConfig.load()
            ticker = _exchange_instance.fetch_ticker(config.symbol)
            return float(ticker['last'])
    except Exception as e:
        logging.getLogger(__name__).warning(f"Could not fetch live price: {e}")
    
    # Fallback to latest history price
    if _history:
        return _history[-1]['close']
    
    # Last fallback to state
    if _state.get('last_signal'):
        return _state['last_signal'].get('price', 0.0)
    
    raise ValueError("No price data available")


def create_manual_signal(direction: str, current_price: float, position_size: float, config) -> object:
    """
    Create a synthetic signal for manual trading.
    
    Args:
        direction: 'bullish' or 'bearish'
        current_price: Current market price
        position_size: Position size as decimal (0.2 = 20%)
        config: BotConfig instance for stop loss/take profit calculation
    
    Returns:
        StrategySignal object
    """
    from strategy import StrategySignal
    from datetime import datetime, timezone
    
    # Calculate stop loss and take profit based on config
    if direction == "bullish":
        if config.use_atr_stops:
            # Estimate ATR as 2% of price for manual trades
            estimated_atr = current_price * 0.02
            stop_loss = current_price - (estimated_atr * config.atr_stop_multiplier)
        else:
            stop_loss = current_price * (1 - config.stop_loss_pct)
        take_profit = current_price * (1 + config.take_profit_pct)
    else:  # bearish
        if config.use_atr_stops:
            estimated_atr = current_price * 0.02
            stop_loss = current_price + (estimated_atr * config.atr_stop_multiplier)
        else:
            stop_loss = current_price * (1 + config.stop_loss_pct)
        take_profit = current_price * (1 - config.take_profit_pct)
    
    return StrategySignal(
        direction=direction,
        price=current_price,
        short_ema=current_price,
        long_ema=current_price,
        trend_strength=0.0,
        timestamp=datetime.now(timezone.utc),
        info={"manual_trade": True, "source": "dashboard"},
        stop_loss=stop_loss,
        take_profit=take_profit,
        position_size=position_size,
        atr=current_price * 0.02,  # Estimated ATR
    )


def start_dashboard(host="0.0.0.0", port=8000):
    """Start the Flask dashboard with security configuration"""
    global cors
    
    # Load config to get CORS settings
    try:
        from config import BotConfig
        config = BotConfig.load()
        
        # Configure CORS
        allowed_origins = config.allowed_origins
        if allowed_origins == "*":
            cors = CORS(app, resources={r"/*": {"origins": "*"}})
        else:
            origins_list = [origin.strip() for origin in allowed_origins.split(",")]
            cors = CORS(app, resources={r"/*": {"origins": origins_list}})
        
        # Configure rate limiting
        if not config.enable_rate_limiting:
            limiter.enabled = False
        else:
            limiter.limit(f"{config.rate_limit_per_minute} per minute")
        
        # Log security status
        if AUTH_AVAILABLE and config.dashboard_auth_enabled:
            flask_logging.info("🔒 Dashboard authentication is ENABLED")
            flask_logging.info(f"   Username: {config.dashboard_username}")
        else:
            flask_logging.warning("⚠️  Dashboard authentication is DISABLED - all endpoints are public!")
        
        if config.enable_rate_limiting:
            flask_logging.info(f"🚦 Rate limiting enabled: {config.rate_limit_per_minute} requests/minute")
        else:
            flask_logging.info("⚠️  Rate limiting is DISABLED")
        
        flask_logging.info(f"🌐 CORS origins: {allowed_origins}")
        
    except Exception as e:
        flask_logging.error(f"Failed to load dashboard config: {e}")
        # Use defaults
        cors = CORS(app, resources={r"/*": {"origins": "*"}})
    
    def runner():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()

