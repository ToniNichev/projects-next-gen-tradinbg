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
GET /api/paper/performance          Paper test so far: bot vs. holding BTC, hourly
"""

import logging
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

from flask import Blueprint, has_request_context, jsonify, request

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

def _current_bot_signal(app_state):
    """What the enabled strategies say right now (None before the first check)."""
    sm = app_state.get_strategy_manager()
    if sm is None:
        return None
    signals = [
        (strategy, sm.last_signals.get(strategy.name))
        for strategy in sm.strategies
        if strategy.is_enabled() and sm.last_signals.get(strategy.name) is not None
    ]
    if not signals:
        return None
    directions = {sig.direction for _, sig in signals}
    newest = max((sig for _, sig in signals), key=lambda sig: sig.timestamp)
    return {
        "signal_direction": directions.pop() if len(directions) == 1 else "mixed",
        "price": float(newest.price),
        "timestamp": newest.timestamp.isoformat() if newest.timestamp else None,
        "strategies": [getattr(st, "display_name", st.name) for st, _ in signals],
    }


def _trade_scope():
    """Which trades the dashboard shows: True = real money only (the bot is
    trading real money), False = practice only (?practice=1), None = all."""
    if has_request_context() and request.args.get("practice", "").lower() in ("1", "true", "yes"):
        return False
    pots = get_app_state().get_pot_manager()
    return True if pots is not None and getattr(pots, "live", False) else None


def _scope_name(live):
    return {True: "real", False: "practice", None: "all"}[live]


def _latest_trade():
    """Most recent executed trade from the database (None if there are none)."""
    if not DATABASE_AVAILABLE:
        return None
    try:
        trades = get_database().get_trades(limit=1, live=_trade_scope())
    except Exception as exc:
        logger.warning("Could not read latest trade: %s", exc)
        return None
    if not trades:
        return None
    t = trades[0]
    when = t.timestamp
    if when is not None and when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return {
        "side": t.side,
        "timestamp": when.isoformat() if when else None,
        "price": float(t.price),
        "amount": float(t.amount),
        "notional": float(t.notional),
        "pnl": float(t.pnl) if t.pnl is not None else None,
        "exit_reason": t.exit_reason,
        "usdt_balance": float(t.usdt_balance),
        "pot": _pot_name(getattr(t, "pot", None)),
        "strategy_name": getattr(t, "strategy_name", None),
    }


_UNASSIGNED_CACHE = {"at": 0.0, "value": 0.0}


def _cached_unassigned(pots, max_age=60.0):
    """Cash no pot owns. Asking costs an exchange call, so reuse it for a minute."""
    import time
    now = time.monotonic()
    if _UNASSIGNED_CACHE["at"] and now - _UNASSIGNED_CACHE["at"] < max_age:
        return _UNASSIGNED_CACHE["value"]
    try:
        value = float(pots.unassigned_cash() or 0.0)
    except Exception as exc:
        logger.warning("Could not read unassigned cash: %s", exc)
        value = _UNASSIGNED_CACHE["value"]
    _UNASSIGNED_CACHE.update(at=now, value=value)
    return value


def _pots_overview(app_state):
    """All pots together, for the dashboard's top cards (None without pots).

    total: cash + BTC across every pot, plus cash no pot owns yet.
    holding: each pot holding BTC and what would make it sell.
    """
    pots = app_state.get_pot_manager()
    if pots is None:
        return None
    try:
        price = app_state.get_trading_state().current_price
        if not price:
            from config import BotConfig
            price = _get_price(app_state, BotConfig.load().symbol)
        price = float(price)
        summary = pots.summary(price)
        unassigned = _cached_unassigned(pots)
        rows = summary["pots"]
        cash = sum(r["cash"] for r in rows) + unassigned
        btc = sum(r["btc"] for r in rows)
        sm = app_state.get_strategy_manager()
        holding = []
        for r in rows:
            if not r["holding"]:
                continue
            pot = pots.get(r["name"])
            sells_below = None
            if pot is not None and pot.strategy is not None and sm is not None:
                sig = sm.last_signals.get(pot.strategy.name)
                if sig is not None and (sig.indicators or {}).get("sell_below"):
                    sells_below = float(sig.indicators["sell_below"])
            holding.append({
                "name": r["name"], "label": r["label"], "color": r.get("color"),
                "btc": r["btc"], "value": r["btc"] * price,
                "entry_price": r["entry_price"], "stop_loss": r["stop_loss"],
                "take_profit": r["take_profit"], "sells_below_daily_close": sells_below,
            })
        total = summary["total"]
        return {
            "real_money": summary["real_money"],
            "price": price,
            "value": total["value"] + unassigned,
            "invested": total["invested"],
            "pnl": total["pnl"],
            "pnl_pct": total["pnl_pct"],
            "cash": cash,
            "unassigned": unassigned,
            "btc": btc,
            "btc_value": btc * price,
            "holding": holding,
        }
    except Exception as exc:
        logger.warning("Could not build the pots overview: %s", exc)
        return None


@market_bp.route("/state")
@require_auth
def get_state():
    """Return current trading state in the format expected by the UI."""
    app_state = get_app_state()
    ts = app_state.get_trading_state()

    last_signal = _current_bot_signal(app_state)
    last_trade = _latest_trade()

    return jsonify({
        "balances": {
            "USDT": ts.usdt_balance,
            "BASE": ts.base_balance,
        },
        "last_signal": last_signal,
        "last_trade": last_trade,
        # With money pots: every pot together (the balances above are one pot's)
        "pots": _pots_overview(app_state),
        "updated_at": ts.last_update.isoformat(),
        # When the bot last checked, and the hourly close its prices are from
        "check": app_state.get_last_check(),
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

_TIMEFRAME_DELTA = {
    "1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30), "1h": timedelta(hours=1), "4h": timedelta(hours=4),
    "1d": timedelta(days=1), "1w": timedelta(weeks=1),
}


@market_bp.route("/api/candles/<timeframe>")
@limiter.limit("30 per minute")
@require_auth
def get_candles(timeframe):
    """Serve OHLCV candles — local DB first, Binance as fallback."""
    valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
    if timeframe not in valid_timeframes:
        return jsonify({"error": f"Invalid timeframe. Must be one of: {', '.join(valid_timeframes)}"}), 400

    try:
        import ccxt
        from config import BotConfig

        config = BotConfig.load()
        limit = min(int(request.args.get("limit", 300)), 1000)
        since_param = request.args.get("since")

        # Try DB first — fast, no Binance API call on every chart load
        if DATABASE_AVAILABLE:
            try:
                db = get_database()
                since_dt = None
                if since_param:
                    since_dt = datetime.fromtimestamp(int(since_param) / 1000, tz=timezone.utc).replace(tzinfo=None)
                candles = db.get_candles(config.symbol, timeframe, limit=limit, since=since_dt)
                # When loading older history, the DB must reach back to `since`;
                # it only holds what the bot has seen, so older ranges come
                # from the exchange.
                covers_since = since_dt is None or (
                    candles
                    and datetime.fromisoformat(candles[0]["timestamp"]).replace(tzinfo=None)
                    <= since_dt + _TIMEFRAME_DELTA[timeframe]
                )
                if len(candles) >= 50 and covers_since:
                    return jsonify({
                        "timeframe": timeframe,
                        "symbol": config.symbol,
                        "candles": candles,
                        "count": len(candles),
                        "oldest_timestamp": candles[0]["timestamp"] if candles else None,
                        "newest_timestamp": candles[-1]["timestamp"] if candles else None,
                        "source": "db",
                    })
            except Exception as db_exc:
                logger.warning("DB candle fetch failed, falling back to Binance: %s", db_exc)

        # Fallback: fetch live from Binance
        exchange = get_app_state().get_exchange()
        if exchange is None:
            exchange = ccxt.binanceus({
                "apiKey": config.binance_api_key,
                "secret": config.binance_api_secret,
                "enableRateLimit": True,
            })

        kwargs = {"limit": min(limit, 500)}
        if since_param:
            kwargs["since"] = int(since_param)

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
            "source": "binance",
        })

    except Exception as exc:
        logger.error("get_candles failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Trade history
# ---------------------------------------------------------------------------

@market_bp.route("/api/trades")
@limiter.limit("30 per minute")
@require_auth
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

        scope = _trade_scope()
        trades = db.get_trades(limit=limit, live=scope, **filters)

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
                    "pot": _pot_name(t.pot),
                })
            except Exception as exc:
                logger.error("Error serialising trade %s: %s", getattr(t, "id", "?"), exc)

        return jsonify({"trades": trades_data, "count": len(trades_data),
                        "scope": _scope_name(scope)})

    except Exception as exc:
        logger.error("get_trades failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Statistics / positions / performance
# ---------------------------------------------------------------------------

@market_bp.route("/api/stats")
@limiter.limit("30 per minute")
@require_auth
def get_stats():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        return jsonify(get_database().get_trade_stats(live=_trade_scope()))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@market_bp.route("/api/positions")
@limiter.limit("30 per minute")
@require_auth
def get_positions():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        db = get_database()
        positions = db.get_open_positions(live=_trade_scope())
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
@limiter.limit("30 per minute")
@require_auth
def get_performance():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        db = get_database()
        scope = _trade_scope()
        stats = db.get_trade_stats(live=scope)
        recent = db.get_trades(limit=100, live=scope)

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


@market_bp.route("/api/paper/performance")
@limiter.limit("30 per minute")
@require_auth
def get_paper_performance():
    """The paper account vs. just holding BTC, in % since the first paper trade."""
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        from config import BotConfig
        from app.services.paper_performance import compute_paper_performance

        db = get_database()
        # With money pots this panel is about the Trend Hold pot only
        pots = get_app_state().get_pot_manager()
        trend_tag = pots.get("trend").tag if pots is not None else None
        trades = db.get_trades(limit=10000, pot=trend_tag)
        rows = [{
            "timestamp": t.timestamp,
            "side": t.side,
            "price": float(t.price or 0),
            "amount": float(t.amount or 0),
            "notional": float(t.notional or 0),
            "fee": float(t.fee or 0),
            "usdt_balance": float(t.usdt_balance or 0),
            "base_balance": float(t.base_balance or 0),
        } for t in trades]
        if not rows:
            return jsonify({"success": True, "data": {"started": False}})

        first = min(r["timestamp"] for r in rows)
        if first.tzinfo is None:
            first = first.replace(tzinfo=timezone.utc)
        config = BotConfig.load()
        candles = db.get_candles(config.symbol, "1h", limit=24 * 400, since=first - timedelta(hours=3))
        data = compute_paper_performance(rows, candles)
        data["symbol"] = config.symbol
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        logger.error("get_paper_performance failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Money pots
# ---------------------------------------------------------------------------

def _get_price(app_state, symbol):
    """Latest BTC price: from the bot's state, else the exchange."""
    price = app_state.get_trading_state().current_price
    if not price:
        price = float(app_state.get_exchange().fetch_ticker(symbol)["last"])
    return float(price)


def _pot_name(tag):
    """'live-intraday' -> 'intraday'; untagged (pre-pots) trades -> None."""
    if not tag:
        return None
    return tag[len("live-"):] if tag.startswith("live-") else tag


@market_bp.route("/api/pots")
@limiter.limit("30 per minute")
@require_auth
def get_pots():
    """Each money pot's cash, BTC, value and result (pots.py)."""
    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": True, "enabled": False})
    try:
        price = app_state.get_trading_state().current_price
        if not price:
            exchange = app_state.get_exchange()
            from config import BotConfig
            price = float(exchange.fetch_ticker(BotConfig.load().symbol)["last"])
        lock = app_state.get_trader_lock()
        with lock if lock else nullcontext():
            data = pots.summary(float(price))
            data["transfers"] = pots.recent_transfers()
            try:
                data["unassigned"] = pots.unassigned_cash()
            except Exception as exc:
                logger.warning("Could not read unassigned cash: %s", exc)
                data["unassigned"] = None
            data["account"] = pots.account_check()
        return jsonify({"success": True, "enabled": True, **data})
    except Exception as exc:
        logger.error("get_pots failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/transfer", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def transfer_pot_cash():
    """Move uninvested cash: {"from": "trend"|"unassigned", "to": ..., "amount": 5}."""
    from pots import TransferError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    params = request.get_json(silent=True) or {}
    lock = app_state.get_trader_lock()
    try:
        with lock if lock else nullcontext():
            result = pots.transfer(
                str(params.get("from", "")),
                str(params.get("to", "")),
                params.get("amount"),
                str(params.get("note", ""))[:200],
            )
            balances = {p.name: p.balances() for p in pots.pots.values()}
        return jsonify({"success": True, **result, "balances": balances})
    except TransferError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("transfer_pot_cash failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/sell", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def sell_pot_now():
    """Sell all of one pot's BTC now: {"pot": "trend", "pause": true|false}.
    pause=true also stops that pot buying again until it is resumed."""
    from pots import PotActionError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    params = request.get_json(silent=True) or {}
    name = str(params.get("pot", ""))
    pause = bool(params.get("pause", False))
    lock = app_state.get_trader_lock()
    try:
        with lock if lock else nullcontext():
            trade = pots.sell_now(name, pause=pause)
            pot = pots.get(name)
            balances = pot.balances()
            paused = pot.paused
            if pot.trader is app_state.get_trader():  # the main panels show this pot
                pos = pot.trader.open_position  # None unless the sell was partial
                app_state.update_trading_state(
                    usdt_balance=pot.trader.usdt_balance, base_balance=pot.trader.base_balance,
                    position_open=pos is not None,
                    position_entry_price=pos.entry_price if pos else 0.0,
                    position_amount=pos.amount if pos else 0.0,
                    position_side="long" if pos else "none",
                    stop_loss=pos.stop_loss if pos else 0.0,
                    take_profit=pos.take_profit if pos else 0.0,
                    trailing_stop=pos.trailing_stop if pos else 0.0,
                )
        return jsonify({
            "success": True,
            "message": (f"Sold {trade.amount:.6f} BTC at ${trade.price:,.2f} (${trade.notional:,.2f})"
                        + (". The pot is paused" if paused else "")),
            "trade": trade.to_dict(),
            "balances": balances,
            "paused": paused,
        })
    except PotActionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("sell_pot_now failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/pause", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def pause_pot():
    """Pause (no new buys) or resume a pot: {"pot": "trend", "paused": true|false}."""
    from pots import PotActionError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    params = request.get_json(silent=True) or {}
    name = str(params.get("pot", ""))
    paused = bool(params.get("paused", True))
    lock = app_state.get_trader_lock()
    try:
        with lock if lock else nullcontext():
            pots.set_paused(name, paused)
            label = pots.get(name).label
        return jsonify({"success": True, "paused": paused,
                        "message": f"{label} pot {'paused: it will not buy' if paused else 'resumed'}"})
    except PotActionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("pause_pot failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/reset-loss-limit", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def reset_pot_loss_limit():
    """Let a pot stopped by the loss limit buy again: {"pot": "trend"}.
    Its value now becomes its new best value."""
    from pots import PotActionError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    name = str((request.get_json(silent=True) or {}).get("pot", ""))
    lock = app_state.get_trader_lock()
    try:
        from config import BotConfig
        price = _get_price(app_state, BotConfig.load().symbol)
        with lock if lock else nullcontext():
            result = pots.reset_loss_limit(name, price)
            label = pots.get(name).label
        return jsonify({"success": True, **result,
                        "message": f"{label} pot can buy again; the loss limit now counts from ${result['new_peak']:.2f}"})
    except PotActionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("reset_pot_loss_limit failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/clear-mismatch", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def clear_pots_mismatch():
    """The user checked the account after "pots don't match the exchange".
    Only clears when the pots match the exchange now."""
    from pots import PotActionError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    lock = app_state.get_trader_lock()
    try:
        with lock if lock else nullcontext():
            pots.clear_mismatch()
        return jsonify({"success": True, "message": "The pots match the exchange again: trading is back on"})
    except PotActionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("clear_pots_mismatch failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/clear-check", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def clear_pot_check():
    """The user checked a pot whose order went through but wasn't recorded:
    {"pot": "intraday"}. Only clears when the pots match the exchange."""
    from pots import PotActionError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    name = str((request.get_json(silent=True) or {}).get("pot", ""))
    lock = app_state.get_trader_lock()
    try:
        with lock if lock else nullcontext():
            pots.clear_needs_check(name)
            label = pots.get(name).label
        return jsonify({"success": True, "message": f"{label} pot is trading again"})
    except PotActionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("clear_pot_check failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/add", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def add_pot():
    """Add a pot that starts with $0:
    {"name": "macd", "strategy": "macd_volume", "max_buys_per_day": 3, "order_pct": 0.95, "label": ""}"""
    from pots import PotActionError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    params = request.get_json(silent=True) or {}
    lock = app_state.get_trader_lock()
    try:
        with lock if lock else nullcontext():
            pot = pots.add_pot(
                params.get("name", ""), params.get("strategy", ""),
                params.get("max_buys_per_day", 3), params.get("order_pct", 0.95),
                label=str(params.get("label", ""))[:40],
            )
            if hasattr(pot.trader, "sync_balances"):
                try:
                    pot.trader.sync_balances()
                except Exception as exc:
                    logger.warning("New pot %s: balance sync failed: %s", pot.name, exc)
        return jsonify({"success": True, "pot": pot.name,
                        "message": f"Added the {pot.label} pot with $0. Use Move money to fund it"})
    except PotActionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("add_pot failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/remove", methods=["POST"])
@limiter.limit("10 per minute")
@require_auth
def remove_pot():
    """Remove a pot added from the dashboard, only when it holds nothing: {"pot": "macd"}."""
    from config import BotConfig
    from pots import PotActionError

    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": False, "error": "Money pots are off"}), 400
    name = str((request.get_json(silent=True) or {}).get("pot", ""))
    lock = app_state.get_trader_lock()
    try:
        price = _get_price(app_state, BotConfig.load().symbol)
        with lock if lock else nullcontext():
            label = pots.get(name).label if pots.get(name) else name
            pots.remove_pot(name, price)
        return jsonify({"success": True, "message": f"Removed the {label} pot"})
    except PotActionError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.error("remove_pot failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


@market_bp.route("/api/pots/performance")
@limiter.limit("30 per minute")
@require_auth
def get_pots_performance():
    """Each pot's result over time vs. holding BTC (one point per hour)."""
    app_state = get_app_state()
    pots = app_state.get_pot_manager()
    if pots is None:
        return jsonify({"success": True, "enabled": False})
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        from config import BotConfig
        from app.services.pot_performance import compute_pot_performance

        db = get_database()
        specs = []
        for pot in pots.pots.values():
            tag = pot.tag
            trades = db.get_trades(limit=100000, pot=tag)
            moves = db.get_pot_transfers(limit=100000, pot=tag)
            specs.append({
                "name": pot.name,
                "label": pot.label,
                "start_time": pot.start_time or datetime.now(timezone.utc),
                "start_cash": pot.start_value,
                "trades": [{"timestamp": t.timestamp, "usdt_balance": float(t.usdt_balance or 0),
                            "base_balance": float(t.base_balance or 0)} for t in trades],
                "moves": [{"timestamp": m.timestamp,
                           "amount": float(m.amount) if m.to_pot == tag else -float(m.amount)}
                          for m in moves],
            })
        first = min(
            (s["start_time"] if s["start_time"].tzinfo else s["start_time"].replace(tzinfo=timezone.utc))
            for s in specs
        )
        config = BotConfig.load()
        candles = db.get_candles(config.symbol, "1h", limit=24 * 400, since=first - timedelta(hours=3))
        data = compute_pot_performance(specs, candles)
        return jsonify({"success": True, "enabled": True, **data})
    except Exception as exc:
        logger.error("get_pots_performance failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500
