"""
Test suite for LiveTrader module.

Tests cover:
- Trading mode validation
- Pre-trade validation
- Order execution (simulated)
- Position management
- Safety controls
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal

from live_trader import (
    LiveTrader,
    TradingMode,
    OrderStatus,
    TradeRecord,
    LivePosition,
    OrderRecord,
)
from config import BotConfig


class MockExchange:
    """Mock CCXT exchange for testing"""
    
    def __init__(self):
        self.markets = {
            'BTC/USDT': {
                'symbol': 'BTC/USDT',
                'base': 'BTC',
                'quote': 'USDT',
                'limits': {
                    'amount': {'min': 0.0001, 'max': 1000},
                    'cost': {'min': 10.0, 'max': 1000000},
                },
                'precision': {
                    'amount': 8,
                    'price': 2,
                }
            }
        }
        self._balance = {
            'USDT': {'free': 1000.0, 'total': 1000.0},
            'BTC': {'free': 0.0, 'total': 0.0},
        }
        self._ticker = {'ask': 50000.0, 'bid': 49990.0, 'last': 50000.0}
    
    def load_markets(self):
        return self.markets
    
    def fetch_balance(self):
        return self._balance
    
    def fetch_ticker(self, symbol):
        return self._ticker
    
    def fetch_my_trades(self, symbol, limit=10):
        return []
    
    def create_market_buy_order(self, symbol, amount):
        price = self._ticker['ask']
        return {
            'id': 'test-order-123',
            'symbol': symbol,
            'side': 'buy',
            'type': 'market',
            'amount': amount,
            'filled': amount,
            'remaining': 0,
            'price': price,
            'average': price,
            'status': 'closed',
            'datetime': datetime.now(timezone.utc).isoformat(),
            'fee': {'cost': amount * price * 0.001, 'currency': 'USDT'},
        }
    
    def create_market_sell_order(self, symbol, amount):
        price = self._ticker['bid']
        return {
            'id': 'test-order-456',
            'symbol': symbol,
            'side': 'sell',
            'type': 'market',
            'amount': amount,
            'filled': amount,
            'remaining': 0,
            'price': price,
            'average': price,
            'status': 'closed',
            'datetime': datetime.now(timezone.utc).isoformat(),
            'fee': {'cost': amount * price * 0.001, 'currency': 'USDT'},
        }


def create_test_config():
    """Create a test configuration.

    The default safety gates (require_trade_confirmation,
    confirmation_threshold_usd, max_single_trade_usd) are explicitly
    relaxed here so legacy tests that submit larger notionals continue to
    validate the *other* checks. Tests that target the new gates pass
    their own overrides.
    """
    return BotConfig(
        binance_api_key="test_key",
        binance_api_secret="test_secret",
        symbol="BTC/USDT",
        timeframe="1h",
        initial_usdt=1000.0,
        fee_rate=0.001,
        slippage=0.0005,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
        trailing_stop_pct=0.015,
        use_trailing_stop=True,
        order_pct=0.25,
        max_position_size=0.35,
        min_position_size=0.15,
        max_portfolio_drawdown=0.10,
        max_trades_per_day=5,
        trading_mode="paper",
        live_trading_enabled=False,
        require_trade_confirmation=False,
        confirmation_threshold_usd=0.0,
        max_single_trade_usd=0.0,
    )


class TestTradingModes(unittest.TestCase):
    """Test trading mode configuration and validation"""
    
    def test_trading_mode_enum(self):
        """Test TradingMode enum values"""
        self.assertEqual(TradingMode.PAPER.value, "paper")
        self.assertEqual(TradingMode.DRY_RUN.value, "dry_run")
        self.assertEqual(TradingMode.LIVE.value, "live")
    
    def test_default_paper_mode(self):
        """Test that paper mode is the default"""
        exchange = MockExchange()
        config = create_test_config()
        
        trader = LiveTrader(exchange, config)
        
        self.assertEqual(trader.mode, TradingMode.PAPER)
    
    def test_explicit_live_mode(self):
        """Test explicit live mode initialization"""
        exchange = MockExchange()
        config = create_test_config()
        
        trader = LiveTrader(exchange, config, mode=TradingMode.LIVE)
        
        self.assertEqual(trader.mode, TradingMode.LIVE)
    
    def test_dry_run_mode(self):
        """Test dry run mode initialization"""
        exchange = MockExchange()
        config = create_test_config()
        
        trader = LiveTrader(exchange, config, mode=TradingMode.DRY_RUN)
        
        self.assertEqual(trader.mode, TradingMode.DRY_RUN)


class TestPreTradeValidation(unittest.TestCase):
    """Test pre-trade validation logic"""
    
    def setUp(self):
        self.exchange = MockExchange()
        self.config = create_test_config()
        self.trader = LiveTrader(self.exchange, self.config)
        self.trader.usdt_balance = 1000.0
        self.trader.base_balance = 0.0
    
    def test_validate_valid_buy(self):
        """Test validation passes for valid buy"""
        is_valid, msg = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")
    
    def test_validate_insufficient_balance(self):
        """Test validation fails for insufficient balance"""
        self.trader.usdt_balance = 100.0
        is_valid, msg = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("Insufficient USDT", msg)
    
    def test_validate_below_min_amount(self):
        """Test validation fails for amount below minimum"""
        is_valid, msg = self.trader.validate_trade('buy', 0.00001, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("below minimum", msg)
    
    def test_validate_below_min_notional(self):
        """Test validation fails for notional below minimum"""
        is_valid, msg = self.trader.validate_trade('buy', 0.0001, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("Notional", msg)
    
    def test_validate_emergency_stop(self):
        """Test validation fails when emergency stop is active"""
        self.trader.emergency_stop = True
        is_valid, msg = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("Emergency stop", msg)
    
    def test_validate_trading_disabled(self):
        """Test validation fails when trading is disabled"""
        self.trader.trading_enabled = False
        is_valid, msg = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("disabled", msg)
    
    def test_validate_daily_trade_limit(self):
        """Test validation fails when daily trade limit reached"""
        self.trader.daily_trades = 10  # Over limit
        is_valid, msg = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("Daily trade limit", msg)
    
    def test_validate_sell_insufficient_base(self):
        """Test validation fails for sell with insufficient base"""
        self.trader.base_balance = 0.001
        is_valid, msg = self.trader.validate_trade('sell', 0.01, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("Insufficient balance", msg)

    def test_validate_max_single_trade_usd_blocks_oversize(self):
        """Validation fails when notional exceeds BOT_MAX_SINGLE_TRADE_USD."""
        self.trader.config.max_single_trade_usd = 100.0
        is_valid, msg = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("max single-trade cap", msg)

    def test_validate_max_single_trade_usd_zero_disables_cap(self):
        """A cap of 0 disables enforcement (legacy / paper-only setups)."""
        self.trader.config.max_single_trade_usd = 0.0
        is_valid, _ = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertTrue(is_valid)

    def test_validate_require_confirmation_blocks_above_threshold(self):
        """Validation fails when confirmation is required and threshold breached."""
        self.trader.config.require_trade_confirmation = True
        self.trader.config.confirmation_threshold_usd = 100.0
        is_valid, msg = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertFalse(is_valid)
        self.assertIn("confirmation threshold", msg)

    def test_validate_require_confirmation_allows_below_threshold(self):
        """Trades at or below the threshold pass when confirmation is required."""
        self.trader.config.require_trade_confirmation = True
        self.trader.config.confirmation_threshold_usd = 1000.0
        is_valid, _ = self.trader.validate_trade('buy', 0.01, 50000.0)
        self.assertTrue(is_valid)


class TestOrderExecution(unittest.TestCase):
    """Test order execution in different modes"""
    
    def setUp(self):
        self.exchange = MockExchange()
        self.config = create_test_config()
    
    def test_paper_buy_execution(self):
        """Test paper trading buy execution"""
        trader = LiveTrader(self.exchange, self.config, mode=TradingMode.PAPER)
        trader.usdt_balance = 1000.0
        
        trade = trader.execute_market_buy(0.01)
        
        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, 'buy')
        self.assertAlmostEqual(trade.amount, 0.01, places=8)
        self.assertLess(trader.usdt_balance, 1000.0)
        self.assertGreater(trader.base_balance, 0)
    
    def test_paper_sell_execution(self):
        """Test paper trading sell execution"""
        trader = LiveTrader(self.exchange, self.config, mode=TradingMode.PAPER)
        trader.usdt_balance = 500.0
        trader.base_balance = 0.01
        
        # Create a position first
        trader.open_position = LivePosition(
            side='long',
            entry_price=50000.0,
            amount=0.01,
            entry_time=datetime.now(timezone.utc).isoformat(),
            stop_loss=49000.0,
            take_profit=52000.0,
            trailing_stop=49250.0,
            initial_trailing_stop_pct=0.015,
        )
        
        trade = trader.execute_market_sell(0.01, exit_reason='test')
        
        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, 'sell')
        self.assertEqual(trade.exit_reason, 'test')
        self.assertIsNone(trader.open_position)
    
    def test_dry_run_no_balance_change(self):
        """Test dry run mode doesn't change balances"""
        trader = LiveTrader(self.exchange, self.config, mode=TradingMode.DRY_RUN)
        trader.usdt_balance = 1000.0
        initial_balance = trader.usdt_balance
        
        trade = trader.execute_market_buy(0.01)
        
        self.assertIsNotNone(trade)
        self.assertEqual(trader.usdt_balance, initial_balance)


class TestPositionManagement(unittest.TestCase):
    """Test position tracking and risk management"""
    
    def setUp(self):
        self.exchange = MockExchange()
        self.config = create_test_config()
        self.trader = LiveTrader(self.exchange, self.config, mode=TradingMode.PAPER)
        self.trader.usdt_balance = 1000.0
    
    def test_position_creation(self):
        """Test position is created on buy"""
        trade = self.trader.execute_market_buy(0.01)
        
        self.assertIsNotNone(self.trader.open_position)
        self.assertEqual(self.trader.open_position.side, 'long')
        self.assertGreater(self.trader.open_position.stop_loss, 0)
        self.assertGreater(self.trader.open_position.take_profit, 0)
    
    def test_trailing_stop_update(self):
        """Test trailing stop updates on price increase"""
        self.trader.execute_market_buy(0.01)
        initial_trailing = self.trader.open_position.trailing_stop
        initial_highest = self.trader.open_position.highest_price

        # update_position is responsible for raising both highest_price and
        # trailing_stop when a new high is observed.  We pass a price strictly
        # greater than the existing highest_price (the entry price) so the
        # ratchet must move.
        self.trader.update_position(52000.0)

        self.assertGreater(self.trader.open_position.highest_price, initial_highest)
        self.assertGreater(self.trader.open_position.trailing_stop, initial_trailing)
    
    def test_stop_loss_trigger(self):
        """Test stop loss triggers sell"""
        self.trader.execute_market_buy(0.01)
        entry_price = self.trader.open_position.entry_price
        stop_loss = entry_price * 0.95  # Below stop loss
        
        trade = self.trader.update_position(stop_loss)
        
        self.assertIsNotNone(trade)
        self.assertEqual(trade.exit_reason, 'stop_loss')
        self.assertIsNone(self.trader.open_position)
    
    def test_take_profit_trigger(self):
        """Test take profit triggers sell"""
        self.trader.execute_market_buy(0.01)
        entry_price = self.trader.open_position.entry_price
        take_profit = entry_price * 1.05  # Above take profit
        
        trade = self.trader.update_position(take_profit)
        
        self.assertIsNotNone(trade)
        self.assertEqual(trade.exit_reason, 'take_profit')


class TestSafetyControls(unittest.TestCase):
    """Test safety control mechanisms"""
    
    def setUp(self):
        self.exchange = MockExchange()
        self.config = create_test_config()
        self.trader = LiveTrader(self.exchange, self.config)
    
    def test_emergency_stop(self):
        """Test emergency stop disables trading"""
        self.trader.trigger_emergency_stop(close_positions=False)
        
        self.assertTrue(self.trader.emergency_stop)
        self.assertFalse(self.trader.trading_enabled)
    
    def test_disable_enable_trading(self):
        """Test trading can be disabled and enabled"""
        self.trader.disable_trading()
        self.assertFalse(self.trader.trading_enabled)
        
        self.trader.enable_trading()
        self.assertTrue(self.trader.trading_enabled)
    
    def test_reset_emergency_stop(self):
        """Test emergency stop reset"""
        self.trader.trigger_emergency_stop(close_positions=False)
        self.trader.reset_emergency_stop()
        
        self.assertFalse(self.trader.emergency_stop)
        # Trading should still be disabled until explicitly enabled
        self.assertFalse(self.trader.trading_enabled)


class TestStatistics(unittest.TestCase):
    """Test statistics tracking"""
    
    def setUp(self):
        self.exchange = MockExchange()
        self.config = create_test_config()
        self.trader = LiveTrader(self.exchange, self.config, mode=TradingMode.PAPER)
        self.trader.usdt_balance = 1000.0
    
    def test_trade_counters(self):
        """Test trade counters increment correctly"""
        initial_trades = self.trader.total_trades
        
        self.trader.execute_market_buy(0.01)
        
        self.assertEqual(self.trader.total_trades, initial_trades + 1)
        self.assertEqual(self.trader.daily_trades, initial_trades + 1)
    
    def test_stats_output(self):
        """Test get_stats returns expected fields"""
        stats = self.trader.get_stats()
        
        required_fields = [
            'mode', 'total_trades', 'winning_trades', 'losing_trades',
            'win_rate', 'total_pnl', 'daily_trades', 'daily_pnl',
            'trading_enabled', 'emergency_stop', 'has_position'
        ]
        
        for field in required_fields:
            self.assertIn(field, stats)


if __name__ == '__main__':
    unittest.main(verbosity=2)
