"""With real money, the dashboard shows real trades only.

On 2026-11-02 the dashboard's "last trade" said "Bought $98.73": a practice
(paper) trade from Oct 22, shown while the bot was trading real money.
"""

import threading
from datetime import datetime, timezone
from unittest.mock import patch

import auth as _auth_module  # noqa: F401  (import order, see test_manual_trade_api)
from database import initialize_database
from pots import POT_TREND
from tests.test_pots import PRICE, candle, live_pots, make_config


def practice_trade(db, pot=None, when=None):
    db.add_trade({
        "timestamp": when or datetime(2026, 10, 22, 19, 0, tzinfo=timezone.utc),
        "side": "buy", "price": 81330.0, "amount": 0.00121, "notional": 98.73,
        "fee": 0.07, "slippage": 0.0, "usdt_balance": 0.92, "base_balance": 0.00121,
        "pot": pot,
    })


def test_db_splits_real_and_practice_trades():
    db = initialize_database("sqlite:///:memory:")
    practice_trade(db)                 # before pots: no tag
    practice_trade(db, pot="intraday")  # a paper pot
    practice_trade(db, pot="live-trend")
    assert len(db.get_trades()) == 3
    assert [t.pot for t in db.get_trades(live=True)] == ["live-trend"]
    assert {t.pot for t in db.get_trades(live=False)} == {None, "intraday"}
    assert db.get_trade_stats(live=True)["total_trades"] == 1


def test_dashboard_hides_practice_trades_when_live():
    from app import create_app, init_services
    from auth import get_auth_config

    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False,
                         use_atr_stops=False)
    pots, trend, intraday, sm, exchange = live_pots(db, config=config)
    # A newer practice trade, so "latest" would pick it if not filtered
    practice_trade(db, when=datetime(2030, 1, 1, tzinfo=timezone.utc))
    trend.direction = "bullish"
    candle(pots, sm)  # a real buy in the trend pot
    assert pots.get(POT_TREND).holding

    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots)
    client = app.test_client()
    try:
        with patch("config.BotConfig.load", return_value=config):
            r = client.get("/api/trades")
            data = r.get_json()
            assert r.status_code == 200, r.data[:300]
            assert data["scope"] == "real"
            assert [t["pot"] for t in data["trades"]] == ["trend"]
            assert data["trades"][0]["notional"] < 80  # the real ~$74 buy, not $98.73

            last = client.get("/state").get_json()["last_trade"]
            assert last and last["price"] == PRICE

            practice = client.get("/api/trades?practice=1").get_json()
            assert practice["scope"] == "practice" and len(practice["trades"]) == 1
            assert client.get("/api/stats").get_json()["total_trades"] == 1
    finally:
        state.set_pot_manager(None)
