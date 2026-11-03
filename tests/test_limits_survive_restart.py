"""Limits that used to live only in memory survive a restart (audit, 2026-11-02)."""

from unittest.mock import MagicMock

from database import initialize_database
from pots import POT_INTRADAY, POT_TREND
from tests.test_pots import PRICE, build, candle, live_pots


def test_emergency_stop_stays_on_after_a_restart():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, _, sm, exchange = live_pots(db)
    for t in pots.traders():
        t.trigger_emergency_stop(close_positions=False)
    again, trend2, _, sm2 = build(db, mode="live", exchange=exchange)
    t = again.get(POT_TREND).trader
    assert t.emergency_stop and not t.trading_enabled
    trend2.direction = "bullish"
    candle(again, sm2)
    assert not again.get(POT_TREND).holding           # still stopped

    for t in again.traders():
        t.reset_emergency_stop()
        t.enable_trading()
    third, *_ = build(db, mode="live", exchange=exchange)
    t = third.get(POT_TREND).trader
    assert not t.emergency_stop and t.trading_enabled


def test_disabled_trading_stays_off_after_a_restart():
    db = initialize_database("sqlite:///:memory:")
    pots, *_rest, exchange = live_pots(db)
    for t in pots.traders():
        t.disable_trading()
    again, *_ = build(db, mode="live", exchange=exchange)
    assert not again.get(POT_INTRADAY).trader.trading_enabled


def test_todays_trades_are_counted_again_after_a_restart():
    db = initialize_database("sqlite:///:memory:")
    pots, _, intraday, sm, exchange = live_pots(db)
    intraday.direction = "bullish"
    candle(pots, sm)
    intraday.direction = "bearish"
    candle(pots, sm)
    before = pots.get(POT_INTRADAY).trader
    again, *_ = build(db, mode="live", exchange=exchange)
    after = again.get(POT_INTRADAY).trader
    assert after.daily_trades == 2
    assert abs(after.daily_pnl - before.daily_pnl) < 1e-9 and after.daily_pnl < 0  # fees


def test_every_live_pot_gets_a_starting_best_value():
    db = initialize_database("sqlite:///:memory:")
    pots, *_rest, sm, exchange = live_pots(db)
    assert pots._read_peak(pots.get(POT_TREND)) is None
    candle(pots, sm)
    assert pots._read_peak(pots.get(POT_TREND)) == 75.0     # the money put in
    ll = pots.loss_limit(pots.get(POT_TREND), PRICE)
    assert ll["peak"] == 75.0 and ll["drop_pct"] is not None


def test_loss_limit_that_cant_be_read_blocks_the_buy():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, _, sm, exchange = live_pots(db)
    t = pots.get(POT_TREND).trader
    t.db_manager = MagicMock(wraps=db)
    t.db_manager.get_strategy_config = MagicMock(side_effect=RuntimeError("database is locked"))
    ok, why = t._check_portfolio_peak_drawdown("buy", PRICE)
    assert not ok and "loss limit" in why
