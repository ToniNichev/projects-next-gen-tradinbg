"""
Batch D: exchange protective stops, startup re-arm after DB restore.

Uses the same lightweight CCXT-shaped exchange as ``test_live_trader_batch_c``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from live_trader import LiveTrader, TradingMode

from tests.test_live_trader_batch_c import _PollableExchange, _make_config


def _exchange_with_stops() -> _PollableExchange:
    ex = _PollableExchange()
    ex.create_order = MagicMock(
        return_value={"id": "STOP-1", "status": "open", "type": "STOP_LOSS_LIMIT"}
    )
    ex.cancel_order = MagicMock()
    return ex


class ExchangeProtectiveStopTests(unittest.TestCase):
    def setUp(self):
        self.exchange = _exchange_with_stops()
        self.config = _make_config()
        self.config.exchange_stop_loss_enabled = True
        self.config.exchange_stop_update_on_trailing = True
        self.trader = LiveTrader(self.exchange, self.config, mode=TradingMode.LIVE)
        self.trader.usdt_balance = 1_000.0

    def test_buy_places_stop_loss_limit(self):
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-B", "status": "closed",
            "amount": 0.01, "filled": 0.01, "average": 50_000.0,
            "fee": {"cost": 0.5, "currency": "USDT"},
        }
        self.exchange.fetch_order.side_effect = [
            {
                "id": "OID-B", "status": "closed",
                "amount": 0.01, "filled": 0.01, "average": 50_000.0,
                "fee": {"cost": 0.5, "currency": "USDT"},
            },
        ]
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }

        trade = self.trader.execute_market_buy(0.01)
        self.assertIsNotNone(trade)
        self.assertTrue(self.exchange.create_order.called)
        sym, otype, side, *_rest = self.exchange.create_order.call_args[0]
        self.assertEqual(sym, "BTC/USDT")
        self.assertEqual(otype, "STOP_LOSS_LIMIT")
        self.assertEqual(side, "sell")
        self.assertEqual(
            self.trader.open_position.exchange_stop_order_id,
            "STOP-1",
        )

    def test_sell_cancels_protective_stop_before_market(self):
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-C", "status": "closed",
            "amount": 0.01, "filled": 0.01, "average": 50_000.0,
            "fee": {"cost": 0.5, "currency": "USDT"},
        }
        self.exchange.fetch_order.side_effect = [
            {
                "id": "OID-C", "status": "closed",
                "amount": 0.01, "filled": 0.01, "average": 50_000.0,
                "fee": {"cost": 0.5, "currency": "USDT"},
            },
            {
                "id": "OID-SELL", "status": "closed",
                "amount": 0.01, "filled": 0.01, "average": 50_000.0,
                "fee": {"cost": 0.5, "currency": "USDT"},
            },
        ]
        self.exchange.create_market_sell_order.return_value = {
            "id": "OID-SELL", "status": "open",
            "amount": 0.01, "filled": 0.0,
        }
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }

        self.trader.execute_market_buy(0.01)
        self.assertEqual(
            self.trader.open_position.exchange_stop_order_id,
            "STOP-1",
        )

        self.trader.execute_market_sell(0.01, exit_reason="signal")

        self.assertTrue(self.exchange.cancel_order.called)
        self.assertTrue(self.exchange.create_market_sell_order.called)


class RestoreRearmsStopTests(unittest.TestCase):
    def setUp(self):
        self.db = initialize_database("sqlite:///:memory:")
        self.exchange = _exchange_with_stops()
        self.config = _make_config()
        self.config.exchange_stop_loss_enabled = True

    def test_restore_calls_sync_for_protective_stop(self):
        trader_a = LiveTrader(
            self.exchange, self.config,
            mode=TradingMode.LIVE, db_manager=self.db,
        )
        trader_a.usdt_balance = 1_000.0
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-R", "status": "closed",
            "amount": 0.01, "filled": 0.01, "average": 50_000.0,
            "fee": {"cost": 0.5, "currency": "USDT"},
        }
        self.exchange.fetch_order.side_effect = [
            {
                "id": "OID-R", "status": "closed",
                "amount": 0.01, "filled": 0.01, "average": 50_000.0,
                "fee": {"cost": 0.5, "currency": "USDT"},
            },
        ]
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        trader_a.execute_market_buy(0.01)

        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        create_before_restart = self.exchange.create_order.call_count

        LiveTrader(
            self.exchange, self.config,
            mode=TradingMode.LIVE, db_manager=self.db,
        )

        self.assertGreater(
            self.exchange.create_order.call_count,
            create_before_restart,
            "Fresh LiveTrader after DB restore should re-arm exchange stop",
        )


class TrailingUpdatesStopTests(unittest.TestCase):
    def setUp(self):
        self.exchange = _exchange_with_stops()
        self.config = _make_config()
        self.config.exchange_stop_loss_enabled = True
        self.config.exchange_stop_update_on_trailing = True
        self.trader = LiveTrader(self.exchange, self.config, mode=TradingMode.LIVE)
        self.trader.usdt_balance = 1_000.0

    def test_trailing_ratchet_places_new_protective_stop(self):
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-T", "status": "closed",
            "amount": 0.01, "filled": 0.01, "average": 50_000.0,
            "fee": {"cost": 0.5, "currency": "USDT"},
        }
        self.exchange.fetch_order.side_effect = [
            {
                "id": "OID-T", "status": "closed",
                "amount": 0.01, "filled": 0.01, "average": 50_000.0,
                "fee": {"cost": 0.5, "currency": "USDT"},
            },
        ]
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        self.trader.execute_market_buy(0.01)
        after_buy = self.exchange.create_order.call_count

        self.trader.update_position(51_000.0)
        self.assertGreater(
            self.exchange.create_order.call_count,
            after_buy,
            "Trailing ratchet should replace the exchange protective stop",
        )


class ExchangeStopOrderIdDbTests(unittest.TestCase):
    """exchange_stop_order_id is stored on the positions row."""

    def setUp(self):
        self.db = initialize_database("sqlite:///:memory:")
        self.exchange = _exchange_with_stops()
        self.config = _make_config()
        self.config.exchange_stop_loss_enabled = True
        self.trader = LiveTrader(
            self.exchange, self.config,
            mode=TradingMode.LIVE, db_manager=self.db,
        )
        self.trader.usdt_balance = 1_000.0

    def _do_buy(self):
        self.exchange.create_market_buy_order.return_value = {
            "id": "OID-DB", "status": "closed",
            "amount": 0.01, "filled": 0.01, "average": 50_000.0,
            "fee": {"cost": 0.5, "currency": "USDT"},
        }
        self.exchange.fetch_order.side_effect = [
            {
                "id": "OID-DB", "status": "closed",
                "amount": 0.01, "filled": 0.01, "average": 50_000.0,
                "fee": {"cost": 0.5, "currency": "USDT"},
            },
        ]
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        self.trader.execute_market_buy(0.01)

    def test_row_persists_exchange_stop_order_id_after_buy(self):
        self._do_buy()
        rows = self.db.get_open_positions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].exchange_stop_order_id, "STOP-1")

    def test_cancel_protective_stop_writes_null_to_db(self):
        self._do_buy()
        self.assertEqual(self.db.get_open_positions()[0].exchange_stop_order_id, "STOP-1")
        self.trader._cancel_exchange_protective_stop()
        self.assertIsNone(self.trader.open_position.exchange_stop_order_id)
        self.assertIsNone(self.db.get_open_positions()[0].exchange_stop_order_id)

    def test_second_process_init_keeps_exchange_stop_linked_in_db(self):
        """Fresh LiveTrader restores from DB then re-syncs protective stop."""
        self._do_buy()
        row = self.db.get_open_positions()[0]
        self.exchange._balance = {
            "USDT": {"free": 500.0, "total": 500.0},
            "BTC": {"free": 0.01, "total": 0.01},
        }
        trader2 = LiveTrader(
            self.exchange, self.config,
            mode=TradingMode.LIVE, db_manager=self.db,
        )
        self.assertIsNotNone(trader2.open_position)
        self.assertEqual(trader2.open_position.exchange_stop_order_id, "STOP-1")
        still = self.db.get_open_positions()
        self.assertEqual(len(still), 1)
        self.assertEqual(still[0].exchange_stop_order_id, "STOP-1")
        self.assertEqual(still[0].id, row.id)


if __name__ == "__main__":
    unittest.main()
