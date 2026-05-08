"""
Batch C behavior tests for LiveTrader.

Covers four invariants that did not previously exist in the test suite:

1. Retry helper retries transient ccxt errors and re-raises permanent ones
   without retrying.
2. ``execute_market_buy`` polls the order to a terminal state and uses the
   *final* fill data (not the initial response).  Partial fills are
   accepted as the actual position size, never silently rounded up.
3. Open positions persist to the in-memory DB and survive a "restart"
   (i.e. a fresh ``LiveTrader`` constructed against the same DB recovers
   the position with the correct stop-loss / take-profit / trailing-stop).
4. ``sync_positions`` refuses to auto-adopt base-currency balance that
   the bot did not put on the exchange itself.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

import ccxt

from config import BotConfig
from database import initialize_database
import live_trader as lt
from live_trader import (
    LiveTrader,
    TradingMode,
    _retry_call,
    _wait_for_order_terminal,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

class _PollableExchange:
    """A minimal CCXT-shaped exchange that lets each test script the
    sequence of statuses returned by ``fetch_order``."""

    def __init__(
        self,
        *,
        ticker_last: float = 50_000.0,
        ticker_ask: float = 50_001.0,
        ticker_bid: float = 49_999.0,
        balances: dict | None = None,
    ):
        self.markets = {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "base": "BTC",
                "quote": "USDT",
                "limits": {
                    "amount": {"min": 0.0001, "max": 1000.0},
                    "cost": {"min": 10.0, "max": 1_000_000.0},
                },
                "precision": {"amount": 8, "price": 2},
            }
        }
        self._ticker = {
            "last": ticker_last,
            "ask": ticker_ask,
            "bid": ticker_bid,
        }
        self._balance = balances or {
            "USDT": {"free": 1_000.0, "total": 1_000.0},
            "BTC": {"free": 0.0, "total": 0.0},
        }
        self.create_market_buy_order = MagicMock()
        self.create_market_sell_order = MagicMock()
        self.create_order = MagicMock(
            return_value={"id": "stub-stop", "status": "open", "type": "STOP_LOSS_LIMIT"},
        )
        self.cancel_order = MagicMock()
        self.fetch_order = MagicMock()
        self.fetch_my_trades = MagicMock(return_value=[])

    def load_markets(self):
        return self.markets

    def fetch_balance(self):
        return self._balance

    def fetch_ticker(self, _symbol):
        return self._ticker


def _make_config() -> BotConfig:
    return BotConfig(
        binance_api_key="",
        binance_api_secret="",
        symbol="BTC/USDT",
        timeframe="1h",
        initial_usdt=1_000.0,
        order_pct=0.25,
        fee_rate=0.001,
        slippage=0.0005,
        stop_loss_pct=0.025,
        take_profit_pct=0.04,
        trailing_stop_pct=0.015,
        use_trailing_stop=True,
        max_trades_per_day=10,
        max_portfolio_drawdown=0.10,
        max_single_trade_usd=10_000.0,
        require_trade_confirmation=False,
        confirmation_threshold_usd=10_000.0,
        api_retry_attempts=3,
        api_retry_delay_seconds=0.0,            # speed up tests
        order_poll_timeout_seconds=2.0,
        order_poll_interval_seconds=0.0,        # poll as fast as possible
    )


# ---------------------------------------------------------------------------
# 1. Retry helper
# ---------------------------------------------------------------------------

class RetryCallTests(unittest.TestCase):
    def test_retries_transient_errors_then_succeeds(self):
        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ccxt.NetworkError("temporary")
            return "ok"

        result = _retry_call(flaky, attempts=3, delay=0.0, description="t")
        self.assertEqual(result, "ok")
        self.assertEqual(attempts["n"], 3)

    def test_gives_up_after_attempts_and_reraises(self):
        def always_timeout():
            raise ccxt.RequestTimeout("nope")

        with self.assertRaises(ccxt.RequestTimeout):
            _retry_call(always_timeout, attempts=2, delay=0.0, description="t")

    def test_permanent_errors_are_not_retried(self):
        attempts = {"n": 0}

        def insufficient():
            attempts["n"] += 1
            raise ccxt.InsufficientFunds("not enough")

        with self.assertRaises(ccxt.InsufficientFunds):
            _retry_call(insufficient, attempts=5, delay=0.0, description="t")
        self.assertEqual(
            attempts["n"], 1,
            msg="permanent errors must not be retried",
        )


# ---------------------------------------------------------------------------
# 2. Order polling / partial fills
# ---------------------------------------------------------------------------

class OrderPollingTests(unittest.TestCase):
    def test_polls_until_status_is_terminal(self):
        exchange = _PollableExchange()
        exchange.fetch_order.side_effect = [
            {"id": "1", "status": "open", "filled": 0.0, "amount": 0.01},
            {"id": "1", "status": "open", "filled": 0.005, "amount": 0.01},
            {"id": "1", "status": "closed", "filled": 0.01, "amount": 0.01,
             "average": 50_010.0},
        ]
        result = _wait_for_order_terminal(
            exchange, "1", "BTC/USDT",
            timeout_seconds=5.0,
            poll_interval=0.0,
            retry_attempts=2,
            retry_delay=0.0,
        )
        self.assertEqual(result["status"], "closed")
        self.assertEqual(exchange.fetch_order.call_count, 3)

    def test_returns_latest_snapshot_on_timeout(self):
        exchange = _PollableExchange()
        exchange.fetch_order.return_value = {
            "id": "1", "status": "open", "filled": 0.0, "amount": 0.01,
        }
        result = _wait_for_order_terminal(
            exchange, "1", "BTC/USDT",
            timeout_seconds=0.0,
            poll_interval=0.0,
            retry_attempts=1,
            retry_delay=0.0,
        )
        self.assertEqual(result["status"], "open")


class PartialFillTests(unittest.TestCase):
    def setUp(self):
        self.exchange = _PollableExchange()
        self.config = _make_config()
        self.trader = LiveTrader(self.exchange, self.config, mode=TradingMode.LIVE)
        self.trader.usdt_balance = 1_000.0

    def test_buy_uses_polled_filled_amount(self):
        """Initial response says half-filled; polled response shows full
        fill.  The position must reflect the *polled* amount."""
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-1", "status": "open", "amount": 0.01, "filled": 0.005,
            "average": 50_005.0, "fee": {"cost": 0.5, "currency": "USDT"},
        }
        # After polling, exchange reports the fill completed.
        self.exchange.fetch_order.side_effect = [
            {"id": "OID-1", "status": "closed", "amount": 0.01,
             "filled": 0.01, "average": 50_005.0,
             "fee": {"cost": 1.0, "currency": "USDT"}},
        ]
        # Balance after fill
        self.exchange._balance = {
            "USDT": {"free": 499.0, "total": 499.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }

        trade = self.trader.execute_market_buy(0.01)

        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.amount, 0.01, places=8)
        self.assertIsNotNone(self.trader.open_position)
        self.assertAlmostEqual(self.trader.open_position.amount, 0.01, places=8)

    def test_buy_reflects_partial_fill_when_order_expires(self):
        """Some venues will return ``status='expired'`` after a partial
        market fill (rare but real).  The bot must record the actual
        filled amount, not the requested amount."""
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-2", "status": "open", "amount": 0.01, "filled": 0.0,
        }
        self.exchange.fetch_order.side_effect = [
            {"id": "OID-2", "status": "expired", "amount": 0.01,
             "filled": 0.004, "average": 50_010.0,
             "fee": {"cost": 0.4, "currency": "USDT"}},
        ]
        self.exchange._balance = {
            "USDT": {"free": 800.0, "total": 800.0},
            "BTC": {"free": 0.004, "total": 0.004},
        }

        trade = self.trader.execute_market_buy(0.01)

        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.amount, 0.004, places=8)
        self.assertIsNotNone(self.trader.open_position)
        self.assertAlmostEqual(self.trader.open_position.amount, 0.004, places=8)

    def test_buy_returns_none_when_no_fills(self):
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-3", "status": "open", "amount": 0.01, "filled": 0.0,
        }
        self.exchange.fetch_order.side_effect = [
            {"id": "OID-3", "status": "expired", "amount": 0.01,
             "filled": 0.0},
        ]
        trade = self.trader.execute_market_buy(0.01)
        self.assertIsNone(trade)
        self.assertIsNone(self.trader.open_position)

    def test_buy_propagates_permanent_error_as_clean_failure(self):
        self.exchange.create_market_buy_order.side_effect = ccxt.InsufficientFunds(
            "not enough USDT"
        )
        trade = self.trader.execute_market_buy(0.01)
        self.assertIsNone(trade)
        self.assertIsNone(self.trader.open_position)


# ---------------------------------------------------------------------------
# 3. DB persistence + restore on restart
# ---------------------------------------------------------------------------

class DatabasePersistenceTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh in-memory SQLite DB.
        self.db = initialize_database("sqlite:///:memory:")
        self.exchange = _PollableExchange()
        self.config = _make_config()

    def _make_trader(self) -> LiveTrader:
        trader = LiveTrader(
            self.exchange, self.config,
            mode=TradingMode.LIVE,
            db_manager=self.db,
        )
        trader.usdt_balance = 1_000.0
        return trader

    def _open_simple_position(self, trader: LiveTrader, fill_price: float = 50_000.0):
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-A", "status": "closed",
            "amount": 0.01, "filled": 0.01, "average": fill_price,
            "fee": {"cost": fill_price * 0.01 * 0.001, "currency": "USDT"},
        }
        self.exchange.fetch_order.side_effect = [
            {"id": "OID-A", "status": "closed",
             "amount": 0.01, "filled": 0.01, "average": fill_price,
             "fee": {"cost": fill_price * 0.01 * 0.001, "currency": "USDT"}},
        ]
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        trade = trader.execute_market_buy(0.01)
        self.assertIsNotNone(trade)

    def test_open_position_is_persisted(self):
        trader = self._make_trader()
        self._open_simple_position(trader)

        rows = self.db.get_open_positions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].side, "long")
        self.assertAlmostEqual(rows[0].amount, 0.01, places=8)
        self.assertEqual(rows[0].is_open, True)

    def test_position_survives_restart(self):
        # Open in trader A.
        trader_a = self._make_trader()
        self._open_simple_position(trader_a, fill_price=50_000.0)
        original_sl = trader_a.open_position.stop_loss
        original_tp = trader_a.open_position.take_profit

        # Simulate a process restart: brand new LiveTrader sharing the DB.
        # Have it see the same exchange balance.
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        trader_b = self._make_trader()
        # Restoration happens in __init__; sync_positions also re-uses it.
        restored = trader_b.sync_positions()

        self.assertIsNotNone(restored)
        self.assertAlmostEqual(restored.amount, 0.01, places=8)
        self.assertAlmostEqual(restored.stop_loss, original_sl, places=4)
        self.assertAlmostEqual(restored.take_profit, original_tp, places=4)

    def test_trailing_stop_ratchet_is_persisted(self):
        trader = self._make_trader()
        self._open_simple_position(trader, fill_price=50_000.0)
        initial_trailing = trader.open_position.trailing_stop

        # Pick a price that is above the entry (so the trailing stop
        # ratchets upward) but below the take-profit (so the position is
        # not closed).  Entry = $50_000, TP = +4% = $52_000, so $51_000
        # gives us a +2% move in safe territory.
        trader.update_position(51_000.0)
        self.assertIsNotNone(
            trader.open_position,
            "update_position should not close the trade at +2%",
        )

        new_trailing = trader.open_position.trailing_stop
        self.assertGreater(new_trailing, initial_trailing)

        rows = self.db.get_open_positions()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].trailing_stop, new_trailing, places=4)
        self.assertAlmostEqual(rows[0].highest_price, 51_000.0, places=4)


# ---------------------------------------------------------------------------
# 4. Orphan-balance guard
# ---------------------------------------------------------------------------

class OrphanBalanceTests(unittest.TestCase):
    def setUp(self):
        self.db = initialize_database("sqlite:///:memory:")
        self.config = _make_config()

    def test_sync_does_not_adopt_unrelated_btc(self):
        """If the exchange holds BTC but the bot has no DB record for it,
        ``sync_positions`` must return None and not start managing it."""
        exchange = _PollableExchange(balances={
            # Pre-existing BTC, not put there by the bot.
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.05, "total": 0.05},
        })
        trader = LiveTrader(
            exchange, self.config,
            mode=TradingMode.LIVE,
            db_manager=self.db,
        )

        result = trader.sync_positions()
        self.assertIsNone(result)
        self.assertIsNone(trader.open_position)
        self.assertEqual(len(self.db.get_open_positions()), 0)

    def test_sync_restores_bot_managed_btc_only(self):
        """When the DB has an open row, sync_positions must restore it
        regardless of any extra BTC the account happens to hold."""
        exchange = _PollableExchange(balances={
            "USDT": {"free": 1_000.0, "total": 1_000.0},
            "BTC": {"free": 0.0, "total": 0.0},
        })

        # Open a position via trader A (writes a DB row).
        trader_a = LiveTrader(exchange, self.config,
                              mode=TradingMode.LIVE, db_manager=self.db)
        trader_a.usdt_balance = 1_000.0
        exchange.create_market_buy_order.return_value = {
            "id": "OID-Z", "status": "closed",
            "amount": 0.01, "filled": 0.01, "average": 50_000.0,
            "fee": {"cost": 0.5, "currency": "USDT"},
        }
        exchange.fetch_order.side_effect = [
            {"id": "OID-Z", "status": "closed",
             "amount": 0.01, "filled": 0.01, "average": 50_000.0,
             "fee": {"cost": 0.5, "currency": "USDT"}},
        ]
        exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        trader_a.execute_market_buy(0.01)

        # Now imagine the user manually deposited an extra 0.5 BTC.
        exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.51, "total": 0.51},
        }

        trader_b = LiveTrader(exchange, self.config,
                              mode=TradingMode.LIVE, db_manager=self.db)
        restored = trader_b.sync_positions()

        # Restored amount comes from the DB (0.01), not from the exchange (0.51).
        self.assertIsNotNone(restored)
        self.assertAlmostEqual(restored.amount, 0.01, places=8)


if __name__ == "__main__":
    unittest.main()
