"""
Live Trader - Execute real orders on Binance.US

This module provides live trading capabilities with:
- Market order execution
- Order status tracking
- Position synchronization
- Pre-trade validation
- Safety limits and controls
"""

import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    from strategy import StrategySignal

try:
    from database import DatabaseManager, Trade as DBTrade, Position as DBPosition
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


class TradingMode(Enum):
    """Trading execution modes"""
    PAPER = "paper"      # Simulated trades (no real orders)
    DRY_RUN = "dry_run"  # Real signals, logged but not executed
    LIVE = "live"        # Real order execution


class OrderStatus(Enum):
    """Order status states"""
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    PARTIALLY_FILLED = "partially_filled"


@dataclass
class OrderRecord:
    """Record of an order placed on the exchange"""
    order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market', 'limit'
    amount: float
    price: Optional[float]  # Filled price for market orders
    filled: float
    remaining: float
    status: str
    timestamp: str
    fee: Optional[float] = None
    fee_currency: Optional[str] = None
    average_price: Optional[float] = None
    trades: Optional[List[Dict]] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TradeRecord:
    """Record of a completed trade"""
    side: str
    price: float
    amount: float
    notional: float
    fee: float
    slippage: float
    usdt_balance: float
    base_balance: float
    timestamp: str
    signal: Dict[str, object]
    exit_reason: Optional[str] = None
    pnl: Optional[float] = None
    order_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class LivePosition:
    """Tracks an open position with risk management"""
    side: str  # 'long' or 'short'
    entry_price: float
    amount: float
    entry_time: str
    stop_loss: float
    take_profit: float
    trailing_stop: float
    initial_trailing_stop_pct: float
    entry_order_id: Optional[str] = None
    highest_price: float = 0.0
    lowest_price: float = 0.0


class LiveTrader:
    """
    Execute real orders on Binance.US with safety controls.
    
    Features:
    - Market order execution via CCXT
    - Order status tracking and polling
    - Position synchronization with exchange
    - Pre-trade validation (balance, limits, sizes)
    - Daily loss limit enforcement
    - Max trades per day limit
    - Comprehensive logging
    """
    
    def __init__(
        self,
        exchange,
        config,
        mode: TradingMode = TradingMode.PAPER,
        db_manager: Optional['DatabaseManager'] = None,
    ):
        """
        Initialize LiveTrader.
        
        Args:
            exchange: CCXT exchange instance (binanceus)
            config: BotConfig instance
            mode: Trading mode (paper, dry_run, live)
            db_manager: Optional database manager for persistence
        """
        self.exchange = exchange
        self.config = config
        self.mode = mode
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        
        # Symbol info (populated on first use)
        self._market_info: Optional[Dict] = None
        
        # Position tracking
        self.open_position: Optional[LivePosition] = None
        
        # Balance tracking (synced from exchange)
        self.usdt_balance: float = 0.0
        self.base_balance: float = 0.0
        self.reserved_balance: float = 0.0  # Reserved for fees
        
        # Order tracking
        self.pending_orders: Dict[str, OrderRecord] = {}
        self.completed_orders: List[OrderRecord] = []
        
        # Daily limits tracking
        self.daily_trades: int = 0
        self.daily_pnl: float = 0.0
        self.daily_reset_time: datetime = self._get_daily_reset_time()
        
        # Statistics
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.total_pnl: float = 0.0
        
        # Safety flags
        self.trading_enabled: bool = True
        self.emergency_stop: bool = False
        
        self.logger.info(f"LiveTrader initialized in {mode.value} mode")
    
    def _get_daily_reset_time(self) -> datetime:
        """Get the next daily reset time (midnight UTC)"""
        now = datetime.now(timezone.utc)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return tomorrow
    
    def _check_daily_reset(self):
        """Reset daily counters if past reset time"""
        now = datetime.now(timezone.utc)
        if now >= self.daily_reset_time:
            self.logger.info("Resetting daily trade counters")
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.daily_reset_time = self._get_daily_reset_time()
    
    def _get_market_info(self) -> Dict:
        """Get market info for the trading symbol"""
        if self._market_info is None:
            self.exchange.load_markets()
            symbol = self.config.symbol
            if symbol not in self.exchange.markets:
                raise ValueError(f"Symbol {symbol} not found on exchange")
            self._market_info = self.exchange.markets[symbol]
        return self._market_info
    
    def get_min_order_size(self) -> float:
        """Get minimum order size for the symbol"""
        market = self._get_market_info()
        limits = market.get('limits', {})
        amount_limits = limits.get('amount', {})
        return float(amount_limits.get('min', 0.0001))
    
    def get_min_notional(self) -> float:
        """Get minimum notional value for orders"""
        market = self._get_market_info()
        limits = market.get('limits', {})
        cost_limits = limits.get('cost', {})
        return float(cost_limits.get('min', 10.0))  # Binance.US typically $10 min
    
    def get_price_precision(self) -> int:
        """Get price precision for the symbol"""
        market = self._get_market_info()
        return market.get('precision', {}).get('price', 2)
    
    def get_amount_precision(self) -> int:
        """Get amount precision for the symbol"""
        market = self._get_market_info()
        return market.get('precision', {}).get('amount', 8)
    
    def round_amount(self, amount: float) -> float:
        """Round amount to exchange precision"""
        precision = self.get_amount_precision()
        factor = 10 ** precision
        return float(Decimal(str(amount)).quantize(
            Decimal(str(1 / factor)), rounding=ROUND_DOWN
        ))
    
    def round_price(self, price: float) -> float:
        """Round price to exchange precision"""
        precision = self.get_price_precision()
        return round(price, precision)
    
    # =========================================================================
    # Balance Management
    # =========================================================================
    
    def sync_balances(self) -> Dict[str, float]:
        """
        Sync balances from exchange.
        
        Returns:
            Dict with USDT and BASE balances
        """
        try:
            balance = self.exchange.fetch_balance()
            
            # Extract USDT balance
            usdt_info = balance.get('USDT', {})
            self.usdt_balance = float(usdt_info.get('free', 0.0))
            usdt_total = float(usdt_info.get('total', 0.0))
            
            # Extract base currency balance (e.g., BTC)
            base_currency = self.config.symbol.split('/')[0]
            base_info = balance.get(base_currency, {})
            self.base_balance = float(base_info.get('free', 0.0))
            base_total = float(base_info.get('total', 0.0))
            
            # Reserve some USDT for fees (0.1%)
            self.reserved_balance = self.usdt_balance * 0.001
            
            self.logger.info(
                f"Balances synced: USDT={self.usdt_balance:.2f} (total={usdt_total:.2f}), "
                f"{base_currency}={self.base_balance:.8f} (total={base_total:.8f})"
            )
            
            return {
                "USDT": self.usdt_balance,
                "BASE": self.base_balance,
                "USDT_total": usdt_total,
                "BASE_total": base_total,
            }
            
        except Exception as e:
            self.logger.error(f"Failed to sync balances: {e}")
            raise
    
    def get_balances(self) -> Dict[str, float]:
        """Get current balances"""
        return {"USDT": self.usdt_balance, "BASE": self.base_balance}
    
    def get_available_usdt(self) -> float:
        """Get USDT available for trading (minus reserve)"""
        return max(0, self.usdt_balance - self.reserved_balance)
    
    def get_portfolio_value(self, current_price: float) -> float:
        """Calculate total portfolio value"""
        return self.usdt_balance + (self.base_balance * current_price)
    
    # =========================================================================
    # Position Synchronization
    # =========================================================================
    
    def sync_positions(self) -> Optional[LivePosition]:
        """
        Sync positions from exchange.
        
        For spot trading, we infer position from base balance.
        
        Returns:
            LivePosition if we have a position, None otherwise
        """
        try:
            self.sync_balances()
            
            base_currency = self.config.symbol.split('/')[0]
            min_position = self.get_min_order_size()
            
            if self.base_balance > min_position:
                # We have a position - get recent trade to determine entry
                trades = self.exchange.fetch_my_trades(
                    self.config.symbol, limit=10
                )
                
                if trades:
                    # Find the most recent buy that established position
                    buy_trades = [t for t in trades if t['side'] == 'buy']
                    if buy_trades:
                        last_buy = buy_trades[-1]
                        entry_price = float(last_buy['price'])
                        entry_time = last_buy['datetime']
                        
                        # Create position record
                        self.open_position = LivePosition(
                            side='long',
                            entry_price=entry_price,
                            amount=self.base_balance,
                            entry_time=entry_time,
                            stop_loss=entry_price * (1 - self.config.stop_loss_pct),
                            take_profit=entry_price * (1 + self.config.take_profit_pct),
                            trailing_stop=entry_price * (1 - self.config.trailing_stop_pct),
                            initial_trailing_stop_pct=self.config.trailing_stop_pct,
                            entry_order_id=last_buy.get('order'),
                            highest_price=entry_price,
                        )
                        
                        self.logger.info(
                            f"Position synced: LONG {self.base_balance:.8f} {base_currency} "
                            f"@ ${entry_price:.2f}"
                        )
                        return self.open_position
            
            # No significant position
            self.open_position = None
            self.logger.info("No open position detected")
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to sync positions: {e}")
            return None
    
    # =========================================================================
    # Pre-Trade Validation
    # =========================================================================
    
    def validate_trade(
        self,
        side: str,
        amount: float,
        price: float,
    ) -> tuple[bool, str]:
        """
        Validate trade before execution.
        
        Args:
            side: 'buy' or 'sell'
            amount: Amount to trade
            price: Current price
            
        Returns:
            (is_valid, error_message)
        """
        # Check emergency stop
        if self.emergency_stop:
            return False, "Emergency stop is active"
        
        # Check if trading is enabled
        if not self.trading_enabled:
            return False, "Trading is disabled"
        
        # Check daily reset
        self._check_daily_reset()
        
        # Check daily trade limit
        max_trades = getattr(self.config, 'max_trades_per_day', 10)
        if self.daily_trades >= max_trades:
            return False, f"Daily trade limit reached ({max_trades})"
        
        # Check daily loss limit
        max_daily_loss = self.config.initial_usdt * self.config.max_portfolio_drawdown
        if self.daily_pnl < -max_daily_loss:
            return False, f"Daily loss limit reached (${abs(self.daily_pnl):.2f})"
        
        # Check minimum order size
        min_amount = self.get_min_order_size()
        if amount < min_amount:
            return False, f"Amount {amount} below minimum {min_amount}"
        
        # Check minimum notional value
        notional = amount * price
        min_notional = self.get_min_notional()
        if notional < min_notional:
            return False, f"Notional ${notional:.2f} below minimum ${min_notional:.2f}"
        
        # Check balance for buys
        if side == 'buy':
            available = self.get_available_usdt()
            required = notional * 1.001  # Add 0.1% for fees
            if required > available:
                return False, f"Insufficient USDT: need ${required:.2f}, have ${available:.2f}"
        
        # Check balance for sells
        if side == 'sell':
            if amount > self.base_balance:
                return False, f"Insufficient balance: need {amount}, have {self.base_balance}"
        
        return True, ""
    
    # =========================================================================
    # Order Execution
    # =========================================================================
    
    def execute_market_buy(
        self,
        amount: float,
        signal: Optional["StrategySignal"] = None,
    ) -> Optional[TradeRecord]:
        """
        Execute a market buy order.
        
        Args:
            amount: Amount of base currency to buy
            signal: Optional strategy signal that triggered the trade
            
        Returns:
            TradeRecord if successful, None otherwise
        """
        symbol = self.config.symbol
        
        # Get current price for validation
        ticker = self.exchange.fetch_ticker(symbol)
        current_price = float(ticker['ask'])
        
        # Round amount to exchange precision
        amount = self.round_amount(amount)
        
        # Validate trade
        is_valid, error_msg = self.validate_trade('buy', amount, current_price)
        if not is_valid:
            self.logger.warning(f"Trade validation failed: {error_msg}")
            return None
        
        # DRY_RUN mode - log but don't execute
        if self.mode == TradingMode.DRY_RUN:
            self.logger.info(
                f"[DRY_RUN] Would BUY {amount} {symbol} @ ~${current_price:.2f} "
                f"(notional: ${amount * current_price:.2f})"
            )
            return self._create_simulated_trade('buy', amount, current_price, signal)
        
        # PAPER mode - simulate
        if self.mode == TradingMode.PAPER:
            return self._simulate_market_buy(amount, current_price, signal)
        
        # LIVE mode - execute real order
        try:
            self.logger.info(f"Executing MARKET BUY: {amount} {symbol}")
            
            order = self.exchange.create_market_buy_order(
                symbol=symbol,
                amount=amount,
            )
            
            # Track order
            order_record = self._parse_order(order)
            self.completed_orders.append(order_record)
            
            # Update balances
            self.sync_balances()
            
            # Calculate fill price and fees
            fill_price = float(order.get('average', current_price))
            filled_amount = float(order.get('filled', amount))
            fee_info = order.get('fee', {})
            fee = float(fee_info.get('cost', filled_amount * fill_price * self.config.fee_rate))
            
            notional = filled_amount * fill_price
            slippage = fill_price - current_price
            
            # Create trade record
            trade = TradeRecord(
                side='buy',
                price=fill_price,
                amount=filled_amount,
                notional=notional,
                fee=fee,
                slippage=slippage,
                usdt_balance=self.usdt_balance,
                base_balance=self.base_balance,
                timestamp=datetime.now(timezone.utc).isoformat(),
                signal=signal.to_dict() if signal else {},
                order_id=order_record.order_id,
            )
            
            # Update position
            self._open_long_position(fill_price, filled_amount, signal, order_record.order_id)
            
            # Update counters
            self.daily_trades += 1
            self.total_trades += 1
            
            # Log trade
            self._log_trade(trade)
            
            self.logger.info(
                f"BUY executed: {filled_amount} @ ${fill_price:.2f} "
                f"(fee: ${fee:.4f}, slippage: ${slippage:.4f})"
            )
            
            return trade
            
        except Exception as e:
            self.logger.error(f"Market buy failed: {e}")
            raise
    
    def execute_market_sell(
        self,
        amount: float,
        signal: Optional["StrategySignal"] = None,
        exit_reason: str = "signal",
    ) -> Optional[TradeRecord]:
        """
        Execute a market sell order.
        
        Args:
            amount: Amount of base currency to sell
            signal: Optional strategy signal
            exit_reason: Reason for exit (signal, stop_loss, take_profit, etc.)
            
        Returns:
            TradeRecord if successful, None otherwise
        """
        symbol = self.config.symbol
        
        # Get current price for validation
        ticker = self.exchange.fetch_ticker(symbol)
        current_price = float(ticker['bid'])
        
        # Round amount to exchange precision
        amount = self.round_amount(amount)
        
        # Validate trade
        is_valid, error_msg = self.validate_trade('sell', amount, current_price)
        if not is_valid:
            self.logger.warning(f"Trade validation failed: {error_msg}")
            return None
        
        # DRY_RUN mode - log but don't execute
        if self.mode == TradingMode.DRY_RUN:
            self.logger.info(
                f"[DRY_RUN] Would SELL {amount} {symbol} @ ~${current_price:.2f} "
                f"(reason: {exit_reason})"
            )
            return self._create_simulated_trade('sell', amount, current_price, signal, exit_reason)
        
        # PAPER mode - simulate
        if self.mode == TradingMode.PAPER:
            return self._simulate_market_sell(amount, current_price, signal, exit_reason)
        
        # LIVE mode - execute real order
        try:
            self.logger.info(f"Executing MARKET SELL: {amount} {symbol} (reason: {exit_reason})")
            
            order = self.exchange.create_market_sell_order(
                symbol=symbol,
                amount=amount,
            )
            
            # Track order
            order_record = self._parse_order(order)
            self.completed_orders.append(order_record)
            
            # Calculate P&L before balance sync
            pnl = None
            if self.open_position and self.open_position.side == 'long':
                entry_cost = self.open_position.amount * self.open_position.entry_price
                fill_price = float(order.get('average', current_price))
                exit_value = float(order.get('filled', amount)) * fill_price
                fee_info = order.get('fee', {})
                fee = float(fee_info.get('cost', exit_value * self.config.fee_rate))
                pnl = exit_value - entry_cost - fee
                
                # Update stats
                self.total_pnl += pnl
                self.daily_pnl += pnl
                if pnl > 0:
                    self.winning_trades += 1
            
            # Update balances
            self.sync_balances()
            
            # Calculate fill details
            fill_price = float(order.get('average', current_price))
            filled_amount = float(order.get('filled', amount))
            fee_info = order.get('fee', {})
            fee = float(fee_info.get('cost', filled_amount * fill_price * self.config.fee_rate))
            
            notional = filled_amount * fill_price
            slippage = current_price - fill_price
            
            # Create trade record
            trade = TradeRecord(
                side='sell',
                price=fill_price,
                amount=filled_amount,
                notional=notional,
                fee=fee,
                slippage=slippage,
                usdt_balance=self.usdt_balance,
                base_balance=self.base_balance,
                timestamp=datetime.now(timezone.utc).isoformat(),
                signal=signal.to_dict() if signal else {},
                exit_reason=exit_reason,
                pnl=pnl,
                order_id=order_record.order_id,
            )
            
            # Clear position
            self.open_position = None
            
            # Update counters
            self.daily_trades += 1
            self.total_trades += 1
            
            # Log trade
            self._log_trade(trade)
            
            self.logger.info(
                f"SELL executed: {filled_amount} @ ${fill_price:.2f} "
                f"(fee: ${fee:.4f}, P&L: ${pnl:.2f if pnl else 0:.2f})"
            )
            
            return trade
            
        except Exception as e:
            self.logger.error(f"Market sell failed: {e}")
            raise
    
    # =========================================================================
    # Order Status & Tracking
    # =========================================================================
    
    def _parse_order(self, order: Dict) -> OrderRecord:
        """Parse CCXT order response into OrderRecord"""
        fee_info = order.get('fee', {})
        
        return OrderRecord(
            order_id=str(order.get('id', '')),
            client_order_id=order.get('clientOrderId'),
            symbol=order.get('symbol', self.config.symbol),
            side=order.get('side', ''),
            order_type=order.get('type', 'market'),
            amount=float(order.get('amount', 0)),
            price=float(order.get('price', 0)) if order.get('price') else None,
            filled=float(order.get('filled', 0)),
            remaining=float(order.get('remaining', 0)),
            status=order.get('status', 'unknown'),
            timestamp=order.get('datetime', datetime.now(timezone.utc).isoformat()),
            fee=float(fee_info.get('cost', 0)) if fee_info else None,
            fee_currency=fee_info.get('currency'),
            average_price=float(order.get('average', 0)) if order.get('average') else None,
            trades=order.get('trades'),
        )
    
    def get_order_status(self, order_id: str) -> Optional[OrderRecord]:
        """
        Get status of an order.
        
        Args:
            order_id: Exchange order ID
            
        Returns:
            OrderRecord with current status
        """
        try:
            order = self.exchange.fetch_order(order_id, self.config.symbol)
            return self._parse_order(order)
        except Exception as e:
            self.logger.error(f"Failed to fetch order {order_id}: {e}")
            return None
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.
        
        Args:
            order_id: Exchange order ID
            
        Returns:
            True if cancelled successfully
        """
        try:
            self.exchange.cancel_order(order_id, self.config.symbol)
            self.logger.info(f"Order {order_id} cancelled")
            
            # Update pending orders
            if order_id in self.pending_orders:
                self.pending_orders[order_id].status = OrderStatus.CANCELED.value
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False
    
    # =========================================================================
    # Position Management
    # =========================================================================
    
    def _open_long_position(
        self,
        entry_price: float,
        amount: float,
        signal: Optional["StrategySignal"],
        order_id: Optional[str] = None,
    ):
        """Open a new long position"""
        stop_loss = signal.stop_loss if signal and signal.stop_loss > 0 else entry_price * (1 - self.config.stop_loss_pct)
        take_profit = signal.take_profit if signal and signal.take_profit > 0 else entry_price * (1 + self.config.take_profit_pct)
        trailing_stop = entry_price * (1 - self.config.trailing_stop_pct)
        
        self.open_position = LivePosition(
            side='long',
            entry_price=entry_price,
            amount=amount,
            entry_time=datetime.now(timezone.utc).isoformat(),
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=trailing_stop,
            initial_trailing_stop_pct=self.config.trailing_stop_pct,
            entry_order_id=order_id,
            highest_price=entry_price,
        )
        
        self.logger.info(
            f"Position opened: LONG {amount:.8f} @ ${entry_price:.2f} "
            f"| SL: ${stop_loss:.2f} | TP: ${take_profit:.2f}"
        )
    
    def update_position(self, current_price: float) -> Optional[TradeRecord]:
        """
        Update position and check for exit conditions.
        
        Args:
            current_price: Current market price
            
        Returns:
            TradeRecord if position was closed, None otherwise
        """
        if not self.open_position:
            return None
        
        pos = self.open_position
        exit_reason = None
        
        if pos.side == 'long':
            # Update trailing stop
            if self.config.use_trailing_stop:
                if current_price > pos.highest_price:
                    pos.highest_price = current_price
                    new_trailing = current_price * (1 - pos.initial_trailing_stop_pct)
                    if new_trailing > pos.trailing_stop:
                        pos.trailing_stop = new_trailing
                        self.logger.debug(f"Trailing stop updated to ${pos.trailing_stop:.2f}")
            
            # Check exit conditions
            if current_price <= pos.stop_loss:
                exit_reason = "stop_loss"
            elif current_price >= pos.take_profit:
                exit_reason = "take_profit"
            elif self.config.use_trailing_stop and current_price <= pos.trailing_stop:
                exit_reason = "trailing_stop"
        
        # Exit if triggered
        if exit_reason:
            self.logger.info(f"Exit triggered: {exit_reason} at ${current_price:.2f}")
            return self.execute_market_sell(
                amount=pos.amount,
                signal=None,
                exit_reason=exit_reason,
            )
        
        return None
    
    # =========================================================================
    # Signal Handling
    # =========================================================================
    
    def handle_signal(
        self,
        signal: "StrategySignal",
        order_pct: Optional[float] = None,
    ) -> Optional[TradeRecord]:
        """
        Handle a trading signal.
        
        Args:
            signal: Strategy signal
            order_pct: Position size override (uses signal.position_size if None)
            
        Returns:
            TradeRecord if trade executed, None otherwise
        """
        # Use dynamic position size from signal
        if order_pct is None and signal.position_size > 0:
            order_pct = signal.position_size
        elif order_pct is None:
            order_pct = self.config.order_pct
        
        # Check for position exit on opposite signal
        if self.open_position:
            if (self.open_position.side == 'long' and signal.direction == 'bearish'):
                self.logger.info("Closing long position on bearish signal")
                return self.execute_market_sell(
                    amount=self.open_position.amount,
                    signal=signal,
                    exit_reason="signal",
                )
        
        # Open new position
        if signal.direction == 'bullish' and not self.open_position:
            # Calculate buy amount
            available = self.get_available_usdt()
            notional = available * order_pct
            amount = notional / signal.price
            
            return self.execute_market_buy(amount=amount, signal=signal)
        
        elif signal.direction == 'bearish' and self.open_position:
            return self.execute_market_sell(
                amount=self.open_position.amount,
                signal=signal,
                exit_reason="signal",
            )
        
        return None
    
    # =========================================================================
    # Simulation Methods (for PAPER and DRY_RUN modes)
    # =========================================================================
    
    def _simulate_market_buy(
        self,
        amount: float,
        price: float,
        signal: Optional["StrategySignal"],
    ) -> TradeRecord:
        """Simulate a market buy (for paper trading)"""
        fill_price = price * (1 + self.config.slippage)
        notional = amount * fill_price
        fee = notional * self.config.fee_rate
        
        self.usdt_balance -= (notional + fee)
        self.base_balance += amount
        
        trade = TradeRecord(
            side='buy',
            price=fill_price,
            amount=amount,
            notional=notional,
            fee=fee,
            slippage=fill_price - price,
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signal=signal.to_dict() if signal else {},
        )
        
        self._open_long_position(fill_price, amount, signal)
        self.daily_trades += 1
        self.total_trades += 1
        self._log_trade(trade)
        
        return trade
    
    def _simulate_market_sell(
        self,
        amount: float,
        price: float,
        signal: Optional["StrategySignal"],
        exit_reason: str = "signal",
    ) -> TradeRecord:
        """Simulate a market sell (for paper trading)"""
        fill_price = price * (1 - self.config.slippage)
        notional = amount * fill_price
        fee = notional * self.config.fee_rate
        
        # Calculate P&L
        pnl = None
        if self.open_position and self.open_position.side == 'long':
            entry_cost = self.open_position.amount * self.open_position.entry_price
            pnl = (notional - fee) - entry_cost
            self.total_pnl += pnl
            self.daily_pnl += pnl
            if pnl > 0:
                self.winning_trades += 1
        
        self.base_balance -= amount
        self.usdt_balance += (notional - fee)
        
        trade = TradeRecord(
            side='sell',
            price=fill_price,
            amount=amount,
            notional=notional,
            fee=fee,
            slippage=price - fill_price,
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signal=signal.to_dict() if signal else {},
            exit_reason=exit_reason,
            pnl=pnl,
        )
        
        self.open_position = None
        self.daily_trades += 1
        self.total_trades += 1
        self._log_trade(trade)
        
        return trade
    
    def _create_simulated_trade(
        self,
        side: str,
        amount: float,
        price: float,
        signal: Optional["StrategySignal"],
        exit_reason: Optional[str] = None,
    ) -> TradeRecord:
        """Create a simulated trade record for DRY_RUN mode"""
        fill_price = price * (1 + self.config.slippage if side == 'buy' else 1 - self.config.slippage)
        notional = amount * fill_price
        fee = notional * self.config.fee_rate
        
        return TradeRecord(
            side=side,
            price=fill_price,
            amount=amount,
            notional=notional,
            fee=fee,
            slippage=abs(fill_price - price),
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signal=signal.to_dict() if signal else {},
            exit_reason=exit_reason,
        )
    
    # =========================================================================
    # Logging & Persistence
    # =========================================================================
    
    def _log_trade(self, trade: TradeRecord):
        """Log trade to database and file"""
        pnl_str = f" | P&L: ${trade.pnl:.2f}" if trade.pnl is not None else ""
        exit_str = f" | Exit: {trade.exit_reason}" if trade.exit_reason else ""
        mode_str = f"[{self.mode.value.upper()}]"
        
        self.logger.info(
            f"{mode_str} Trade: {trade.side.upper()} {trade.amount:.8f} @ ${trade.price:.2f} "
            f"| USDT: ${trade.usdt_balance:.2f}{pnl_str}{exit_str}"
        )
        
        # Save to database if available
        if self.db_manager:
            try:
                trade_data = {
                    "timestamp": datetime.fromisoformat(trade.timestamp.replace('Z', '+00:00')),
                    "side": trade.side,
                    "price": trade.price,
                    "amount": trade.amount,
                    "notional": trade.notional,
                    "fee": trade.fee,
                    "slippage": trade.slippage,
                    "usdt_balance": trade.usdt_balance,
                    "base_balance": trade.base_balance,
                    "exit_reason": trade.exit_reason,
                    "pnl": trade.pnl,
                }
                
                if trade.signal:
                    trade_data.update({
                        "signal_direction": trade.signal.get("direction"),
                        "signal_price": trade.signal.get("price"),
                        "stop_loss": trade.signal.get("stop_loss"),
                        "take_profit": trade.signal.get("take_profit"),
                        "position_size": trade.signal.get("position_size"),
                    })
                
                self.db_manager.add_trade(trade_data)
            except Exception as e:
                self.logger.error(f"Failed to save trade to database: {e}")
    
    # =========================================================================
    # Safety Controls
    # =========================================================================
    
    def enable_trading(self):
        """Enable trading"""
        self.trading_enabled = True
        self.logger.info("Trading ENABLED")
    
    def disable_trading(self):
        """Disable trading"""
        self.trading_enabled = False
        self.logger.warning("Trading DISABLED")
    
    def trigger_emergency_stop(self, close_positions: bool = True):
        """
        Trigger emergency stop.
        
        Args:
            close_positions: Whether to close all open positions
        """
        self.emergency_stop = True
        self.trading_enabled = False
        self.logger.critical("🚨 EMERGENCY STOP TRIGGERED 🚨")
        
        if close_positions and self.open_position:
            self.logger.info("Closing all positions...")
            try:
                ticker = self.exchange.fetch_ticker(self.config.symbol)
                current_price = float(ticker['bid'])
                self.execute_market_sell(
                    amount=self.open_position.amount,
                    signal=None,
                    exit_reason="emergency_stop",
                )
            except Exception as e:
                self.logger.error(f"Failed to close position during emergency: {e}")
    
    def reset_emergency_stop(self):
        """Reset emergency stop (manual intervention required)"""
        self.emergency_stop = False
        self.logger.warning("Emergency stop RESET - trading still disabled until manually enabled")
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict:
        """Get trading statistics"""
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        return {
            "mode": self.mode.value,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.total_trades - self.winning_trades,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "daily_trades": self.daily_trades,
            "daily_pnl": self.daily_pnl,
            "trading_enabled": self.trading_enabled,
            "emergency_stop": self.emergency_stop,
            "has_position": self.open_position is not None,
        }
