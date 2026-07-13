"""
Tests for walk-forward (end_date) and config_overrides support added to the
backtest UI/API path.

Covers two things that used to only be reachable by calling
backtest.run_backtest() directly in a script:
  1. app/api/routes.py's /api/backtest/run now accepts an optional end_date
     and validates its format before starting the background run.
  2. BacktestManager.run_backtest() forwards end_date through to
     backtest.run_backtest() and surfaces the resulting window in the
     result's "parameters" (which the dashboard already renders under
     "Custom Parameters" with no further UI plumbing needed).

config_overrides itself was already wired end-to-end before this change;
only the frontend never sent it. That's covered indirectly here by
asserting it reaches backtest.run_backtest() unmodified (aside from the
skip_llm merge that already existed).
"""

from __future__ import annotations

import os

os.environ.setdefault("DASHBOARD_AUTH_ENABLED", "false")

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import auth as _auth_module  # noqa: F401  (force import order, see test_manual_trade_api.py)

from app import create_app, init_services
from app.services.backtest_manager import BacktestManager
from app.core.state import ApplicationState
from config import BotConfig
from paper_trader import PaperTrader


def _canned_result() -> dict:
    return {
        "trades": 12,
        "final_value": 1010.0,
        "pnl": 10.0,
        "pnl_pct": 1.0,
        "buy_hold_pct": 2.0,
        "max_drawdown_pct": 1.5,
        "sharpe_ratio": 0.8,
        "chart_data": {"candles": [], "trades": [], "portfolio_values": []},
    }


class BacktestManagerWalkForwardTests(unittest.TestCase):
    """Direct (non-HTTP) coverage of the end_date / config_overrides wiring."""

    def setUp(self):
        self.config = BotConfig(binance_api_key="", binance_api_secret="")
        self.manager = BacktestManager(ApplicationState(), self.config)

    def test_end_date_forwarded_and_window_surfaced_in_parameters(self):
        end_date = datetime(2026, 6, 9, tzinfo=timezone.utc)
        overrides = {"strategy_rsi_bb_enabled": True, "strategy_macd_enabled": True}

        with patch("backtest.run_backtest", return_value=_canned_result()) as mock_run:
            result = self.manager.run_backtest(
                days_back=30,
                config_overrides=overrides,
                end_date=end_date,
            )

        self.assertTrue(result["success"], result)
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args.kwargs
        self.assertEqual(call_kwargs["end_date"], end_date)
        self.assertEqual(call_kwargs["config_overrides"]["strategy_rsi_bb_enabled"], True)
        self.assertEqual(call_kwargs["config_overrides"]["strategy_macd_enabled"], True)

        params = result["data"]["parameters"]
        self.assertEqual(params["window_start"], "2026-05-10")
        self.assertEqual(params["window_end"], "2026-06-09")

    def test_no_end_date_omits_window_from_parameters(self):
        """Plain 'last N days' runs (the pre-existing behavior) shouldn't
        get a window echoed back — there isn't a meaningful fixed one."""
        with patch("backtest.run_backtest", return_value=_canned_result()) as mock_run:
            result = self.manager.run_backtest(days_back=30)

        self.assertTrue(result["success"], result)
        self.assertIsNone(mock_run.call_args.kwargs["end_date"])
        self.assertNotIn("window_start", result["data"]["parameters"])


class BacktestRunRouteTests(unittest.TestCase):
    """HTTP-level coverage of end_date validation in /api/backtest/run."""

    def setUp(self):
        from auth import get_auth_config
        get_auth_config().enabled = False

        self.config = BotConfig(
            binance_api_key="",
            binance_api_secret="",
            dashboard_auth_enabled=False,
            enable_rate_limiting=False,
        )
        self.trader = PaperTrader(
            initial_usdt=self.config.initial_usdt,
            fee_rate=self.config.fee_rate,
            slippage=self.config.slippage,
            log_path="",
            enable_database=False,
            enable_csv_logging=False,
        )

        self.app = create_app()
        self.app.config.update(TESTING=True)
        import threading
        init_services(self.trader, threading.Lock(), None, None, self.config)
        self.client = self.app.test_client()

    def test_invalid_end_date_rejected_before_running(self):
        resp = self.client.post(
            "/api/backtest/run",
            json={"days_back": 30, "end_date": "not-a-date"},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("end_date", data["error"])

    def test_valid_end_date_accepted_and_starts_run(self):
        with patch(
            "app.services.backtest_manager.BacktestManager.run_backtest",
            return_value={"success": True, "data": {}},
        ) as mock_run:
            resp = self.client.post(
                "/api/backtest/run",
                json={"days_back": 30, "end_date": "2026-06-09"},
            )
        self.assertEqual(resp.status_code, 202, resp.get_json())
        # Background thread — give it a moment to invoke the (mocked) manager.
        import time
        for _ in range(20):
            if mock_run.called:
                break
            time.sleep(0.01)
        self.assertTrue(mock_run.called)
        call_kwargs = mock_run.call_args.kwargs
        self.assertEqual(call_kwargs["end_date"], datetime(2026, 6, 9, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
