"""Strategy Signals shows every strategy a pot trades.

On 2026-11-02 the panel showed only Trend Hold: RSI + Bollinger Bands was
switched off on the Strategies page, but the Intraday pot trades it anyway.
"""

import threading
from types import SimpleNamespace

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from app.api.strategies import _pattern_description
from strategies.constants import StrategyNames
from database import initialize_database
from pots import POT_TREND
from tests.test_pots import candle, live_pots, make_config


def test_signals_list_the_pots_that_trade_each_strategy():
    from app import create_app, init_services
    from auth import get_auth_config
    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False)
    pots, trend, intraday, sm, exchange = live_pots(db, config=config)
    trend.direction = "bullish"
    candle(pots, sm)

    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots)
    try:
        data = app.test_client().get("/api/strategies/signals").get_json()
        assert data["pots_enabled"] is True
        by_name = {s["name"]: s for s in data["signals"]}
        trend_pots = by_name[StrategyNames.TREND_HOLD]["pots"]
        assert [p["name"] for p in trend_pots] == ["trend"] and trend_pots[0]["holding"]
        intraday_pots = by_name[StrategyNames.RSI_BB_MEAN_REVERSION]["pots"]
        assert [p["name"] for p in intraday_pots] == ["intraday"]
        assert intraday_pots[0]["color"].startswith("#") and not intraday_pots[0]["holding"]
    finally:
        state.set_pot_manager(None)


def test_rsi_text_says_what_is_missing():
    sig = SimpleNamespace(direction="neutral", indicators={"rsi": 17.9},
                          info={"rsi_bullish": True, "bb_lower_touch": False})
    text = _pattern_description(StrategyNames.RSI_BB_MEAN_REVERSION, sig)
    assert "oversold (17.9)" in text and "lower band" in text
    sig.info = {}
    sig.indicators = {"rsi": 50.0}
    assert "not oversold" in _pattern_description(StrategyNames.RSI_BB_MEAN_REVERSION, sig)
