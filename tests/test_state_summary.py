"""/state feeds the dashboard's top cards: current bot signal and latest trade."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.api import market
from database import initialize_database


def _strategy(name, enabled=True):
    return SimpleNamespace(name=name, is_enabled=lambda: enabled)


def _signal(direction, price, minutes_ago=0):
    return SimpleNamespace(
        direction=direction,
        price=price,
        timestamp=datetime(2026, 10, 26, 20, tzinfo=timezone.utc) - timedelta(minutes=minutes_ago),
    )


def _app_state(strategies, last_signals):
    sm = SimpleNamespace(strategies=strategies, last_signals=last_signals)
    return SimpleNamespace(get_strategy_manager=lambda: sm)


def test_signal_from_the_enabled_strategy():
    state = _app_state(
        [_strategy("EMA_Crossover", enabled=False), _strategy("Trend_Hold")],
        {"EMA_Crossover": _signal("bearish", 1), "Trend_Hold": _signal("bullish", 80_000)},
    )
    sig = market._current_bot_signal(state)
    assert sig["signal_direction"] == "bullish"
    assert sig["price"] == 80_000
    assert sig["strategies"] == ["Trend_Hold"]


def test_signal_mixed_when_enabled_strategies_disagree():
    state = _app_state(
        [_strategy("A"), _strategy("B")],
        {"A": _signal("bullish", 1, minutes_ago=60), "B": _signal("bearish", 2)},
    )
    sig = market._current_bot_signal(state)
    assert sig["signal_direction"] == "mixed"
    assert sig["price"] == 2  # from the newest signal


def test_no_signal_before_first_check():
    assert market._current_bot_signal(_app_state([_strategy("A")], {})) is None
    assert market._current_bot_signal(SimpleNamespace(get_strategy_manager=lambda: None)) is None


def test_latest_trade_from_database(monkeypatch):
    db = initialize_database("sqlite:///:memory:")
    monkeypatch.setattr(market, "get_database", lambda: db)
    assert market._latest_trade() is None

    base = {"fee": 0.1, "slippage": 0.0, "usdt_balance": 1.0, "base_balance": 0.001}
    db.add_trade({**base, "timestamp": datetime(2026, 10, 22, 18), "side": "sell",
                  "price": 81_090.0, "amount": 0.0001, "notional": 9.7, "pnl": -0.27,
                  "exit_reason": "trailing_stop"})
    db.add_trade({**base, "timestamp": datetime(2026, 10, 22, 19), "side": "buy",
                  "price": 81_330.0, "amount": 0.0012, "notional": 98.7})

    t = market._latest_trade()
    assert t["side"] == "buy"
    assert t["price"] == 81_330.0
    assert t["pnl"] is None
    assert t["timestamp"].endswith("+00:00")  # stored naive UTC, sent with zone
