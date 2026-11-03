"""Batch D of the 2026-11-03 review.

1. Another website can't make the browser press money buttons (emergency
   stop, manual sell, ...) while the user is logged in.
2. "Clear trades" never wipes the records of real trades.
3. After a restart, no exchange stop is placed for coins that may already be
   sold (it would rest on another pot's coins and could sell them).
4. A stop that sold part of its coins (or sold seconds ago) is not taken for
   missing BTC, which would stop all selling in every pot.
5. Dollars from a stop sale not booked yet can't be handed to another pot.
"""

import threading
from unittest.mock import MagicMock, patch

import ccxt
import pytest

from database import initialize_database
from live_trader import OrderStateUnknown
from pots import POT_INTRADAY, POT_MANUAL, POT_TREND, UNASSIGNED, TransferError
from tests.test_exchange_stop_fill import route_fetch, stop_fills
from tests.test_money_safety_batch_a import holding, lose_reply
from tests.test_pots import PRICE, build, candle, live_pots, make_config


# ------------------------------------------------------- dashboard requests

@pytest.fixture
def client():
    import auth as _auth_module  # noqa: F401
    from app import create_app, init_services
    from app.core.state import get_app_state
    from auth import get_auth_config
    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False,
                         allowed_origins="https://trading.example.com")
    config.trading_mode = "live"
    pots, trend, intraday, sm, exchange = live_pots(db, config=config)
    trend.direction = "bullish"
    candle(pots, sm)
    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, sm, config)
    state.set_pot_manager(pots)
    state.update_trading_state(current_price=PRICE)
    with patch("config.BotConfig.load", return_value=config), \
            patch("app.api.trading.get_database", return_value=db):
        yield app.test_client(), pots, exchange, db
    get_app_state().set_pot_manager(None)


def test_another_website_cant_press_money_buttons(client):
    c, pots, exchange, _ = client
    sells = exchange.create_market_sell_order.call_count
    for path in ("/api/trading/emergency-stop", "/api/manual/sell", "/api/manual/buy",
                 "/api/trading/enable", "/api/manual/clear-trades"):
        r = c.post(path, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403, path
        assert "another website" in r.get_json()["error"]
    # A page with no Origin still gives itself away by its Referer
    r = c.post("/api/trading/emergency-stop", headers={"Referer": "https://evil.example/x"})
    assert r.status_code == 403
    assert exchange.create_market_sell_order.call_count == sells
    assert pots.get(POT_TREND).holding


def test_the_dashboard_itself_and_scripts_still_work(client):
    c, *_ = client
    # The dashboard page, directly and through the proxy's public name
    for origin in ("http://localhost", "https://trading.example.com"):
        r = c.post("/api/pots/clear-mismatch", json={}, headers={"Origin": origin})
        assert r.status_code == 200, (origin, r.get_json())
    # curl / the API key send no Origin or Referer: up to the normal login
    assert c.post("/api/pots/clear-mismatch", json={}).status_code == 200
    # Reading is never blocked
    assert c.get("/api/pots", headers={"Origin": "https://evil.example"}).status_code == 200


def test_clear_trades_refused_with_real_money(client):
    c, pots, _, db = client
    r = c.post("/api/manual/clear-trades")
    assert r.status_code == 403 and "paper mode" in r.get_json()["error"]
    assert db.get_trade_stats()["total_trades"] >= 1
    assert pots.get(POT_TREND).holding


# ------------------------------------------- 3. no stop on coins maybe sold

def test_restart_after_an_unclear_sell_places_no_stop(no_real_notifications):
    db = initialize_database("sqlite:///:memory:")
    pots, _, _, sm, exchange = holding(db)
    lose_reply(exchange, "sell")              # the sale went through, the reply was lost
    base_fetch = exchange.fetch_order.side_effect

    def lookup_down(oid, sym=None, params=None):
        if params:
            raise ccxt.NetworkError("lookup failed too")
        return base_fetch(oid, sym, params)
    exchange.fetch_order.side_effect = lookup_down
    with pytest.raises(OrderStateUnknown):
        pots.sell_now(POT_INTRADAY)
    stops = exchange.create_order.call_count

    again, *_ = build(db, mode="live", exchange=exchange)
    assert again.get(POT_INTRADAY).trader.needs_check
    assert exchange.create_order.call_count == stops     # no stop on Trend's coins


def test_restart_after_a_crash_mid_sale_places_no_stop(no_real_notifications):
    """The bot died after Binance sold the coins but before booking it."""
    db = initialize_database("sqlite:///:memory:")
    pots, _, _, sm, exchange = holding(db)
    amount = exchange.create_order.call_args.args[3]
    exchange.btc -= pots.get(POT_INTRADAY).trader.base_balance    # sold...
    exchange.usd += amount * PRICE
    route_fetch(exchange, {"id": "stop-1", "status": "canceled", "filled": 0.0})  # ...stop cancelled first
    stops = exchange.create_order.call_count

    again, *_ = build(db, mode="live", exchange=exchange)
    assert again.mismatch and again.mismatch["btc"]
    assert exchange.create_order.call_count == stops


def test_restart_still_rearms_stops_when_everything_matches():
    db = initialize_database("sqlite:///:memory:")
    pots, _, _, sm, exchange = holding(db)
    stops = exchange.create_order.call_count
    again, *_ = build(db, mode="live", exchange=exchange)
    assert again.mismatch is None
    assert exchange.create_order.call_count == stops + 1
    assert again.get(POT_INTRADAY).trader.open_position.exchange_stop_order_id


def test_clearing_the_check_puts_the_stop_back():
    pots, _, _, sm, exchange = holding()
    t = pots.get(POT_INTRADAY).trader
    t.open_position.exchange_stop_order_id = None    # held back while unchecked
    t.flag_needs_check("test")
    stops = exchange.create_order.call_count
    pots.clear_needs_check(POT_INTRADAY)
    assert exchange.create_order.call_count == stops + 1
    assert t.open_position.exchange_stop_order_id


# ----------------------------------------------- 4. stop sales not booked yet

def part_filled_stop(exchange, part=0.00005, fill=PRICE * 0.968):
    """The price gapped through the stop's limit: part sold, the rest waits."""
    amount = exchange.create_order.call_args.args[3]
    exchange.btc -= part
    exchange.usd += part * fill
    route_fetch(exchange, {"id": "stop-1", "status": "open", "amount": amount, "filled": part,
                           "average": fill, "fee": {"cost": 0.0, "currency": "USD"}})


def test_part_filled_stop_doesnt_stop_selling():
    pots, trend, _, sm, exchange = holding()
    part_filled_stop(exchange)
    trend.direction = "bearish"
    r = candle(pots, sm, price=PRICE * 0.95)
    assert pots.mismatch is None
    assert r[POT_TREND]["trade"] is not None and not pots.get(POT_TREND).holding
    # The intraday pot's own stop-loss sold what the exchange stop hadn't
    assert not pots.get(POT_INTRADAY).holding
    assert pots.reconcile() == []


def test_stop_that_sold_seconds_ago_is_not_a_mismatch():
    pots, *_rest, exchange = holding()
    stop_fills(exchange)            # sold between the stop check and the account check
    assert pots.reconcile() == [] and pots.mismatch is None


def test_real_missing_btc_is_still_caught():
    pots, *_rest, exchange = holding()
    exchange.btc -= 0.0005
    assert pots.reconcile() and pots.mismatch["btc"]


def test_unreadable_stop_is_given_the_benefit_of_the_doubt_only_up_to_its_coins():
    pots, *_rest, exchange = holding()
    exchange.fetch_order.side_effect = ccxt.NetworkError("down")
    exchange.btc -= 0.0005          # more than the intraday pot holds
    assert pots.reconcile() and pots.mismatch["btc"]


# ------------------------------------------------- 5. unbooked stop dollars

def test_stop_sale_dollars_cant_go_to_another_pot():
    pots, *_rest, exchange = holding()
    amount, fill, fee = stop_fills(exchange)
    proceeds = round(amount * fill - fee, 2)
    with pytest.raises(TransferError):
        pots.transfer(UNASSIGNED, POT_MANUAL, proceeds)
    assert not pots.get(POT_INTRADAY).holding        # booked to its own pot instead
    assert pots.reconcile() == []
