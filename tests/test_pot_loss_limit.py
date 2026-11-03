"""The loss limit on the dashboard: why a pot stopped buying, and a reset.

A live pot stops buying once its value falls BOT_MAX_PORTFOLIO_DRAWDOWN
below its best value. That happened silently: nothing on the dashboard
said so. Moving cash out of a pot also lowered its value, which the limit
would have counted as a loss.
"""

import pytest

from database import initialize_database
from live_trader import _PEAK_PORTFOLIO_EQUITY_KEY
from pots import POT_INTRADAY, POT_MANUAL, POT_TREND, PotActionError, UNASSIGNED
from tests.test_pots import PRICE, live_pots, make_config


def _setup():
    db = initialize_database("sqlite:///:memory:")
    config = make_config(portfolio_drawdown_kill_enabled=True, max_portfolio_drawdown=0.30)
    pots, trend, intraday, sm, exchange = live_pots(db, config=config)
    return db, pots


def _peak(db, pots, name):
    row = db.get_strategy_config(f"{_PEAK_PORTFOLIO_EQUITY_KEY}_{pots.get(name).tag}")
    return float(row.value) if row else None


def test_a_stopped_pot_says_so_and_can_be_reset():
    db, pots = _setup()
    pot = pots.get(POT_TREND)
    pots._write_peak(pot, 150.0)          # its best value was $150, it's worth $75 now
    pot.trader.portfolio_buy_halt = True  # what validate_trade sets when the limit trips

    status = {r["name"]: r for r in pots.summary(PRICE)["pots"]}[POT_TREND]["loss_limit"]
    assert status["enabled"] and status["halted"]
    assert status["peak"] == 150.0 and status["drop_pct"] == pytest.approx(50.0)
    assert status["limit_pct"] == pytest.approx(30.0)

    result = pots.reset_loss_limit(POT_TREND, PRICE)
    assert result["old_peak"] == 150.0 and result["new_peak"] == pytest.approx(75.0)
    assert pot.trader.portfolio_buy_halt is False
    assert _peak(db, pots, POT_TREND) == pytest.approx(75.0)  # counts from today's value
    ok, why = pot.trader.validate_trade("buy", 0.0005, PRICE)
    assert "drawdown" not in why.lower()


def test_reset_is_refused_when_nothing_is_stopped():
    db, pots = _setup()
    with pytest.raises(PotActionError):
        pots.reset_loss_limit(POT_INTRADAY, PRICE)
    with pytest.raises(PotActionError):
        pots.reset_loss_limit(POT_MANUAL, PRICE)


def test_moving_cash_moves_the_best_value_too():
    db, pots = _setup()
    pots._write_peak(pots.get(POT_INTRADAY), 15.0)
    pots.transfer(POT_INTRADAY, UNASSIGNED, 10)   # not a loss
    assert _peak(db, pots, POT_INTRADAY) == pytest.approx(5.0)
    status = pots.loss_limit(pots.get(POT_INTRADAY), PRICE)
    assert status["drop_pct"] == pytest.approx(0.0) and not status["halted"]
    pots.transfer(UNASSIGNED, POT_INTRADAY, 4)
    assert _peak(db, pots, POT_INTRADAY) == pytest.approx(9.0)
    # A pot with no best value yet is left alone (it's taken at its next buy)
    pots.transfer(POT_MANUAL, POT_TREND, 1)
    assert _peak(db, pots, POT_MANUAL) is None
