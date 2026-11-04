"""The "Where the money is" table: pots next to the exchange account.

Added 2026-11-02 so the dashboard shows, in one place, how much money there
is, which pot owns it, how much is cash and how much BTC, and that it adds
up to what Binance.US holds.
"""

from database import initialize_database
from pots import POT_TREND
from tests.test_pots import PRICE, candle, live_pots


def test_account_check_matches_after_a_buy():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, _, sm, exchange = live_pots(db)
    trend.direction = "bullish"
    candle(pots, sm)  # the trend pot buys
    exchange.usd += 4.0  # cash that no pot owns
    pots.unassigned_cash()  # refreshes the exchange balance

    a = pots.account_check()
    assert a["matches"] is True
    assert abs(a["usd"] - exchange.usd) < 1e-9 and abs(a["btc"] - exchange.btc) < 1e-12
    assert abs(a["left_usd"] - 4.0) < 0.01
    assert a["pots_btc"] == pots.get(POT_TREND).trader.base_balance
    # Pots + left over = the whole account
    assert abs(a["pots_usd"] + a["left_usd"] - a["usd"]) < 1e-9
    assert abs((a["pots_btc"] + a["left_btc"]) * PRICE - a["btc"] * PRICE) < 1e-6


def test_account_check_flags_missing_btc():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, _, sm, exchange = live_pots(db)
    trend.direction = "bullish"
    candle(pots, sm)
    exchange.btc = 0.0  # BTC gone from the account
    pots.unassigned_cash()
    assert pots.account_check()["matches"] is False


def test_api_pots_includes_the_account():
    import threading
    import auth as _auth_module  # noqa: F401
    from app import create_app, init_services
    from auth import get_auth_config
    from tests.test_pots import make_config
    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False)
    pots, _, _, sm, exchange = live_pots(db, config=config)
    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots)
    state.update_trading_state(current_price=PRICE)
    try:
        data = app.test_client().get("/api/pots").get_json()
        assert data["account"]["matches"] is True
        assert abs(data["account"]["usd"] - 96.0) < 1e-9
        # For "If each pot sold now"
        assert data["sell_terms"]["fee_rate"] >= 0 and data["sell_terms"]["amount_step"] > 0
    finally:
        state.set_pot_manager(None)
