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
        
        # Convert to JSON-serializable format
        trades_data = [
            {
                "id": t.id,
                "timestamp": t.timestamp.isoformat(),
                "side": t.side,
                "price": t.price,
                "amount": t.amount,
                "notional": t.notional,
                "fee": t.fee,
                "pnl": t.pnl,
                "exit_reason": t.exit_reason,
                "usdt_balance": t.usdt_balance,
                "base_balance": t.base_balance,
                "signal_direction": t.signal_direction,
                "rsi": t.rsi,
                "atr": t.atr,
            }
            for t in trades
        ]
        
        return jsonify({"trades": trades_data, "count": len(trades_data)})
    except Exception as e:
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
    """Get current bot configuration"""
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
        }
        
        return jsonify(config_dict)
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
            try:
                import logging
                from backtest import run_backtest
                from config import BotConfig
                import os
                
                # Temporarily override environment variables
                original_env = {}
                for key, value in config_overrides.items():
                    env_key = f"BOT_{key.upper()}"
                    original_env[env_key] = os.environ.get(env_key)
                    os.environ[env_key] = str(value)
                
                # Run backtest
                result = run_backtest(days_back=days_back, use_database=False)
                
                # Restore environment
                for env_key, original_value in original_env.items():
                    if original_value is None:
                        os.environ.pop(env_key, None)
                    else:
                        os.environ[env_key] = original_value
                
                # Store result
                result_entry = {
                    "id": backtest_id,
                    "timestamp": backtest_id,
                    "days_back": days_back,
                    "parameters": config_overrides,
                    "result": result,
                    "status": "completed"
                }
                
                _backtest_results.insert(0, result_entry)
                if len(_backtest_results) > _max_backtest_results:
                    _backtest_results.pop()
                
            except Exception as e:
                logging.error(f"Backtest failed: {e}")
                result_entry = {
                    "id": backtest_id,
                    "timestamp": backtest_id,
                    "days_back": days_back,
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


@app.route("/settings")
@require_auth
def settings_page():
    """Settings and configuration page"""
    return render_template("settings.html")


@app.route("/backtest")
@require_auth
def backtest_page():
    """Backtest runner page"""
    return render_template("backtest.html")


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

