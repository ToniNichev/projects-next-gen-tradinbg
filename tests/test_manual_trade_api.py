"""
Regression tests for the manual buy/sell endpoints in app/api/trading.py.

These tests cover the bug that originally motivated Batch B: the old
endpoints called PaperTrader-only private methods (``_buy``,
``_close_position``) which do not exist on LiveTrader, so manual trading
crashed with AttributeError as soon as the bot was switched to live mode.

The new endpoints route everything through the unified public API
(``execute_market_buy`` / ``execute_market_sell``) which both traders
implement with consistent base-currency semantics.
"""

from __future__ import annotations

import os

# Disable dashboard auth before any auth-related module is imported. ``auth``
# reads ``DASHBOARD_AUTH_ENABLED`` at import time and caches the answer in a
# module-level singleton, so we have to set the env var before the first
# ``import auth`` happens (transitively via ``app``).
os.environ.setdefault("DASHBOARD_AUTH_ENABLED", "false")

import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import auth as _auth_module  # noqa: F401  (force import order)

from app import create_app, init_services
from app.core.state import get_app_state
from config import BotConfig
from paper_trader import PaperTrader
from strategies.base_strategy import StrategySignal


class _FakeTicker(dict):
    pass


class _FakeExchange:
    """Minimal CCXT-shaped exchange returning a fixed price."""

    def __init__(self, last: float = 50_000.0):
        self.last = last

    def fetch_ticker(self, symbol: str):
        return _FakeTicker(last=self.last, bid=self.last - 1, ask=self.last + 1)


def _make_config() -> BotConfig:
    cfg = BotConfig(
        binance_api_key="",
        binance_api_secret="",
        symbol="BTC/USDT",
        timeframe="1h",
        initial_usdt=1_000.0,
        order_pct=0.25,
        fee_rate=0.00075,
        slippage=0.0005,
        min_position_size=0.10,
        max_position_size=0.35,
        stop_loss_pct=0.025,
        take_profit_pct=0.04,
        trailing_stop_pct=0.015,
        use_trailing_stop=True,
        use_atr_stops=False,
        atr_stop_multiplier=2.5,
        dashboard_auth_enabled=False,  # unauthenticated for tests
        enable_rate_limiting=False,
    )
    return cfg


class ManualTradeAPITests(unittest.TestCase):
    """End-to-end coverage of /api/manual/buy and /api/manual/sell."""

    def setUp(self):
        # Force-disable auth for this test class regardless of the imported
        # singleton's earlier state (it is cached after first import).
        from auth import get_auth_config
        get_auth_config().enabled = False

        self.config = _make_config()
        self.exchange = _FakeExchange(last=50_000.0)
        self.trader = PaperTrader(
            initial_usdt=self.config.initial_usdt,
            fee_rate=self.config.fee_rate,
            slippage=self.config.slippage,
            log_path="",            # disable CSV
            enable_database=False,  # disable DB
            enable_csv_logging=False,
            use_trailing_stop=self.config.use_trailing_stop,
            trailing_stop_pct=self.config.trailing_stop_pct,
        )
        self.trader_lock = threading.Lock()

        self.app = create_app()
        self.app.config.update(TESTING=True)

        # init_services would normally start the live server — replicate the
        # in-process wiring without spawning a thread.
        app_state = init_services(
            self.trader,
            self.trader_lock,
            self.exchange,
            None,   # strategy_manager
            self.config,
        )
        self.app_state = app_state

        self.client = self.app.test_client()

    # ------------------------------------------------------------------
    # /api/manual/buy
    # ------------------------------------------------------------------

    def _patched_config(self):
        # ``BotConfig.load`` is imported lazily inside the route, so patching
        # the symbol on the ``config`` module (the real source) is reliable
        # while ``app.api.trading.BotConfig`` is not an attribute path.
        return patch("config.BotConfig.load", return_value=self.config)

    def test_buy_with_position_size_opens_long(self):
        with self._patched_config():
            resp = self.client.post(
                "/api/manual/buy",
                json={"position_size": 0.25},
            )
        self.assertEqual(resp.status_code, 200, resp.get_json())
        data = resp.get_json()
        self.assertTrue(data["success"])
        # 25% of $1000 = $250 notional → ~0.005 BTC at $50k
        self.assertAlmostEqual(data["trade"]["amount"], 0.25 * 1000 / 50_000, places=4)
        # Position now open
        self.assertIsNotNone(self.trader.open_position)
        self.assertEqual(self.trader.open_position.side, "long")

    def test_buy_rejects_oversize_position(self):
        with self._patched_config():
            resp = self.client.post(
                "/api/manual/buy",
                json={"position_size": 0.99},
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("too large", resp.get_json()["error"])

    def test_buy_rejects_undersize_position(self):
        with self._patched_config():
            resp = self.client.post(
                "/api/manual/buy",
                json={"position_size": 0.01},
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("too small", resp.get_json()["error"])

    def test_buy_with_zero_balance_returns_400(self):
        self.trader.usdt_balance = 0.0
        with self._patched_config():
            resp = self.client.post(
                "/api/manual/buy",
                json={"position_size": 0.25},
            )
        self.assertEqual(resp.status_code, 400)

    # ------------------------------------------------------------------
    # /api/manual/sell
    # ------------------------------------------------------------------

    def test_sell_without_position_returns_400(self):
        with self._patched_config():
            resp = self.client.post("/api/manual/sell", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No open long position", resp.get_json()["error"])

    def test_sell_closes_open_long(self):
        # Open a position first.
        with self._patched_config():
            self.client.post("/api/manual/buy", json={"position_size": 0.25})
            self.assertIsNotNone(self.trader.open_position)

            resp = self.client.post("/api/manual/sell", json={})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["trade"]["side"], "sell")
        self.assertEqual(data["trade"]["exit_reason"], "manual")
        self.assertIsNone(self.trader.open_position)


class PublicTraderAPISymmetryTests(unittest.TestCase):
    """``execute_market_buy(amount, signal)`` must mean the same thing on
    both traders so route handlers can be trader-agnostic."""

    def setUp(self):
        self.config = _make_config()
        self.trader = PaperTrader(
            initial_usdt=self.config.initial_usdt,
            fee_rate=self.config.fee_rate,
            slippage=self.config.slippage,
            log_path="",
            enable_database=False,
            enable_csv_logging=False,
            use_trailing_stop=self.config.use_trailing_stop,
            trailing_stop_pct=self.config.trailing_stop_pct,
        )

    def _make_signal(self, price: float, direction: str = "bullish") -> StrategySignal:
        return StrategySignal(
            direction=direction,
            price=price,
            confidence=1.0,
            timestamp=datetime.now(timezone.utc),
            strategy_name="test",
            stop_loss=price * 0.975 if direction == "bullish" else price * 1.025,
            take_profit=price * 1.04 if direction == "bullish" else price * 0.96,
            position_size=0.25,
        )

    def test_execute_market_buy_amount_is_base_currency(self):
        """Asking for 0.005 BTC should buy approximately 0.005 BTC."""
        signal = self._make_signal(price=50_000.0)
        trade = self.trader.execute_market_buy(amount=0.005, signal=signal)
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade.amount, 0.005, places=8)

    def test_execute_market_buy_rejects_over_balance(self):
        """If the requested base amount would over-spend USDT it must fail
        cleanly (no negative balance)."""
        signal = self._make_signal(price=50_000.0)
        # 1 BTC at $50k = $50,000, but balance is only $1,000.
        trade = self.trader.execute_market_buy(amount=1.0, signal=signal)
        self.assertIsNone(trade)
        self.assertEqual(self.trader.usdt_balance, 1_000.0)
        self.assertEqual(self.trader.base_balance, 0.0)

    def test_execute_market_sell_rejects_partial(self):
        """Paper trader does not support partial sells: passing an amount
        that doesn't match the open position must be rejected, never
        silently truncated."""
        signal = self._make_signal(price=50_000.0)
        self.trader.execute_market_buy(amount=0.005, signal=signal)
        self.assertIsNotNone(self.trader.open_position)

        # Try to sell half — should be rejected.
        trade = self.trader.execute_market_sell(
            amount=0.0025,
            signal=self._make_signal(price=51_000.0, direction="bearish"),
            exit_reason="manual",
        )
        self.assertIsNone(trade)
        self.assertIsNotNone(self.trader.open_position)

        # Selling the full amount succeeds.
        full_amount = self.trader.open_position.amount
        trade = self.trader.execute_market_sell(
            amount=full_amount,
            signal=self._make_signal(price=51_000.0, direction="bearish"),
            exit_reason="manual",
        )
        self.assertIsNotNone(trade)
        self.assertIsNone(self.trader.open_position)


if __name__ == "__main__":
    unittest.main()
