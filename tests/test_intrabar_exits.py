"""Tests for PaperTrader.update_position_intrabar (backtest exit model)."""

import pytest

from paper_trader import PaperTrader, Position

SLIP = 0.0005


def _trader(trailing=True):
    t = PaperTrader(
        log_path="", enable_database=False, enable_csv_logging=False,
        slippage=SLIP, use_trailing_stop=trailing, trailing_stop_pct=0.025,
    )
    t.usdt_balance, t.base_balance = 0.0, 1.0
    t.open_position = Position(
        side="long", entry_price=100.0, amount=1.0, entry_time="2026-10-20T15:00:00",
        stop_loss=95.0, take_profit=110.0, trailing_stop=97.5,
        initial_trailing_stop_pct=0.025, highest_price=100.0,
    )
    return t


def _fill(price):
    return pytest.approx(price * (1 - SLIP))


def test_no_exit_when_candle_stays_inside_range():
    t = _trader()
    assert t.update_position_intrabar(100, 101, 99, 100.5) is None
    assert t.open_position is not None


def test_stop_triggers_on_low_even_if_close_recovers():
    t = _trader(trailing=False)
    trade = t.update_position_intrabar(100, 100.5, 94.0, 99.0)
    assert trade.exit_reason == "stop_loss"
    assert trade.price == _fill(95.0)


def test_gap_down_fills_at_open():
    t = _trader(trailing=False)
    trade = t.update_position_intrabar(93.0, 93.5, 92.0, 93.0)
    assert trade.price == _fill(93.0)


def test_take_profit_triggers_on_high():
    t = _trader()
    trade = t.update_position_intrabar(105, 111, 104, 106)
    assert trade.exit_reason == "take_profit"
    assert trade.price == _fill(110.0)


def test_candle_touching_both_assumes_stop_first():
    t = _trader()
    trade = t.update_position_intrabar(100, 111, 94, 100)
    assert trade.exit_reason == "trailing_stop"  # 97.5 trailing is above 95 stop
    assert trade.price == _fill(97.5)


def test_trailing_raised_by_high_then_hit_by_close():
    t = _trader()
    # High 108 raises trailing to 105.3; close 105 is below it
    trade = t.update_position_intrabar(101, 108, 100.5, 105)
    assert trade.exit_reason == "trailing_stop"
    assert trade.price == _fill(108 * 0.975)


def test_trailing_raised_and_kept_when_close_holds():
    t = _trader()
    assert t.update_position_intrabar(101, 108, 100.5, 107) is None
    assert t.open_position.highest_price == 108
    assert t.open_position.trailing_stop == pytest.approx(108 * 0.975)
