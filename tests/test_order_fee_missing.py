"""The exchange's order reply has an empty fee: the bot must still book the buy.

On 2026-11-02 the first real buy filled on Binance.US, but the reply had
fee {"cost": None}. The bot crashed reading it, so the buy was never recorded
and the pot still showed all its cash. The real fee is in the order's fills.
"""

from unittest.mock import MagicMock

import pytest

from database import initialize_database
from pots import POT_TREND
from tests.test_live_sell_dust import PRICE, BinanceUSLike, make_trader, signal
from tests.test_pots import live_pots

FEE_BTC = 1.9e-07


def binance_reply_without_fee(exchange):
    """Buy like Binance.US: BTC fee taken, but the order reply leaves it empty."""
    def buy(symbol, amount, params=None):
        exchange.usd -= amount * PRICE
        exchange.btc += amount - FEE_BTC
        exchange._last = {"id": "o-1", "status": "closed", "side": "buy", "amount": amount,
                          "filled": amount, "remaining": 0.0, "average": PRICE,
                          "fee": {"currency": None, "cost": None, "rate": None},
                          "fees": [{"currency": None, "cost": None, "rate": None}]}
        return exchange._last
    exchange.create_market_buy_order = MagicMock(side_effect=buy)
    exchange.fetch_my_trades = MagicMock(return_value=[
        {"order": "o-1", "fee": {"cost": FEE_BTC, "currency": "BTC"}},
    ])


def test_buy_is_booked_with_the_fee_from_its_fills():
    exchange = BinanceUSLike()
    binance_reply_without_fee(exchange)
    trader = make_trader(exchange)
    trade = trader.handle_signal(signal("bullish"))
    assert trade is not None
    pos = trader.open_position
    assert pos is not None
    assert pos.amount == pytest.approx(trade.amount - FEE_BTC)  # what we can sell later
    assert trade.fee == pytest.approx(FEE_BTC * PRICE)            # shown in dollars
    exchange.fetch_my_trades.assert_called_once()


def test_unknown_fee_falls_back_to_an_estimate():
    exchange = BinanceUSLike()
    binance_reply_without_fee(exchange)
    exchange.fetch_my_trades = MagicMock(side_effect=Exception("down"))
    trader = make_trader(exchange)
    trade = trader.handle_signal(signal("bullish"))
    assert trade is not None and trader.open_position is not None


def test_pot_books_the_buy_and_matches_the_exchange():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm, exchange = live_pots(db)
    binance_reply_without_fee(exchange)
    pot = pots.get(POT_TREND)
    cash = pot.balances()["USDT"]
    pot.trader.handle_signal(signal("bullish"))
    assert pot.holding
    b = pot.balances()
    assert b["BASE"] == pytest.approx(pot.trader.open_position.amount)
    assert b["USDT"] < cash
    assert pots.reconcile() == []


def test_adopt_a_buy_that_filled_but_was_never_booked():
    exchange = BinanceUSLike()
    binance_reply_without_fee(exchange)
    trader = make_trader(exchange)
    order = exchange.create_market_buy_order("BTC/USD", 0.001)  # filled, bot never saw it
    exchange.fetch_order = MagicMock(return_value=order)
    trade = trader.adopt_filled_buy("o-1", signal("bullish"))
    assert trade is not None and trade.price == PRICE
    assert trader.open_position.amount == pytest.approx(0.001 - FEE_BTC)
