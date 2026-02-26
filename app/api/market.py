"""
Market-data API endpoints.

Routes
------
GET /state                          Current bot state (balances, last signal/trade)
GET /history                        Price/signal history for charting
GET /api/candles/<timeframe>        OHLCV candles from Binance
GET /api/trades                     Filtered trade history from DB
GET /api/stats                      Aggregate trade statistics
GET /api/positions                  Open positions from DB
GET /api/performance                Detailed performance metrics
"""

import logging
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from app.extensions import limiter, require_auth
from app.core.state import get_app_state

try:
    from database import get_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__)


# ---------------------------------------------------------------------------
# State / history (consumed directly by the existing UI templates)
# ---------------------------------------------------------------------------

@market_bp.route("/state")
@require_auth
def get_state():
    """Return current trading state in the format expected by the UI."""
    app_state = get_app_state()
    ts = app_state.get_trading_state()
    history = app_state.get_history(limit=1)

    last_signal = history[0].get("last_signal") if history else None
    last_trade = history[0].get("last_trade") if history else None

    return jsonify({
        "balances": {
            "USDT": ts.usdt_balance,
            "BASE": ts.base_balance,
        },
        "last_signal": last_signal,
        "last_trade": last_trade,
        "updated_at": ts.last_update.isoformat(),
        "current_price": ts.current_price,
        "position": {
            "open": ts.position_open,
            "side": ts.position_side,
            "entry_price": ts.position_entry_price,
            "amount": ts.position_amount,
            "stop_loss": ts.stop_loss,
            "take_profit": ts.take_profit,
            "trailing_stop": ts.trailing_stop,
        } if ts.position_open else None,
    })


@market_bp.route("/history")
@require_auth
def get_history():
    """Return price/signal history for the chart."""
    app_state = get_app_state()
    records = app_state.get_history(limit=250)
    last = records[0] if records else {}
    return jsonify({
        "history": list(reversed(records)),
        "last_signal": last.get("last_signal"),
        "last_trade": last.get("last_trade"),
    })


# ---------------------------------------------------------------------------
# Candle data
# ---------------------------------------------------------------------------

@market_bp.route("/api/candles/<timeframe>")
@require_auth
@limiter.limit("30 per minute")
def get_candles(timeframe):
    """Fetch OHLCV candles from Binance for the given timeframe."""
    valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
    if timeframe not in valid_timeframes:
        return jsonify({"error": f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes)}"}), 400

    try:
        import ccxt
        from config import BotConfig

        config = BotConfig.load()
        limit = min(int(request.args.get("limit", 100)), 500)
        since = request.args.get("since")

        exchange = get_app_state().get_exchange()
        if exchange is None:
            exchange = ccxt.binanceus({
                "apiKey": config.binance_api_key,
                "secret": config.binance_api_secret,
                "enableRateLimit": True,
            })

        kwargs = {"limit": limit}
        if since:
            kwargs["since"] = int(since)

        ohlcv = exchange.fetch_ohlcv(config.symbol, timeframe, **kwargs)

        candles = [
            {
                "timestamp": datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc).isoformat(),
                "open": c[1], "high": c[2], "low": c[3], "close": c[4], "volume": c[5],
            }
            for c in ohlcv
        ]

        return jsonify({
            "timeframe": timeframe,
            "symbol": config.symbol,
            "candles": candles,
            "count": len(candles),
            "oldest_timestamp": candles[0]["timestamp"] if candles else None,
            "newest_timestamp": candles[-1]["timestamp"] if candles else None,
        })

    except Exception as exc:
        logger.error("get_candles failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Trade history
# ---------------------------------------------------------------------------

@market_bp.route("/api/trades")
@require_auth
@limiter.limit("30 per minute")
def get_trades():
    """Return filtered trade history from the database."""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503

    try:
        db = get_database()
        limit = int(request.args.get("limit", 100))
        filters = {}
        if request.args.get("side"):
            filters["side"] = request.args["side"]
        if request.args.get("exit_reason"):
            filters["exit_reason"] = request.args["exit_reason"]
        if request.args.get("days_back"):
            filters["start_date"] = datetime.now(timezone.utc) - timedelta(days=int(request.args["days_back"]))

        trades = db.get_trades(limit=limit, **filters)

        trades_data = []
        for t in trades:
            try:
                ts = t.timestamp
                if ts and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                trades_data.append({
                    "id": t.id,
                    "timestamp": ts.isoformat() if ts else None,
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
                    "strategy_name": t.strategy_name,
                })
            except Exception as exc:
                logger.error("Error serialising trade %s: %s", getattr(t, "id", "?"), exc)

        return jsonify({"trades": trades_data, "count": len(trades_data)})

    except Exception as exc:
        logger.error("get_trades failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Statistics / positions / performance
# ---------------------------------------------------------------------------

@market_bp.route("/api/stats")
@require_auth
@limiter.limit("30 per minute")
def get_stats():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        return jsonify(get_database().get_trade_stats())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@market_bp.route("/api/positions")
@require_auth
@limiter.limit("30 per minute")
def get_positions():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        db = get_database()
        positions = db.get_open_positions()
        data = [
            {
                "id": p.id,
                "side": p.side,
                "entry_price": float(p.entry_price),
                "entry_time": p.entry_time.isoformat(),
                "amount": float(p.amount),
                "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                "take_profit": float(p.take_profit) if p.take_profit else None,
                "trailing_stop": float(p.trailing_stop) if p.trailing_stop else None,
            }
            for p in positions
        ]
        return jsonify({"positions": data, "count": len(data)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@market_bp.route("/api/performance")
@require_auth
@limiter.limit("30 per minute")
def get_performance():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        db = get_database()
        stats = db.get_trade_stats()
        recent = db.get_trades(limit=100)

        if recent:
            wins = [t for t in recent if t.pnl and t.pnl > 0]
            losses = [t for t in recent if t.pnl and t.pnl < 0]
            total_wins = sum(t.pnl for t in wins)
            total_losses = abs(sum(t.pnl for t in losses))
            stats.update({
                "avg_win": float(total_wins / len(wins)) if wins else 0.0,
                "avg_loss": float(sum(t.pnl for t in losses) / len(losses)) if losses else 0.0,
                "profit_factor": float(total_wins / total_losses) if total_losses > 0 else 0.0,
                "recent_trades_count": len(recent),
            })

        return jsonify(stats)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
