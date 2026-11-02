"""Sell one pot now from the dashboard, and optionally pause it.

Trend Hold never sells to take a profit, so cashing out is the user's call.
Before this, the only way was the emergency stop (sells every pot).
"""

import threading
from unittest.mock import patch

import pytest

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from database import initialize_database
from pots import POT_INTRADAY, POT_MANUAL, POT_TREND, PotActionError
from tests.test_pots import PRICE, build, candle, live_pots, make_config


def holding_live_pots(db=None, config=None):
    pots, trend, intraday, sm, exchange = live_pots(db, config=config)
    trend.direction = intraday.direction = "bullish"
    candle(pots, sm)
    assert pots.get(POT_TREND).holding and pots.get(POT_INTRADAY).holding
    return pots, trend, intraday, sm, exchange


def test_sell_now_sells_only_that_pot():
    pots, trend, intraday, sm, exchange = holding_live_pots()
    btc_intraday = pots.get(POT_INTRADAY).balances()["BASE"]

    trade = pots.sell_now(POT_TREND)
    assert trade.side == "sell" and trade.exit_reason == "manual"
    assert not pots.get(POT_TREND).holding
    assert pots.get(POT_TREND).balances()["BASE"] < 1e-05  # only a sliver below the 0.00001 step
    assert pots.get(POT_INTRADAY).balances()["BASE"] == pytest.approx(btc_intraday)  # untouched
    assert pots.reconcile() == []

    # Not paused: the trend is still up, so it buys back at the next check
    candle(pots, sm)
    assert pots.get(POT_TREND).holding


def test_sell_and_pause_stays_in_cash_until_resumed():
    pots, trend, intraday, sm, exchange = holding_live_pots()
    pots.sell_now(POT_TREND, pause=True)
    results = candle(pots, sm)  # still bullish
    assert not pots.get(POT_TREND).holding
    assert "paused" in results[POT_TREND]["note"]

    pots.set_paused(POT_TREND, False)
    candle(pots, sm)
    assert pots.get(POT_TREND).holding


def test_pause_survives_a_restart():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm, exchange = live_pots(db)
    pots.set_paused(POT_INTRADAY, True)
    again, *_ = build(db, mode="live", exchange=exchange)
    assert again.get(POT_INTRADAY).paused and not again.get(POT_TREND).paused
    assert again.summary(PRICE)["pots"][1]["paused"] is True


def test_nothing_to_sell_and_manual_cannot_pause():
    pots, *_ = live_pots()
    with pytest.raises(PotActionError, match="no BTC"):
        pots.sell_now(POT_TREND)
    with pytest.raises(PotActionError, match="Unknown"):
        pots.sell_now("nope")
    with pytest.raises(PotActionError, match="Manual"):
        pots.set_paused(POT_MANUAL, True)


def test_paused_pot_still_sells_on_its_own_rule():
    pots, trend, intraday, sm, exchange = holding_live_pots()
    pots.set_paused(POT_TREND, True)
    trend.direction = "bearish"
    candle(pots, sm)
    assert not pots.get(POT_TREND).holding


def test_sell_now_api():
    from app import create_app, init_services
    from auth import get_auth_config

    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False,
                         use_atr_stops=False)
    pots, trend, intraday, sm, exchange = holding_live_pots(db, config=config)
    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots)
    client = app.test_client()
    try:
        with patch("config.BotConfig.load", return_value=config):
            r = client.post("/api/pots/sell", json={"pot": "trend", "pause": True})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()
            assert body["success"] and body["paused"] and "Sold" in body["message"]
            assert state.get_trading_state().position_open is False  # main panel updated

            r = client.post("/api/pots/sell", json={"pot": "trend"})
            assert r.status_code == 400 and "no BTC" in r.get_json()["error"]

            pots_data = client.get("/api/pots").get_json()["pots"]
            assert [p["paused"] for p in pots_data] == [True, False, False]

            r = client.post("/api/pots/pause", json={"pot": "trend", "paused": False})
            assert r.status_code == 200 and not pots.get(POT_TREND).paused
            assert pots.get(POT_INTRADAY).holding  # never touched
    finally:
        state.set_pot_manager(None)
