"""Add pots (from .env or the dashboard) without touching the built-in three."""

import threading
from unittest.mock import patch

import pytest

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from database import initialize_database
from pots import (BUILTIN_POTS, POT_INTRADAY, POT_TREND, UNASSIGNED, PotActionError,
                  parse_extra_pots)
from tests.test_pots import PRICE, build, candle, live_pots, make_config


def test_builtin_pots_unchanged_and_first():
    db = initialize_database("sqlite:///:memory:")
    pots, *_ = live_pots(db, config=make_config(pots_extra="extra:rsi_bb"))
    assert list(pots.pots)[:3] == list(BUILTIN_POTS)
    assert [p.tag for p in pots.pots.values()][:3] == ["live-trend", "live-intraday", "live-manual"]
    assert [pots.get(n).budget for n in BUILTIN_POTS] == [75.0, 15.0, 6.0]
    assert pots.get(POT_TREND).trader.initial_usdt == 75.0  # loss limit as before
    rows = pots.summary(PRICE)["pots"]
    assert [(r["letter"], r["color"]) for r in rows[:3]] == [
        ("T", "#FFD700"), ("I", "#FF6B9D"), ("M", "#00D9FF")]
    assert rows[3]["name"] == "extra" and rows[3]["letter"] == "E" and rows[3]["source"] == "env"


def test_added_pot_starts_empty_trades_only_its_own_money():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm, exchange = live_pots(db, usd=126.0)  # $30 not in any pot
    # Resting stop orders stay open (the fake would otherwise call them filled)
    exchange.fetch_order.side_effect = lambda oid, sym: (
        {"id": oid, "status": "open", "filled": 0.0} if str(oid).startswith("stop") else exchange._last)
    pot = pots.add_pot("dip", "rsi_bb", max_buys_per_day=2, order_pct=0.5)
    assert pot.tag == "live-dip" and pot.balances()["USDT"] == 0.0

    intraday.direction = "bullish"
    results = candle(pots, sm)
    assert not pot.holding and "no cash" in results["dip"]["note"]

    pots.transfer(UNASSIGNED, "dip", 20)
    assert pot.trader.initial_usdt == 20.0  # loss limit follows the money put in
    cash_before = {n: pots.get(n).balances()["USDT"] for n in BUILTIN_POTS}
    candle(pots, sm)
    assert pot.holding
    assert 9.0 < pot.balances()["USDT"] < 11.5  # about 50% per buy (BTC rounds to 0.00001)
    assert pots.get(POT_TREND).balances()["USDT"] == cash_before[POT_TREND]
    assert pots.reconcile() == []


def test_added_pot_is_back_after_a_restart_and_can_be_removed():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm, exchange = live_pots(db, usd=126.0)
    # Trend Hold places no exchange stop (the fake exchange can't tell stop
    # orders from market orders when the bot asks about one)
    pots.add_pot("dip", "trend_hold", order_pct=1.0)
    pots.transfer(UNASSIGNED, "dip", 20)
    trend.direction = "bullish"
    candle(pots, sm)
    btc = pots.get("dip").balances()["BASE"]

    again, *_ = build(db, mode="live", exchange=exchange)
    pot = again.get("dip")
    assert pot is not None and pot.source == "dashboard" and pot.holding
    assert pot.balances()["BASE"] == pytest.approx(btc)

    with pytest.raises(PotActionError, match="holds BTC"):
        again.remove_pot("dip", PRICE)
    again.sell_now("dip")
    with pytest.raises(PotActionError, match="cash"):
        again.remove_pot("dip", PRICE)
    again.transfer("dip", UNASSIGNED, round(pot.balances()["USDT"] - 0.005, 2))
    again.remove_pot("dip", PRICE)  # a sliver of BTC too small to sell may stay
    assert again.get("dip") is None
    assert again.reconcile() == []

    third, *_ = build(db, mode="live", exchange=exchange)
    assert third.get("dip") is None
    with pytest.raises(PotActionError, match="used before"):
        third.add_pot("dip", "rsi_bb")


def test_what_cannot_be_added_or_removed():
    db = initialize_database("sqlite:///:memory:")
    pots, *_ = live_pots(db, config=make_config(pots_extra="fromenv:trend_hold"))
    for bad, why in [("Tr-nd", "Name"), ("1abc", "Name"), ("trend", "already"),
                     ("unassigned", "already"), ("fromenv", "already"), ("way_too_long_name", "Name")]:
        with pytest.raises(PotActionError, match=why):
            pots.add_pot(bad, "rsi_bb")
    with pytest.raises(PotActionError, match="Unknown strategy"):
        pots.add_pot("x", "llm_pattern")
    with pytest.raises(PotActionError, match="isn't available"):
        pots.add_pot("x", "macd_volume")  # not set up in this test's strategy manager
    with pytest.raises(PotActionError, match="Spend per buy"):
        pots.add_pot("x", "rsi_bb", order_pct=0.01)
    with pytest.raises(PotActionError, match="built in"):
        pots.remove_pot(POT_INTRADAY, PRICE)
    with pytest.raises(PotActionError, match="BOT_POTS_EXTRA"):
        pots.remove_pot("fromenv", PRICE)


def test_bad_env_entries_are_skipped_and_the_bot_still_starts():
    specs, errors = parse_extra_pots("a:rsi_bb:2:0.5, broken, b:ema:x")
    assert specs == [{"name": "a", "strategy": "rsi_bb", "max_buys_per_day": 2, "order_pct": 0.5}]
    assert len(errors) == 2
    pots, *_ = live_pots(config=make_config(pots_extra="ok:rsi_bb, nope:no_such, TREND:rsi_bb"))
    assert list(pots.pots) == [*BUILTIN_POTS, "ok"]


def test_add_and_remove_api():
    from app import create_app, init_services
    from auth import get_auth_config

    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False, use_atr_stops=False)
    pots, trend, intraday, sm, exchange = live_pots(db, config=config)
    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots)
    client = app.test_client()
    try:
        with patch("config.BotConfig.load", return_value=config):
            data = client.get("/api/pots").get_json()
            assert [c["key"] for c in data["strategy_choices"]][:2] == ["trend_hold", "rsi_bb"]

            r = client.post("/api/pots/add", json={"name": "dip", "strategy": "rsi_bb",
                                                   "max_buys_per_day": 2, "order_pct": 0.9})
            assert r.status_code == 200, r.get_json()
            names = [p["name"] for p in client.get("/api/pots").get_json()["pots"]]
            assert names == [*BUILTIN_POTS, "dip"]

            r = client.post("/api/pots/add", json={"name": "dip", "strategy": "rsi_bb"})
            assert r.status_code == 400

            r = client.post("/api/pots/remove", json={"pot": "dip"})
            assert r.status_code == 200, r.get_json()
            r = client.post("/api/pots/remove", json={"pot": "trend"})
            assert r.status_code == 400 and "built in" in r.get_json()["error"]
    finally:
        state.set_pot_manager(None)
