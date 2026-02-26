"""
Legacy state-management shim.

During the migration to the new Blueprint-based architecture (``app/``),
``main.py`` still imports three helpers from this module:

    from dashboard import set_trader, update_state, _record_history

These functions update the in-process state dictionaries that the old UI
templates consumed.  The *new* ``/state`` and ``/history`` routes (served by
``app.api.market``) read from ``ApplicationState`` instead, so this module
is gradually becoming dead code.

TODO: once ``main.py`` is updated to call ``app_state.*`` methods directly,
this file can be deleted.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory state (mirrors ApplicationState; kept for backward compatibility)
# ---------------------------------------------------------------------------

_state = {
    "balances": {"USDT": 0.0, "BASE": 0.0},
    "last_signal": None,
    "last_trade": None,
    "updated_at": None,
}

_history: list = []
_max_history = 250

# Trader references
_trader_instance = None
_trader_lock = None
_exchange_instance = None
_strategy_manager = None


# ---------------------------------------------------------------------------
# Public helpers (called from main.py)
# ---------------------------------------------------------------------------

def set_trader(trader, lock, exchange=None, strategy_manager=None) -> None:
    """Register the active trader with the legacy state globals."""
    global _trader_instance, _trader_lock, _exchange_instance, _strategy_manager

    _trader_instance = trader
    _trader_lock = lock
    _exchange_instance = exchange
    _strategy_manager = strategy_manager

    _state["balances"] = trader.get_balances()
    _state["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info("Legacy trader registered (dashboard shim)")


def _record_history(
    timestamp,
    price: float,
    signal_direction: Optional[str],
    trade_side: Optional[str],
    ohlc: Optional[dict] = None,
) -> None:
    """Append one candle/event to the in-memory history ring-buffer."""
    candle = {"open": price, "high": price, "low": price, "close": price}
    if ohlc:
        candle.update(ohlc)

    _history.append({
        "timestamp": timestamp,
        "price": candle["close"],
        "signal_direction": signal_direction,
        "trade_side": trade_side,
        "open": candle["open"],
        "high": candle["high"],
        "low": candle["low"],
        "close": candle["close"],
    })

    if len(_history) > _max_history:
        _history.pop(0)


def update_state(
    balances=None,
    last_signal=None,
    last_trade=None,
    price: Optional[float] = None,
    signal_direction: Optional[str] = None,
    timestamp=None,
    trade_side: Optional[str] = None,
    ohlc: Optional[dict] = None,
    updated_at=None,
) -> None:
    """Update the legacy in-memory state dict and append a history record."""
    if balances is not None:
        _state["balances"] = balances
    if last_signal is not None:
        _state["last_signal"] = last_signal
    if last_trade is not None:
        _state["last_trade"] = last_trade

    _state["updated_at"] = updated_at or datetime.now(timezone.utc).isoformat()

    if price is not None and signal_direction is not None:
        _record_history(
            timestamp or datetime.now(timezone.utc).isoformat(),
            price,
            signal_direction,
            trade_side,
            ohlc=ohlc,
        )


def get_current_price() -> float:
    """Return a best-effort current price from exchange, history, or state."""
    try:
        if _exchange_instance:
            from config import BotConfig
            config = BotConfig.load()
            ticker = _exchange_instance.fetch_ticker(config.symbol)
            return float(ticker["last"])
    except Exception as exc:
        logger.warning("Could not fetch live price from exchange: %s", exc)

    if _history:
        return float(_history[-1]["close"])

    if _state.get("last_signal"):
        return float(_state["last_signal"].get("price", 0.0))

    raise ValueError("No price data available")
