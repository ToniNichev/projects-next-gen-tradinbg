"""Strategies page with money pots: each pot's rule and the settings it uses.

On 2026-11-04 the old page's switch showed RSI + Bollinger Bands as off while
the Intraday pot traded it every hour, and one Presets click could rewrite the
settings a pot trades real money with.
"""

import threading

import pytest

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from config import BotConfig
from database import initialize_database
from pots import POT_INTRADAY, POT_TREND, build_pots
from strategies.constants import StrategyNames
from strategies.rsi_bb_strategy import RSIBollingerBandsStrategy
from strategies.strategy_manager import StrategyManager
from strategies.trend_hold_strategy import TrendHoldStrategy
from app.api import pot_settings
from tests.test_pots import make_config


def real_setup():
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False)
    cfgs = BotConfig.load().get_strategy_configs()
    rsi = RSIBollingerBandsStrategy(cfgs["rsi_bb"])
    trend = TrendHoldStrategy(cfgs["trend_hold"])
    sm = StrategyManager([trend, rsi])
    pots = build_pots(config, exchange=None, db_manager=db, strategy_manager=sm, trading_mode="paper")
    return db, config, pots, sm, rsi, trend


@pytest.fixture
def client():
    from app import create_app, init_services
    from auth import get_auth_config
    get_auth_config().enabled = False
    db, config, pots, sm, rsi, trend = real_setup()
    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), None, sm, config)
    state.set_pot_manager(pots)
    try:
        yield app.test_client(), db, pots, rsi, trend
    finally:
        state.set_pot_manager(None)


def test_each_pot_lists_only_the_settings_it_uses(client):
    c, *_ = client
    data = c.get("/api/pot-strategies").get_json()
    assert data["pots_enabled"] is True
    by = {p["name"]: p for p in data["pots"]}
    keys = {n: [f["key"] for f in p["settings"]] for n, p in by.items()}
    assert "strategy_rsi_bb_rsi_oversold" in keys["intraday"]
    assert keys["trend"] == ["strategy_trend_ma_days", "strategy_trend_band", "strategy_trend_emergency_stop_pct"]
    assert "take_profit_pct" in keys["manual"]
    # Percents shown as percents; shared settings name the other pot
    band = next(f for f in by["trend"]["settings"] if f["key"] == "strategy_trend_band")
    assert band["unit"] == "%" and band["value"] == pytest.approx(1.0)
    atr = next(f for f in by["intraday"]["settings"] if f["key"] == "atr_stop_multiplier")
    assert atr["also"] == ["Manual"]
    assert any("RSI below" in r for r in by["intraday"]["rules"])
    assert "Trend Hold" not in " ".join(data["unused_strategies"])


def test_check_only_saves_nothing(client):
    c, db, pots, rsi, _ = client
    r = c.post("/api/pot-strategies/update", json={"pot": "intraday",
               "changes": {"strategy_rsi_bb_rsi_oversold": 25}})
    j = r.get_json()
    assert r.status_code == 200 and j["applied"] is False
    assert j["changes"][0]["before"] == 30 and j["changes"][0]["after"] == 25
    assert rsi.rsi_oversold == 30
    assert "strategy_rsi_bb_rsi_oversold" not in db.get_all_strategy_configs()


def test_confirmed_change_reaches_the_running_strategy(client):
    c, db, pots, rsi, _ = client
    r = c.post("/api/pot-strategies/update", json={"pot": "intraday", "confirm": True,
               "changes": {"strategy_rsi_bb_rsi_oversold": 25, "strategy_rsi_bb_take_profit_pct": 2.5}})
    j = r.get_json()
    assert r.status_code == 200 and j["success"] and j["applied"] and not j["not_applied"]
    assert rsi.rsi_oversold == 25 and rsi.take_profit_pct == pytest.approx(0.025)
    assert pots.get(POT_INTRADAY).strategy is rsi
    assert db.get_all_strategy_configs()["strategy_rsi_bb_take_profit_pct"] == pytest.approx(0.025)


@pytest.mark.parametrize("pot,changes", [
    ("trend", {"strategy_rsi_bb_rsi_oversold": 25}),      # not this pot's setting
    ("intraday", {"strategy_rsi_bb_rsi_oversold": 99}),   # out of range
    ("intraday", {"rsi_period": 14.5}),                   # not whole
    ("intraday", {"use_atr_stops": "yes"}),               # not on/off
    ("intraday", {"strategy_rsi_bb_rsi_oversold": 30}),   # nothing changes
    ("nope", {"rsi_period": 10}),
])
def test_bad_changes_are_refused(client, pot, changes):
    c, db, *_ = client
    r = c.post("/api/pot-strategies/update", json={"pot": pot, "changes": changes, "confirm": True})
    assert r.status_code == 400
    assert not set(db.get_all_strategy_configs()) & pot_settings.LIVE_KEYS


def test_presets_are_off_and_old_form_skips_pot_settings(client):
    c, db, *_ = client
    r = c.post("/api/presets/anything/apply")
    assert r.status_code == 409
    r = c.post("/api/strategy-config/update", json={"strategy_rsi_bb_rsi_oversold": 10, "short_window": 9})
    j = r.get_json()
    assert j["skipped_pot_keys"] == ["strategy_rsi_bb_rsi_oversold"]
    saved = db.get_all_strategy_configs()
    assert "strategy_rsi_bb_rsi_oversold" not in saved and saved["short_window"] == 9


def test_strategies_page_is_the_pot_page(client):
    c, *_ = client
    assert b"Pot strategies" in c.get("/strategies").data
    old = c.get("/strategies/all").data
    assert b"Strategy Center" in old and b"Money pots are on" in old


def test_display_conversions():
    assert pot_settings.from_display("strategy_trend_band", 1.5) == pytest.approx(0.015)
    assert pot_settings.to_display("strategy_trend_band", 0.015) == pytest.approx(1.5)
    with pytest.raises(ValueError):
        pot_settings.from_display("strategy_trend_ma_days", 5)
    assert set(pot_settings.POT_FIELDS[StrategyNames.TREND_HOLD]) <= set(pot_settings.FIELDS)
