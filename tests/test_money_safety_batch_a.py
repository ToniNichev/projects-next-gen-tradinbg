"""Batch A of the 2026-11-02 audit: no pot may ever use another pot's money.

1. An order that went through but couldn't be recorded stops that pot until
   a person checks it (otherwise the next check sells the same coins again,
   out of another pot's BTC).
2. An order with no clear answer is looked up on the exchange before trying
   again (a blind retry could buy or sell twice).
3. When the pots don't match the exchange, buying stops in every pot (and
   selling too when BTC is short) until a person clears it.
4. A stop order that sold while the bot was down is booked at start-up,
   not cancelled and forgotten.
5. A stop that can't be cancelled is kept, and nothing is sold against it.
"""

from unittest.mock import MagicMock

import ccxt
import pytest

from database import initialize_database
from live_trader import OrderStateUnknown
from pots import POT_INTRADAY, POT_MANUAL, POT_TREND, PotActionError
from tests.test_exchange_stop_fill import stop_fills
from tests.test_pots import PRICE, build, candle, live_pots


def holding(db=None):
    """Trend and intraday both bought; intraday has a stop on the exchange."""
    pots, trend, intraday, sm, exchange = live_pots(db)
    trend.direction = intraday.direction = "bullish"
    candle(pots, sm)
    assert pots.get(POT_TREND).holding and pots.get(POT_INTRADAY).holding
    intraday.direction = "neutral"
    return pots, trend, intraday, sm, exchange


def lose_reply(exchange, side):
    """The order goes through on the exchange, but the reply is lost."""
    real = exchange._sell if side == "sell" else exchange._buy

    def flaky(symbol, amount, params=None):
        real(symbol, amount, params)
        raise ccxt.RequestTimeout("read timed out")
    mock = MagicMock(side_effect=flaky)
    setattr(exchange, f"create_market_{side}_order", mock)
    return mock


# ------------------------------------------------- 2. unclear answers

def test_sell_with_a_lost_reply_is_found_and_booked_once():
    pots, _, _, sm, exchange = holding()
    sells = lose_reply(exchange, "sell")
    trade = pots.sell_now(POT_INTRADAY)
    assert trade.side == "sell"
    assert sells.call_count == 1                      # not sent a second time
    assert not pots.get(POT_INTRADAY).holding
    assert pots.reconcile() == [] and pots.mismatch is None
    assert not pots.get(POT_INTRADAY).trader.needs_check


def test_buy_that_never_reached_the_exchange_is_tried_again():
    pots, trend, _, sm, exchange = live_pots()
    real = exchange._buy
    calls = {"n": 0}

    def first_fails(symbol, amount, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ccxt.NetworkError("connection reset")  # never reached Binance
        return real(symbol, amount, params)
    exchange.create_market_buy_order = MagicMock(side_effect=first_fails)
    trend.direction = "bullish"
    candle(pots, sm)
    assert calls["n"] == 2 and pots.get(POT_TREND).holding
    assert pots.reconcile() == []


def test_no_clear_answer_stops_the_pot_until_checked(no_real_notifications):
    db = initialize_database("sqlite:///:memory:")
    pots, _, intraday, sm, exchange = holding(db)
    lose_reply(exchange, "sell")
    base_fetch = exchange.fetch_order.side_effect

    def lookup_down(oid, sym=None, params=None):
        if params:
            raise ccxt.NetworkError("lookup failed too")
        return base_fetch(oid, sym, params)
    exchange.fetch_order.side_effect = lookup_down

    with pytest.raises(OrderStateUnknown):
        pots.sell_now(POT_INTRADAY)
    pot = pots.get(POT_INTRADAY)
    assert pot.trader.needs_check
    assert any("Not sure" in n[0] for n in no_real_notifications)

    # The next hourly check leaves this pot alone (no second sell)
    intraday.direction = "bearish"
    sells_before = exchange.create_market_sell_order.call_count
    results = candle(pots, sm)
    assert "check" in results[POT_INTRADAY]["note"]
    assert exchange.create_market_sell_order.call_count == sells_before

    # Remembered across a restart
    again, *_ = build(db, mode="live", exchange=exchange)
    assert again.get(POT_INTRADAY).trader.needs_check
    assert again.summary(PRICE)["pots"][1]["needs_check"]


# ---------------------------------------- 1. went through, not recorded

def test_sell_that_cant_be_recorded_stops_the_pot(no_real_notifications):
    pots, _, intraday, sm, exchange = holding()
    pot = pots.get(POT_INTRADAY)
    pot.trader._log_trade = MagicMock(side_effect=RuntimeError("database is locked"))
    with pytest.raises(RuntimeError):
        pots.sell_now(POT_INTRADAY)
    assert exchange.create_market_sell_order.call_count == 1
    assert pot.trader.needs_check and "wasn't recorded" in pot.trader.needs_check
    assert any("not recorded" in n[0] for n in no_real_notifications)
    assert not any("order failed" in n[0] for n in no_real_notifications)  # it did go through

    intraday.direction = "bearish"
    candle(pots, sm)
    assert exchange.create_market_sell_order.call_count == 1  # never sold twice


def test_balance_refresh_failing_after_a_fill_doesnt_lose_the_trade():
    pots, _, _, sm, exchange = holding()
    pot = pots.get(POT_INTRADAY)
    real_balance = exchange.fetch_balance

    def sell_then_break(symbol, amount, params=None):
        order = exchange._sell(symbol, amount, params)
        exchange.fetch_balance = MagicMock(side_effect=ccxt.NetworkError("balance timed out"))
        return order
    exchange.create_market_sell_order = MagicMock(side_effect=sell_then_break)
    trade = pots.sell_now(POT_INTRADAY)
    assert trade is not None and not pot.holding and not pot.trader.needs_check
    exchange.fetch_balance = real_balance
    assert pots.reconcile() == []


# -------------------------------------------- 3. pots vs the exchange

def test_cash_mismatch_stops_buying_everywhere_until_cleared():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, _, sm, exchange = live_pots(db)
    pots.notify = MagicMock()
    exchange.usd -= 50.0                       # money gone from the account
    trend.direction = "bullish"
    candle(pots, sm)
    assert not pots.get(POT_TREND).holding     # didn't buy
    assert pots.mismatch and pots.mismatch["cash"] and not pots.mismatch["btc"]
    assert "don't match" in pots.notify.call_args.args[0]
    assert pots.notify.call_count == 1        # once, not every hour
    manual = pots.get(POT_MANUAL).trader
    assert manual.execute_market_buy(0.00005) is None
    assert "Buying is stopped" in manual.last_refusal

    with pytest.raises(PotActionError, match="still don't match"):
        pots.clear_mismatch()

    candle(pots, sm)
    assert pots.notify.call_count == 1
    exchange.usd += 50.0                       # sorted out
    candle(pots, sm)
    assert not pots.get(POT_TREND).holding     # still stopped: a person must clear it
    again, *_ = build(db, mode="live", exchange=exchange)
    assert again.mismatch and again.get(POT_TREND).trader.pots_mismatch  # survives a restart

    pots.clear_mismatch()
    assert pots.mismatch is None
    candle(pots, sm)
    assert pots.get(POT_TREND).holding


def test_btc_short_stops_selling_too():
    pots, _, _, sm, exchange = holding()
    exchange.btc -= 0.0005
    pots.reconcile()
    assert pots.mismatch["btc"]
    with pytest.raises(PotActionError, match="Selling is stopped"):
        pots.sell_now(POT_TREND)
    exchange.create_market_sell_order.assert_not_called()


def test_a_normal_stop_sale_mid_hour_is_not_a_mismatch():
    pots, _, _, sm, exchange = holding()
    stop_fills(exchange)                       # sold on the exchange between checks
    results = candle(pots, sm)
    assert results[POT_INTRADAY]["exit"].exit_reason == "stop_loss"
    assert pots.mismatch is None


# ----------------------------------------------- 4. stop sold while down

def test_stop_that_sold_while_the_bot_was_down_is_booked_at_start_up():
    db = initialize_database("sqlite:///:memory:")
    pots, _, _, sm, exchange = holding(db)
    pots.transfer(POT_MANUAL, POT_INTRADAY, 2.0)   # a cash move before the restart
    cash_before = pots.get(POT_INTRADAY).balances()["USDT"]
    amount, fill_price, fee = stop_fills(exchange)
    stops_placed = exchange.create_order.call_count

    again, *_ = build(db, mode="live", exchange=exchange)
    pot = again.get(POT_INTRADAY)
    assert not pot.holding
    assert pot.balances()["USDT"] == pytest.approx(cash_before + amount * fill_price - fee)
    assert exchange.create_order.call_count == stops_placed   # no new stop on others' coins
    row = db.get_trades(limit=1, pot="live-intraday")[0]
    assert row.side == "sell" and row.exit_reason == "stop_loss"
    assert again.reconcile() == [] and again.mismatch is None


# ------------------------------------------------ 5. stop can't be cancelled

def test_stop_that_cant_be_cancelled_is_kept_and_nothing_is_sold():
    pots, _, _, sm, exchange = holding()
    pot = pots.get(POT_INTRADAY)
    exchange.cancel_order = MagicMock(side_effect=ccxt.NetworkError("cancel timed out"))
    with pytest.raises(PotActionError):
        pots.sell_now(POT_INTRADAY)
    exchange.create_market_sell_order.assert_not_called()
    assert pot.holding and pot.trader.open_position.exchange_stop_order_id == "stop-1"


def test_stop_that_sold_part_before_the_cancel_is_booked_then_the_rest_sold():
    pots, _, _, sm, exchange = holding()
    pot = pots.get(POT_INTRADAY)
    part = 0.0001
    fill = PRICE * 0.99

    def cancel(oid, sym):
        fee = part * fill * 0.001
        exchange.btc -= part
        exchange.usd += part * fill - fee
        return {"id": oid, "status": "canceled", "filled": part, "average": fill,
                "fee": {"cost": fee, "currency": "USD"}}
    exchange.cancel_order = MagicMock(side_effect=cancel)
    trade = pots.sell_now(POT_INTRADAY)
    assert trade.exit_reason == "manual"
    assert exchange.create_market_sell_order.call_count == 1
    sold = exchange.create_market_sell_order.call_args.kwargs["amount"]
    assert sold < 0.00017 + 1e-12 and sold <= 0.00017982 - part + 1e-12   # only what's left
    assert not pot.holding
    assert pots.reconcile() == [] and pots.mismatch is None


# ------------------------------------------------------- dashboard buttons

def test_clear_buttons_only_work_when_the_pots_match():
    import threading
    import auth as _auth_module  # noqa: F401
    from app import create_app, init_services
    from auth import get_auth_config
    from tests.test_pots import make_config
    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    config = make_config(dashboard_auth_enabled=False, enable_rate_limiting=False)
    pots, *_rest, exchange = live_pots(db, config=config)
    app = create_app()
    app.config.update(TESTING=True)
    state = init_services(pots.get(POT_TREND).trader, threading.Lock(), exchange, _rest[2], config)
    state.set_pot_manager(pots)
    state.update_trading_state(current_price=PRICE)
    client = app.test_client()
    try:
        exchange.usd -= 50.0
        pots.reconcile()
        pots.get(POT_INTRADAY).trader.flag_needs_check("test: a sell wasn't recorded")
        data = client.get("/api/pots").get_json()
        assert data["mismatch"]["cash"] and data["pots"][1]["needs_check"]

        r = client.post("/api/pots/clear-mismatch", json={})
        assert r.status_code == 400 and "still don't match" in r.get_json()["error"]
        r = client.post("/api/pots/clear-check", json={"pot": POT_INTRADAY})
        assert r.status_code == 400

        exchange.usd += 50.0
        assert client.post("/api/pots/clear-mismatch", json={}).get_json()["success"]
        assert client.post("/api/pots/clear-check", json={"pot": POT_INTRADAY}).get_json()["success"]
        data = client.get("/api/pots").get_json()
        assert data["mismatch"] is None and not data["pots"][1]["needs_check"]
    finally:
        state.set_pot_manager(None)
