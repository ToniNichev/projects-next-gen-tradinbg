"""
Trading-control API endpoints.

Routes
------
GET  /api/manual/status            Current position, balances, price
POST /api/manual/buy               Open/scale-in long position
POST /api/manual/sell              Close position / execute bearish signal
POST /api/manual/clear-trades      Wipe all trade history & reset balance
GET  /api/trading/mode             Current trading mode & safety status
POST /api/trading/emergency-stop   Close all positions, halt trading
POST /api/trading/enable           Re-enable automated trading
POST /api/trading/disable          Disable automated trading (soft halt)
POST /api/trading/sync             Sync balances/positions from exchange
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.extensions import limiter, require_auth
from app.core.state import get_app_state

try:
    from database import get_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

logger = logging.getLogger(__name__)

trading_bp = Blueprint("trading", __name__)


def _get_trader_and_lock():
    """Return (trader, lock) from ApplicationState, or (None, None)."""
    app_state = get_app_state()
    return app_state.get_trader(), app_state.get_trader_lock()


def _get_current_price(exchange, symbol: str) -> float:
    """Fetch live price from exchange, fall back to ApplicationState."""
    try:
        if exchange is not None:
            ticker = exchange.fetch_ticker(symbol)
            return float(ticker["last"])
    except Exception as exc:
        logger.warning("Could not fetch live price: %s", exc)

    # Fallback: last known price from state
    ts = get_app_state().get_trading_state()
    if ts.current_price > 0:
        return ts.current_price

    raise ValueError("No price data available")


def _create_manual_signal(direction: str, price: float, position_size: float, config):
    """Build a synthetic StrategySignal for a manual trade."""
    from strategies.base_strategy import StrategySignal

    if direction == "bullish":
        if config.use_atr_stops:
            atr_est = price * 0.02
            stop_loss = price - atr_est * config.atr_stop_multiplier
        else:
            stop_loss = price * (1 - config.stop_loss_pct)
        take_profit = price * (1 + config.take_profit_pct)
    else:
        if config.use_atr_stops:
            atr_est = price * 0.02
            stop_loss = price + atr_est * config.atr_stop_multiplier
        else:
            stop_loss = price * (1 + config.stop_loss_pct)
        take_profit = price * (1 - config.take_profit_pct)

    return StrategySignal(
        direction=direction,
        price=price,
        confidence=1.0,
        timestamp=datetime.now(timezone.utc),
        strategy_name="Manual",
        stop_loss=stop_loss,
        take_profit=take_profit,
        position_size=position_size,
        indicators={"atr": price * 0.02},
        info={"manual_trade": True, "source": "dashboard"},
    )


# ---------------------------------------------------------------------------
# Manual status
# ---------------------------------------------------------------------------

@trading_bp.route("/api/manual/status")
@require_auth
@limiter.limit("30 per minute")
def get_manual_status():
    trader, lock = _get_trader_and_lock()
    if trader is None:
        return jsonify({"error": "Manual trading not available", "available": False}), 503

    try:
        from config import BotConfig
        config = BotConfig.load()
        exchange = get_app_state().get_exchange()

        with lock:
            price = _get_current_price(exchange, config.symbol)
            balances = trader.get_balances()
            portfolio_value = trader.get_portfolio_value(price)

            position_info = None
            if trader.open_position:
                pos = trader.open_position
                unrealised = (price - pos.entry_price) * pos.amount if pos.side == "long" else (pos.entry_price - price) * pos.amount
                position_info = {
                    "side": pos.side,
                    "entry_price": pos.entry_price,
                    "amount": pos.amount,
                    "current_price": price,
                    "unrealized_pnl": unrealised,
                    "stop_loss": pos.stop_loss,
                    "take_profit": pos.take_profit,
                    "trailing_stop": pos.trailing_stop,
                    "entry_time": pos.entry_time,
                }

        return jsonify({
            "available": True,
            "current_price": price,
            "balances": balances,
            "portfolio_value": portfolio_value,
            "position": position_info,
            "can_buy": balances["USDT"] > 0,
            "can_sell": trader.open_position is not None,
            "min_position_size": config.min_position_size,
            "max_position_size": config.max_position_size,
        })

    except Exception as exc:
        logger.error("get_manual_status failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc), "available": False}), 500


# ---------------------------------------------------------------------------
# Manual buy / sell
# ---------------------------------------------------------------------------

@trading_bp.route("/api/manual/buy", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def manual_buy():
    trader, lock = _get_trader_and_lock()
    if trader is None:
        return jsonify({"error": "Trader not available"}), 503

    try:
        from config import BotConfig
        config = BotConfig.load()
        exchange = get_app_state().get_exchange()
        params = request.get_json() or {}
        position_size = float(params.get("position_size", config.order_pct))

        if position_size < config.min_position_size:
            return jsonify({"error": f"Position size too small (min: {config.min_position_size * 100}%)"}), 400
        if position_size > config.max_position_size:
            return jsonify({"error": f"Position size too large (max: {config.max_position_size * 100}%)"}), 400

        with lock:
            if trader.usdt_balance <= 0:
                return jsonify({"error": "Insufficient USDT balance"}), 400

            price = _get_current_price(exchange, config.symbol)
            signal = _create_manual_signal("bullish", price, position_size, config)
            trade = trader._buy(price, position_size, signal)

            if not trade:
                return jsonify({"error": "Trade execution failed"}), 400

            # Sync ApplicationState
            _sync_state_after_trade(trader)

        return jsonify({
            "success": True,
            "trade": trade.to_dict(),
            "message": "Buy order executed successfully",
            "balances": trader.get_balances(),
        })

    except Exception as exc:
        logger.error("manual_buy failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@trading_bp.route("/api/manual/sell", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def manual_sell():
    trader, lock = _get_trader_and_lock()
    if trader is None:
        return jsonify({"error": "Trader not available"}), 503

    try:
        from config import BotConfig
        config = BotConfig.load()
        exchange = get_app_state().get_exchange()
        params = request.get_json() or {}
        position_size = float(params.get("position_size", config.order_pct))

        with lock:
            price = _get_current_price(exchange, config.symbol)

            # Close existing long position
            if trader.open_position and trader.open_position.side == "long":
                trade = trader._close_position(price, "manual")
                if not trade:
                    return jsonify({"error": "Trade execution failed"}), 400
                _sync_state_after_trade(trader)
                return jsonify({
                    "success": True,
                    "trade": trade.to_dict(),
                    "message": "Position closed successfully",
                    "balances": trader.get_balances(),
                })

            # No open long — attempt bearish signal
            if position_size < config.min_position_size or position_size > config.max_position_size:
                return jsonify({"error": "Invalid position size"}), 400

            signal = _create_manual_signal("bearish", price, position_size, config)
            trade = trader.handle_signal(signal)
            if not trade:
                return jsonify({"error": "No position to close"}), 400

            _sync_state_after_trade(trader)

        return jsonify({
            "success": True,
            "trade": trade.to_dict(),
            "message": "Sell order executed successfully",
            "balances": trader.get_balances(),
        })

    except Exception as exc:
        logger.error("manual_sell failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


def _sync_state_after_trade(trader) -> None:
    """Update ApplicationState after a manual trade."""
    try:
        app_state = get_app_state()
        pos = trader.open_position
        app_state.update_trading_state(
            usdt_balance=trader.usdt_balance,
            base_balance=trader.base_balance,
            position_open=pos is not None,
            position_entry_price=pos.entry_price if pos else 0.0,
            position_amount=pos.amount if pos else 0.0,
            position_side="long" if pos else "none",
            stop_loss=pos.stop_loss if pos else 0.0,
            take_profit=pos.take_profit if pos else 0.0,
            trailing_stop=pos.trailing_stop if pos else 0.0,
        )
    except Exception as exc:
        logger.warning("State sync after trade failed: %s", exc)


# ---------------------------------------------------------------------------
# Clear trades
# ---------------------------------------------------------------------------

@trading_bp.route("/api/manual/clear-trades", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def clear_all_trades():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503

    try:
        db = get_database()
        stats_before = db.get_trade_stats()
        count_before = stats_before["total_trades"]
        deleted = db.clear_all_trades()
        deleted_pos = db.clear_all_positions()

        if deleted != count_before:
            return jsonify({"error": f"Clear inconsistency: expected {count_before}, deleted {deleted}"}), 500

        from config import BotConfig
        config = BotConfig.load()
        initial = config.initial_usdt

        trader, lock = _get_trader_and_lock()
        if trader and lock:
            with lock:
                trader.usdt_balance = initial
                trader.base_balance = 0.0
                trader.open_position = None
                trader.total_trades = 0
                trader.winning_trades = 0
                trader.total_pnl = 0.0

            get_app_state().update_trading_state(
                usdt_balance=initial,
                base_balance=0.0,
                position_open=False,
                position_entry_price=0.0,
                position_amount=0.0,
                position_side="none",
                stop_loss=0.0,
                take_profit=0.0,
                trailing_stop=0.0,
            )

        return jsonify({
            "success": True,
            "message": f"Cleared {deleted} trades and {deleted_pos} positions. Balance reset to ${initial:.2f}",
            "count": deleted,
            "positions_cleared": deleted_pos,
            "balance_reset": initial,
        })

    except Exception as exc:
        logger.error("clear_all_trades failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Trading mode / emergency stop / enable / disable / sync
# ---------------------------------------------------------------------------

@trading_bp.route("/api/trading/mode")
@require_auth
@limiter.limit("30 per minute")
def get_trading_mode():
    try:
        from config import BotConfig
        config = BotConfig.load()
        trader, _ = _get_trader_and_lock()
        is_live = hasattr(trader, "mode") if trader else False

        resp = {
            "configured_mode": config.trading_mode,
            "live_trading_enabled": config.live_trading_enabled,
            "is_live_trader": is_live,
        }
        if is_live and trader:
            resp.update({
                "actual_mode": trader.mode.value,
                "trading_enabled": getattr(trader, "trading_enabled", True),
                "emergency_stop": getattr(trader, "emergency_stop", False),
                "daily_trades": getattr(trader, "daily_trades", 0),
                "daily_pnl": getattr(trader, "daily_pnl", 0.0),
                "total_pnl": getattr(trader, "total_pnl", 0.0),
            })
        else:
            resp.update({"actual_mode": "paper", "trading_enabled": True, "emergency_stop": False})

        return jsonify(resp)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@trading_bp.route("/api/trading/emergency-stop", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def trigger_emergency_stop():
    trader, lock = _get_trader_and_lock()
    if trader is None:
        return jsonify({"error": "Trader not available"}), 503

    try:
        params = request.get_json() or {}
        close_positions = params.get("close_positions", True)

        with lock:
            trader.trigger_emergency_stop(close_positions=close_positions)

        get_app_state().update_trading_state(
            trading_enabled=False,
            emergency_stop=True,
            position_open=False,
            position_entry_price=0.0,
            position_amount=0.0,
            position_side="none",
            stop_loss=0.0,
            take_profit=0.0,
            trailing_stop=0.0,
        )

        return jsonify({
            "success": True,
            "message": "EMERGENCY STOP TRIGGERED",
            "positions_closed": close_positions,
            "trading_enabled": False,
        })
    except Exception as exc:
        logger.error("emergency_stop failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@trading_bp.route("/api/trading/enable", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def enable_trading():
    trader, lock = _get_trader_and_lock()
    if trader is None:
        return jsonify({"error": "Trader not available"}), 503

    try:
        with lock:
            if hasattr(trader, "emergency_stop") and trader.emergency_stop:
                if hasattr(trader, "reset_emergency_stop"):
                    trader.reset_emergency_stop()
            trader.enable_trading()

        get_app_state().update_trading_state(trading_enabled=True, emergency_stop=False)
        return jsonify({"success": True, "message": "Trading enabled", "trading_enabled": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@trading_bp.route("/api/trading/disable", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def disable_trading():
    trader, lock = _get_trader_and_lock()
    if trader is None:
        return jsonify({"error": "Trader not available"}), 503

    try:
        with lock:
            trader.disable_trading()

        get_app_state().update_trading_state(trading_enabled=False)
        return jsonify({"success": True, "message": "Trading disabled", "trading_enabled": False})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@trading_bp.route("/api/trading/sync", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def sync_exchange():
    trader, lock = _get_trader_and_lock()
    if trader is None:
        return jsonify({"error": "Trader not available"}), 503
    if not hasattr(trader, "sync_balances"):
        return jsonify({"error": "Not available in paper trading mode"}), 400

    try:
        with lock:
            balances = trader.sync_balances()
            position = trader.sync_positions()

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
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
