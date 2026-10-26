"""The live module running Trend Hold: exchange stops, sizing, dry run,
and keeping paper and live positions apart."""

from datetime import datetime, timezone

import pytest

from database import initialize_database
from live_trader import LivePosition, LiveTrader, TradingMode
from strategies.base_strategy import StrategySignal
from tests.test_live_trader_batch_c import _PollableExchange, _make_config

PRICE = 50_000.0


def trend_signal(direction="bullish", emergency_stop_pct=0.0):
    """A signal shaped like TrendHoldStrategy's: all in, no real stop."""
    stop = PRICE * (1 - emergency_stop_pct) if emergency_stop_pct else PRICE * 1e-6
    return StrategySignal(
        direction=direction,
        price=PRICE,
        confidence=1.0,
        timestamp=datetime.now(timezone.utc),
        strategy_name="Trend_Hold",
        stop_loss=stop,
        take_profit=PRICE * 100,
        position_size=0.99,
    )


def trend_config():
    config = _make_config()
    config.use_trailing_stop = False
    config.max_position_size = 0.99
    config.exchange_stop_loss_enabled = True
    return config


def live_trader(config=None, db=None):
    exchange = _PollableExchange(ticker_ask=PRICE, ticker_bid=PRICE, ticker_last=PRICE)

    def fill(symbol, amount, params=None):
        order = {
            "id": "BUY-1", "status": "closed", "amount": amount, "filled": amount,
            "average": PRICE, "fee": {"cost": amount * PRICE * 0.001, "currency": "USDT"},
        }
        exchange.fetch_order.return_value = order
        exchange._balance = {
            "USDT": {"free": 1_000.0 - amount * PRICE, "total": 1_000.0 - amount * PRICE},
            "BTC": {"free": amount, "total": amount},
        }
        return order

    exchange.create_market_buy_order.side_effect = fill
    trader = LiveTrader(exchange, config or trend_config(), mode=TradingMode.LIVE, db_manager=db)
    trader.usdt_balance = 1_000.0
    return trader, exchange


# --------------------------------------------------------------- exchange stop

def test_no_exchange_stop_when_strategy_has_no_stop(no_real_notifications):
    trader, exchange = live_trader()
    trade = trader.handle_signal(trend_signal())
    assert trade is not None and trader.open_position is not None
    exchange.create_order.assert_not_called()  # no STOP_LOSS_LIMIT at ~$0.05
    assert not [n for n in no_real_notifications if "protective stop" in n[0].lower()]


def test_emergency_stop_is_placed_on_exchange():
    trader, exchange = live_trader()
    trader.handle_signal(trend_signal(emergency_stop_pct=0.2))
    exchange.create_order.assert_called_once()
    assert exchange.create_order.call_args.args[5]["stopPrice"] == pytest.approx(PRICE * 0.8)


def test_trailing_level_ignored_when_trailing_is_off():
    pos = LivePosition(
        side="long", entry_price=PRICE, amount=0.01, entry_time="", stop_loss=PRICE * 0.5,
        take_profit=PRICE * 2, trailing_stop=PRICE * 0.975, initial_trailing_stop_pct=0.025,
    )
    off, _ = live_trader()
    assert off._effective_protective_trigger(pos) == PRICE * 0.5

    config = trend_config()
    config.use_trailing_stop = True
    on, _ = live_trader(config)
    assert on._effective_protective_trigger(pos) == PRICE * 0.975


# --------------------------------------------------------------------- sizing

def test_buys_almost_all_of_the_balance():
    trader, exchange = live_trader()
    trader.handle_signal(trend_signal())
    amount = exchange.create_market_buy_order.call_args.kwargs["amount"]
    assert amount * PRICE == pytest.approx(1_000.0 * 0.99, rel=1e-3)  # not capped at 15%


# -------------------------------------------------------------------- dry run

def test_dry_run_tracks_a_simulated_position_and_touches_nothing_real():
    db = initialize_database("sqlite:///:memory:")
    exchange = _PollableExchange(ticker_ask=PRICE, ticker_bid=PRICE, ticker_last=PRICE)
    exchange.fetch_balance = lambda: pytest.fail("dry run must not read the real balance")
    config = trend_config()
    config.initial_usdt = 100.0

    trader = LiveTrader(exchange, config, mode=TradingMode.DRY_RUN, db_manager=db)
    trader.sync_balances()
    trader.sync_positions()
    assert trader.get_balances() == {"USDT": 100.0, "BASE": 0.0}

    buy = trader.handle_signal(trend_signal("bullish"))
    assert buy.side == "buy"
    assert trader.open_position is not None
    assert trader.usdt_balance < 2  # ~99% went into BTC

    assert trader.handle_signal(trend_signal("bullish")) is None  # already holding

    sell = trader.handle_signal(trend_signal("bearish"))
    assert sell.side == "sell" and sell.exit_reason == "signal"
    assert trader.open_position is None
    assert trader.usdt_balance == pytest.approx(100.0, rel=0.005)  # minus fees/slippage

    exchange.create_market_buy_order.assert_not_called()
    exchange.create_market_sell_order.assert_not_called()
    exchange.create_order.assert_not_called()
    assert db.get_open_positions() == []
    assert db.get_trades(limit=10) == []


# ------------------------------------------------- paper vs live positions

def _add_position(db, strategy_name):
    db.add_position({
        "side": "long", "entry_price": PRICE, "entry_time": datetime.now(timezone.utc),
        "amount": 0.002, "stop_loss": 1.0, "take_profit": PRICE * 100,
        "is_open": True, "strategy_name": strategy_name,
    })


def test_live_trader_ignores_the_paper_position():
    db = initialize_database("sqlite:///:memory:")
    _add_position(db, "Aggregated")  # the paper bot's position
    trader, _ = live_trader(db=db)
    trader.sync_positions()
    assert trader.open_position is None
    assert len(db.get_open_positions(live=False)) == 1  # left untouched


def test_paper_and_live_filters():
    db = initialize_database("sqlite:///:memory:")
    _add_position(db, "Aggregated")
    _add_position(db, "live_trader")
    assert [p.strategy_name for p in db.get_open_positions(live=True)] == ["live_trader"]
    assert [p.strategy_name for p in db.get_open_positions(live=False)] == ["Aggregated"]
    assert len(db.get_open_positions()) == 2
