"""Fixes from the 2026-11-17 review.

- A stop order that failed to place is placed again on the next hourly check.
- An order whose reply was lost and that the exchange can't find at first is
  looked up again before it is sent a second time.
- Binance's "execution status unknown" (-1006) counts as an unclear answer.
- The stop's limit price sits 0.75% under its trigger.
"""

from unittest.mock import MagicMock

import ccxt
import pytest

import live_trader
from pots import POT_INTRADAY, POT_TREND
from tests.test_pots import candle, live_pots


def test_stop_that_failed_to_place_is_placed_again_next_hour():
    pots, trend, intraday, sm, exchange = live_pots()
    exchange.create_order = MagicMock(side_effect=ccxt.NetworkError("blip"))
    trend.direction = intraday.direction = "bullish"
    candle(pots, sm)
    pot = pots.get(POT_INTRADAY)
    assert pot.holding and not pot.trader.open_position.exchange_stop_order_id

    exchange.create_order = MagicMock(return_value={"id": "stop-9", "status": "open"})
    trend.direction = "bullish"
    intraday.direction = "neutral"
    candle(pots, sm)
    assert pot.trader.open_position.exchange_stop_order_id == "stop-9"
    # Trend Hold has no real stop, so it isn't given one
    assert not pots.get(POT_TREND).trader.open_position.exchange_stop_order_id
    assert exchange.create_order.call_count == 1


def test_order_the_exchange_cant_find_at_first_is_not_sent_twice():
    pots, trend, _, sm, exchange = live_pots()
    real_buy = exchange._buy
    pending = {}

    def slow_buy(symbol, amount, params=None):
        pending["args"] = (symbol, amount, params)  # queued on the exchange
        raise ccxt.RequestTimeout("read timed out")
    exchange.create_market_buy_order = MagicMock(side_effect=slow_buy)

    base_fetch = exchange.fetch_order.side_effect
    looks = {"n": 0}

    def fetch(oid, sym=None, params=None):
        if params and "origClientOrderId" in params and pending:
            looks["n"] += 1
            if looks["n"] == 1:
                real_buy(*pending.pop("args"))  # it fills just after the first look
                raise ccxt.OrderNotFound("Order does not exist")
        return base_fetch(oid, sym, params)
    exchange.fetch_order.side_effect = fetch

    trend.direction = "bullish"
    candle(pots, sm)
    assert exchange.create_market_buy_order.call_count == 1  # not sent again
    assert pots.get(POT_TREND).holding
    assert pots.reconcile() == []


def test_execution_status_unknown_is_looked_up_not_treated_as_a_failure():
    pots, trend, _, sm, exchange = live_pots()
    real_buy = exchange._buy

    def unknown(symbol, amount, params=None):
        real_buy(symbol, amount, params)
        raise ccxt.BadResponse('binanceus {"code":-1006,"msg":"An unexpected response was received"}')
    exchange.create_market_buy_order = MagicMock(side_effect=unknown)

    trend.direction = "bullish"
    candle(pots, sm)
    assert exchange.create_market_buy_order.call_count == 1
    assert pots.get(POT_TREND).holding
    assert pots.reconcile() == []


def test_stop_limit_sits_three_quarters_of_a_percent_under_the_trigger():
    pots, _, intraday, sm, exchange = live_pots()
    intraday.direction = "bullish"
    candle(pots, sm)
    args = exchange.create_order.call_args.args
    limit, trigger = args[4], args[5]["stopPrice"]
    assert limit == pytest.approx(trigger * (1 - live_trader.STOP_LIMIT_GAP), abs=0.01)
    assert live_trader.STOP_LIMIT_GAP == 0.0075
