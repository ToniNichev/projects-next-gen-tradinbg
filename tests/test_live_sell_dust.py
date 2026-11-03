"""A sell that leaves only dust closes the position.

Binance.US takes the buy fee in BTC and sells round down to 5 decimals, so
selling "the whole position" leaves a few millionths of a BTC behind. That
leftover can't be sold (below the minimum order), so it must not keep the
position open - before the fix the bot never bought again.
"""

import ccxt
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from live_trader import LiveTrader, TradingMode
from strategies.base_strategy import StrategySignal
from tests.test_live_trader_batch_c import _make_config

PRICE = 77_000.0
FEE_RATE = 0.001


class BinanceUSLike:
    """BTC/USD with Binance.US's rules: 5-decimal amounts, $1 minimum,
    buy fee charged in BTC, sell fee in USD."""

    def __init__(self, usd=100.0):
        self.markets = {"BTC/USD": {
            "symbol": "BTC/USD",
            "limits": {"amount": {"min": 1e-05, "max": 9000.0}, "cost": {"min": 1.0, "max": None}},
            "precision": {"amount": 5, "price": 2},
        }}
        self.usd, self.btc = usd, 0.0
        self.create_order = MagicMock(return_value={"id": "stop-1", "status": "open"})
        self.cancel_order = MagicMock()
        self.create_market_buy_order = MagicMock(side_effect=self._buy)
        self.create_market_sell_order = MagicMock(side_effect=self._sell)
        self.fetch_order = MagicMock(side_effect=self._fetch)
        self._last = None
        self._n = 0
        self._by_client_id = {}
        self._orders = {}

    def _fetch(self, oid, sym=None, params=None):
        # Like Binance: look up by the client order id when one is given
        cid = (params or {}).get("origClientOrderId")
        if cid is not None:
            if cid not in self._by_client_id:
                raise ccxt.OrderNotFound(f"Order does not exist ({cid})")
            return self._by_client_id[cid]
        if oid in self._orders:
            return self._orders[oid]
        if self._last and self._last.get("id") == oid:  # set directly by a test
            return self._last
        # Any other id (e.g. the resting stop order): still waiting
        return {"id": oid, "status": "open", "filled": 0.0}

    def load_markets(self):
        return self.markets

    def fetch_ticker(self, _symbol):
        return {"last": PRICE, "ask": PRICE, "bid": PRICE}

    def fetch_balance(self):
        return {"USD": {"free": self.usd, "total": self.usd},
                "BTC": {"free": self.btc, "total": self.btc}}

    def _order(self, side, amount, fee, params=None):
        self._n += 1
        self._last = {"id": f"{side}-{self._n}", "status": "closed", "side": side,
                      "amount": amount, "filled": amount, "remaining": 0.0,
                      "average": PRICE, "fee": fee}
        self._orders[self._last["id"]] = self._last
        cid = (params or {}).get("newClientOrderId")
        if cid:
            self._by_client_id[cid] = self._last
        return self._last

    def _buy(self, symbol, amount, params=None):
        fee_btc = amount * FEE_RATE
        self.usd -= amount * PRICE
        self.btc += amount - fee_btc
        return self._order("buy", amount, {"cost": fee_btc, "currency": "BTC"}, params)

    def _sell(self, symbol, amount, params=None):
        assert amount <= self.btc + 1e-12, "sold more BTC than the account has"
        fee_usd = amount * PRICE * FEE_RATE
        self.btc -= amount
        self.usd += amount * PRICE - fee_usd
        return self._order("sell", amount, {"cost": fee_usd, "currency": "USD"}, params)


def signal(direction):
    return StrategySignal(
        direction=direction, price=PRICE, confidence=1.0,
        timestamp=datetime.now(timezone.utc), strategy_name="Trend_Hold",
        stop_loss=PRICE * 1e-6, take_profit=PRICE * 100, position_size=0.99,
    )


def make_trader(exchange):
    config = _make_config()
    config.symbol = "BTC/USD"
    config.use_trailing_stop = False
    config.max_position_size = 0.99
    config.max_single_trade_usd = 0.0
    config.require_trade_confirmation = False
    trader = LiveTrader(exchange, config, mode=TradingMode.LIVE, db_manager=None)
    trader.sync_balances()
    return trader


def test_sell_leaving_dust_closes_the_position_and_the_bot_can_buy_again():
    exchange = BinanceUSLike()
    trader = make_trader(exchange)

    assert trader.handle_signal(signal("bullish")).side == "buy"
    held = trader.open_position.amount
    assert trader.round_amount(held) < held  # the sell can't take it all

    sell = trader.handle_signal(signal("bearish"))
    assert sell is not None and sell.side == "sell"
    assert trader.open_position is None  # dust doesn't keep it open
    assert 0 < exchange.btc < 1e-05      # the dust really is left behind

    again = trader.handle_signal(signal("bullish"))
    assert again is not None and again.side == "buy"


def test_a_real_partial_fill_keeps_the_rest_open():
    exchange = BinanceUSLike()
    trader = make_trader(exchange)
    trader.handle_signal(signal("bullish"))
    held = trader.open_position.amount

    # The exchange fills only half of the sell
    def half_sell(symbol, amount, params=None):
        order = BinanceUSLike._sell(exchange, symbol, round(amount / 2, 5))
        order["amount"], order["remaining"] = amount, amount - order["filled"]
        return order
    exchange.create_market_sell_order.side_effect = half_sell

    trader.handle_signal(signal("bearish"))
    assert trader.open_position is not None
    assert trader.open_position.amount == pytest.approx(held / 2, abs=2e-05)
