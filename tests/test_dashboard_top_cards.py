"""The dashboard's top cards with money pots.

On 2026-11-02 the "Portfolio" card showed ~$74: only the Trend Hold pot,
because the plain balances in /state are the main (trend) trader's. The
"Last trade" card also didn't say which pot traded.
"""

import threading
from unittest.mock import patch

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from app.api import market
from database import initialize_database
from pots import POT_TREND
from tests.test_pots import PRICE, candle, live_pots, make_config


def test_state_has_every_pot_and_the_last_trades_pot():
    from app import create_app, init_services
    from auth import get_auth_config
    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False,
                         use_atr_stops=False)
    pots, trend, intraday, sm, exchange = live_pots(db, config=config)
    trend.direction = "bullish"
    candle(pots, sm)  # the trend pot buys; intraday and manual stay in cash

    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots)
    state.update_trading_state(current_price=PRICE)
    market._UNASSIGNED_CACHE.update(at=0.0, value=0.0)
    try:
        with patch("config.BotConfig.load", return_value=config):
            data = app.test_client().get("/state").get_json()
        o = data["pots"]
        assert o is not None and o["real_money"] is True
        # Every pot's money, not just the trend pot's
        assert o["value"] > 90 and o["invested"] == 96.0
        assert abs(o["value"] - (o["cash"] + o["btc_value"])) < 0.01
        assert [h["name"] for h in o["holding"]] == ["trend"]
        assert o["holding"][0]["value"] > 70
        # The plain balances are still one pot's (kept for the no-pots layout)
        assert data["balances"]["USDT"] + data["balances"]["BASE"] * PRICE < 80
        assert data["last_trade"]["pot"] == "trend" and data["last_trade"]["side"] == "buy"
    finally:
        state.set_pot_manager(None)


def test_no_pots_means_no_overview():
    class NoPots:
        def get_pot_manager(self):
            return None
    assert market._pots_overview(NoPots()) is None
