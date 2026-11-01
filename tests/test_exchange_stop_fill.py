"""The exchange's stop order sold the coins mid-hour: the bot must notice.

A live buy places a stop-loss order on Binance.US. The exchange fires it the
moment the price touches it; the bot only looks once per closed candle.
Before this check the bot kept "holding" coins that were already sold.
"""

import pytest

from database import initialize_database
from pots import POT_INTRADAY
from tests.test_live_sell_dust import BinanceUSLike, make_trader, signal as trend_signal
from tests.test_pots import PRICE, candle, live_pots

FEE_RATE = 0.001


def buy_intraday(db=None):
    pots, trend, intraday, sm, exchange = live_pots(db)
    intraday.direction = "bullish"
    candle(pots, sm)
    pot = pots.get(POT_INTRADAY)
    assert pot.holding
    exchange.create_order.assert_called_once()  # the exchange-side stop
    intraday.direction = "neutral"
    return pots, intraday, sm, exchange, pot


def stop_fills(exchange, fill_price=PRICE * 0.968):
    """The exchange runs the resting stop: coins out, dollars in."""
    args = exchange.create_order.call_args.args
    amount = args[3]
    fee = amount * fill_price * FEE_RATE
    exchange.btc -= amount
    exchange.usd += amount * fill_price - fee
    stop = {"id": "stop-1", "status": "closed", "amount": amount, "filled": amount,
            "average": fill_price, "fee": {"cost": fee, "currency": "USD"}}
    route_fetch(exchange, stop)
    return amount, fill_price, fee


def route_fetch(exchange, stop):
    last = exchange.fetch_order.side_effect
    exchange.fetch_order.side_effect = lambda oid, sym: stop if oid == "stop-1" else last(oid, sym)


def test_filled_stop_is_booked_as_the_pots_sale():
    db = initialize_database("sqlite:///:memory:")
    pots, intraday, sm, exchange, pot = buy_intraday(db)
    cash_before = pot.balances()["USDT"]
    amount, fill_price, fee = stop_fills(exchange)

    # Next hourly check: the price has bounced back above the stop
    results = candle(pots, sm, price=PRICE)
    sale = results[POT_INTRADAY]["exit"]
    assert sale is not None and sale.exit_reason == "stop_loss"
    assert sale.price == pytest.approx(fill_price) and sale.pnl < 0
    assert not pot.holding
    assert pot.balances()["USDT"] == pytest.approx(cash_before + amount * fill_price - fee)
    assert pots.reconcile() == []                       # matches the exchange again
    exchange.create_market_sell_order.assert_not_called()  # nothing sold twice

    row = db.get_trades(limit=1, pot="live-intraday")[0]
    assert row.side == "sell" and row.exit_reason == "stop_loss"

    intraday.direction = "bullish"
    candle(pots, sm)
    assert pot.holding  # free to buy again


def test_resting_stop_changes_nothing():
    pots, intraday, sm, exchange, pot = buy_intraday()
    route_fetch(exchange, {"id": "stop-1", "status": "open", "filled": 0.0})
    results = candle(pots, sm)
    assert results[POT_INTRADAY]["exit"] is None and pot.holding
    assert exchange.create_order.call_count == 1


def test_stop_cancelled_without_selling_is_placed_again():
    pots, intraday, sm, exchange, pot = buy_intraday()
    route_fetch(exchange, {"id": "stop-1", "status": "canceled", "filled": 0.0})
    exchange.create_order.return_value = {"id": "stop-2", "status": "open"}
    candle(pots, sm)
    assert pot.holding
    assert exchange.create_order.call_count == 2
    assert pot.trader.open_position.exchange_stop_order_id == "stop-2"


def test_manual_sell_after_the_stop_fired_sells_nothing_more():
    pots, intraday, sm, exchange, pot = buy_intraday()
    stop_fills(exchange)
    trade = pot.trader.execute_market_sell(
        pot.trader.open_position.amount, exit_reason="manual", is_closing_sell=True,
    )
    assert trade is not None and trade.exit_reason == "stop_loss"
    assert not pot.holding
    exchange.create_market_sell_order.assert_not_called()


def test_single_account_trader_notices_too():
    exchange = BinanceUSLike()
    trader = make_trader(exchange)
    sig = trend_signal("bullish")
    sig.stop_loss = PRICE * 0.97  # a real stop -> placed on the exchange
    trader.handle_signal(sig)
    exchange.create_order.assert_called_once()
    stop_fills(exchange)
    sale = trader.update_position(PRICE)
    assert sale is not None and sale.exit_reason == "stop_loss"
    assert trader.open_position is None
