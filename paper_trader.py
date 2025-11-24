import csv
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from strategy import StrategySignal

try:
    from database import DatabaseManager, Trade as DBTrade, Position as DBPosition
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


@dataclass
class TradeRecord:
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
    exit_reason: Optional[str] = None  # 'signal', 'stop_loss', 'take_profit', 'trailing_stop'
    pnl: Optional[float] = None  # P&L for exit trades

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class Position:
    """Tracks an open position with risk management levels"""
    side: str  # 'long' or 'short'
    entry_price: float
    amount: float
    entry_time: str
    stop_loss: float
    take_profit: float
    trailing_stop: float
    initial_trailing_stop_pct: float
    highest_price: float = 0.0  # For trailing stop tracking (long)
    lowest_price: float = 0.0   # For trailing stop tracking (short)


class PaperTrader:
    def __init__(
        self,
        initial_usdt: float = 1000.0,
        fee_rate: float = 0.00075,
        slippage: float = 0.0005,
        log_path: str = "trade_log.csv",
        use_trailing_stop: bool = True,
        trailing_stop_pct: float = 0.015,
        db_manager: Optional['DatabaseManager'] = None,
        enable_database: bool = True,
        enable_csv_logging: bool = True,
    ):
        self.usdt_balance = initial_usdt
        self.base_balance = 0.0
        self.initial_usdt = initial_usdt
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.log_path = log_path
        self.use_trailing_stop = use_trailing_stop
        self.trailing_stop_pct = trailing_stop_pct
        
        # Database integration
        self.db_manager = db_manager
        self.enable_database = enable_database and DATABASE_AVAILABLE and db_manager is not None
        self.enable_csv_logging = enable_csv_logging
        self.db_position_id: Optional[int] = None  # Track position ID in database
        
        # Position tracking - Priority 1
        self.open_position: Optional[Position] = None
        self.total_trades = 0
        self.winning_trades = 0
        self.total_pnl = 0.0
        
        if self.enable_csv_logging:
            self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        if not self.log_path:
            return
        header = ",".join(
            [
                "timestamp",
                "side",
                "price",
                "amount",
                "notional",
                "fee",
                "slippage",
                "usdt_balance",
                "base_balance",
                "exit_reason",
                "pnl",
            ]
        )
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                f.write(header + "\n")

    def _log_trade(self, trade: TradeRecord) -> None:
        pnl_str = f" | P&L: ${trade.pnl:.2f}" if trade.pnl is not None else ""
        exit_str = f" | Exit: {trade.exit_reason}" if trade.exit_reason else ""
        logging.info(
            "Paper trade -> %s %.4f @ %.2f | usdt=%.2f base=%.6f%s%s",
            trade.side,
            trade.amount,
            trade.price,
            trade.usdt_balance,
            trade.base_balance,
            pnl_str,
            exit_str,
        )
        
        # Save to database if enabled
        if self.enable_database and self.db_manager:
            try:
                trade_data = {
                    "timestamp": datetime.fromisoformat(trade.timestamp) if isinstance(trade.timestamp, str) else trade.timestamp,
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
                
                # Add signal data if available
                if trade.signal and isinstance(trade.signal, dict):
                    trade_data.update({
                        "signal_direction": trade.signal.get("direction"),
                        "signal_price": trade.signal.get("price"),
                        "short_ema": trade.signal.get("short_ema"),
                        "long_ema": trade.signal.get("long_ema"),
                        "trend_strength": trade.signal.get("trend_strength"),
                        "rsi": trade.signal.get("info", {}).get("rsi"),
                        "atr": trade.signal.get("atr"),
                        "position_size": trade.signal.get("position_size"),
                        "stop_loss": trade.signal.get("stop_loss"),
                        "take_profit": trade.signal.get("take_profit"),
                    })
                
                self.db_manager.add_trade(trade_data)
            except Exception as e:
                logging.error(f"Failed to save trade to database: {e}")
        
        # Save to CSV if enabled
        if self.enable_csv_logging and self.log_path:
            with open(self.log_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        trade.timestamp,
                        trade.side,
                        trade.price,
                        trade.amount,
                        trade.notional,
                        trade.fee,
                        trade.slippage,
                        trade.usdt_balance,
                        trade.base_balance,
                        trade.exit_reason or "",
                        trade.pnl or "",
                    ]
                )

    def get_balances(self) -> Dict[str, float]:
        return {"USDT": self.usdt_balance, "BASE": self.base_balance}
    
    def get_portfolio_value(self, current_price: float) -> float:
        """Calculate total portfolio value at current price"""
        return self.usdt_balance + (self.base_balance * current_price)
    
    def get_drawdown(self, current_price: float) -> float:
        """Calculate current drawdown from initial capital"""
        current_value = self.get_portfolio_value(current_price)
        return (self.initial_usdt - current_value) / self.initial_usdt
    
    def update_position(self, current_price: float) -> Optional[TradeRecord]:
        """
        Check if open position should be closed due to stop loss, take profit, or trailing stop.
        Returns TradeRecord if position was closed, None otherwise.
        """
        if not self.open_position:
            return None
        
        pos = self.open_position
        exit_reason = None
        
        if pos.side == "long":
            # Update trailing stop for long positions
            if self.use_trailing_stop:
                if current_price > pos.highest_price:
                    pos.highest_price = current_price
                    # Update trailing stop level
                    new_trailing = current_price * (1 - pos.initial_trailing_stop_pct)
                    if new_trailing > pos.trailing_stop:
                        pos.trailing_stop = new_trailing
            
            # Check exit conditions (order matters: stop loss checked first for safety)
            if current_price <= pos.stop_loss:
                exit_reason = "stop_loss"
            elif current_price >= pos.take_profit:
                exit_reason = "take_profit"
            elif self.use_trailing_stop and current_price <= pos.trailing_stop:
                exit_reason = "trailing_stop"
                
        elif pos.side == "short":
            # Update trailing stop for short positions
            if self.use_trailing_stop:
                if pos.lowest_price == 0 or current_price < pos.lowest_price:
                    pos.lowest_price = current_price
                    # Update trailing stop level
                    new_trailing = current_price * (1 + pos.initial_trailing_stop_pct)
                    if new_trailing < pos.trailing_stop or pos.trailing_stop == 0:
                        pos.trailing_stop = new_trailing
            
            # Check exit conditions
            if current_price >= pos.stop_loss:
                exit_reason = "stop_loss"
            elif current_price <= pos.take_profit:
                exit_reason = "take_profit"
            elif self.use_trailing_stop and pos.trailing_stop > 0 and current_price >= pos.trailing_stop:
                exit_reason = "trailing_stop"
        
        # Exit position if any condition triggered
        if exit_reason:
            return self._close_position(current_price, exit_reason)
        
        return None

    def _open_position_in_db(self, position: Position) -> None:
        """Save position opening to database"""
        if self.enable_database and self.db_manager:
            try:
                position_data = {
                    "side": position.side,
                    "entry_price": position.entry_price,
                    "entry_time": datetime.fromisoformat(position.entry_time) if isinstance(position.entry_time, str) else position.entry_time,
                    "amount": position.amount,
                    "stop_loss": position.stop_loss,
                    "take_profit": position.take_profit,
                    "trailing_stop": position.trailing_stop,
                    "highest_price": position.highest_price,
                    "lowest_price": position.lowest_price,
                    "is_open": True,
                }
                db_position = self.db_manager.add_position(position_data)
                self.db_position_id = db_position.id
            except Exception as e:
                logging.error(f"Failed to save position to database: {e}")
    
    def _close_position_in_db(self, exit_price: float, exit_reason: str, pnl: float) -> None:
        """Update position closure in database"""
        if self.enable_database and self.db_manager and self.db_position_id:
            try:
                pnl_percent = (pnl / (self.open_position.amount * self.open_position.entry_price) * 100) if self.open_position else 0.0
                updates = {
                    "exit_price": exit_price,
                    "exit_time": datetime.now(timezone.utc),
                    "exit_reason": exit_reason,
                    "pnl": pnl,
                    "pnl_percent": pnl_percent,
                    "is_open": False,
                }
                self.db_manager.update_position(self.db_position_id, updates)
                self.db_position_id = None
            except Exception as e:
                logging.error(f"Failed to update position in database: {e}")

    def _close_position(self, current_price: float, exit_reason: str) -> Optional[TradeRecord]:
        """Close the current open position"""
        if not self.open_position:
            return None
        
        pos = self.open_position
        
        if pos.side == "long":
            # Sell to close long position
            fill_price = current_price * (1 - self.slippage)
            notional = pos.amount * fill_price
            fee = notional * self.fee_rate
            self.base_balance -= pos.amount
            self.usdt_balance += notional - fee
            
            # Calculate P&L
            entry_cost = pos.amount * pos.entry_price
            pnl = (notional - fee) - entry_cost
            
        else:  # short
            # Buy to close short position
            fill_price = current_price * (1 + self.slippage)
            notional = pos.amount * fill_price
            fee = notional * self.fee_rate
            self.usdt_balance -= notional + fee
            self.base_balance += pos.amount
            
            # Calculate P&L (for short: profit when price goes down)
            exit_cost = notional + fee
            entry_value = pos.amount * pos.entry_price
            pnl = entry_value - exit_cost
        
        # Update stats
        self.total_trades += 1
        self.total_pnl += pnl
        if pnl > 0:
            self.winning_trades += 1
        
        # Update position in database
        self._close_position_in_db(fill_price, exit_reason, pnl)
        
        trade = TradeRecord(
            side="sell" if pos.side == "long" else "buy",
            price=fill_price,
            amount=pos.amount,
            notional=notional,
            fee=fee,
            slippage=abs(fill_price - current_price),
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signal={},
            exit_reason=exit_reason,
            pnl=pnl,
        )
        
        self._log_trade(trade)
        self.open_position = None
        return trade
    
    def handle_signal(
        self, signal: "StrategySignal", order_pct: float = None
    ) -> Optional[TradeRecord]:
        """
        Handle trading signal with position tracking and risk management.
        Uses signal.position_size if order_pct is None and dynamic sizing is enabled.
        """
        # Use dynamic position size from signal if available
        if order_pct is None and signal.position_size > 0:
            order_pct = signal.position_size
        elif order_pct is None:
            order_pct = 0.2  # Default fallback
        
        # If we have an open position in the opposite direction, close it first
        if self.open_position:
            if (self.open_position.side == "long" and signal.direction == "bearish") or \
               (self.open_position.side == "short" and signal.direction == "bullish"):
                self._close_position(signal.price, "signal")
        
        # Open new position based on signal
        if signal.direction == "bullish" and not self.open_position:
            return self._buy(signal.price, order_pct, signal)
        elif signal.direction == "bearish" and not self.open_position:
            return self._sell(signal.price, order_pct, signal)
        
        return None

    def _buy(self, price: float, order_pct: float, signal) -> Optional[TradeRecord]:
        """Open a long position"""
        if self.usdt_balance <= 0:
            return None
        notional = self.usdt_balance * order_pct
        if notional <= 0:
            return None

        fill_price = price * (1 + self.slippage)
        amount = notional / fill_price
        fee = notional * self.fee_rate
        self.usdt_balance -= notional + fee
        self.base_balance += amount

        # Create position with risk management levels
        self.open_position = Position(
            side="long",
            entry_price=fill_price,
            amount=amount,
            entry_time=datetime.now(timezone.utc).isoformat(),
            stop_loss=signal.stop_loss if signal.stop_loss > 0 else fill_price * 0.98,
            take_profit=signal.take_profit if signal.take_profit > 0 else fill_price * 1.04,
            trailing_stop=fill_price * (1 - self.trailing_stop_pct),
            initial_trailing_stop_pct=self.trailing_stop_pct,
            highest_price=fill_price,
        )
        
        # Save position opening to database
        self._open_position_in_db(self.open_position)

        trade = TradeRecord(
            side="buy",
            price=fill_price,
            amount=amount,
            notional=notional,
            fee=fee,
            slippage=fill_price - price,
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signal=signal.to_dict(),
        )
        self._log_trade(trade)
        return trade

    def _sell(self, price: float, order_pct: float, signal) -> Optional[TradeRecord]:
        """
        Open a short position (in paper trading, we simulate shorting).
        Note: For spot trading, this would just close a long. 
        For futures, this would open an actual short.
        """
        # For spot paper trading: if we have base balance, sell it
        # If no base balance, simulate shorting by treating it as opening a short position
        
        if self.base_balance > 0:
            # Close existing long position
            amount = self.base_balance * order_pct
        else:
            # Simulate short: allocate USDT as if we're borrowing and selling
            if self.usdt_balance <= 0:
                return None
            notional = self.usdt_balance * order_pct
            fill_price = price * (1 - self.slippage)
            amount = notional / fill_price

        fill_price = price * (1 - self.slippage)
        notional = amount * fill_price
        fee = notional * self.fee_rate
        self.base_balance -= amount
        self.usdt_balance += notional - fee

        # Create position for short (if we're actually shorting, not just closing)
        if self.base_balance < 0:  # We have a short position
            self.open_position = Position(
                side="short",
                entry_price=fill_price,
                amount=abs(self.base_balance),
                entry_time=datetime.now(timezone.utc).isoformat(),
                stop_loss=signal.stop_loss if signal.stop_loss > 0 else fill_price * 1.02,
                take_profit=signal.take_profit if signal.take_profit > 0 else fill_price * 0.96,
                trailing_stop=fill_price * (1 + self.trailing_stop_pct),
                initial_trailing_stop_pct=self.trailing_stop_pct,
                lowest_price=fill_price,
            )
            
            # Save position opening to database
            self._open_position_in_db(self.open_position)

        trade = TradeRecord(
            side="sell",
            price=fill_price,
            amount=amount,
            notional=notional,
            fee=fee,
            slippage=price - fill_price,
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signal=signal.to_dict(),
        )
        self._log_trade(trade)
        return trade
    
    def get_trade_history(self, limit: int = 100, **filters) -> List[Dict]:
        """
        Get trade history from database.
        
        Args:
            limit: Maximum number of trades to return
            **filters: Additional filters (side, exit_reason, start_date, end_date)
            
        Returns:
            List of trade dictionaries
        """
        if not self.enable_database or not self.db_manager:
            return []
        
        try:
            trades = self.db_manager.get_trades(limit=limit, **filters)
            return [
                {
                    "id": t.id,
                    "timestamp": t.timestamp.isoformat(),
                    "side": t.side,
                    "price": t.price,
                    "amount": t.amount,
                    "notional": t.notional,
                    "fee": t.fee,
                    "pnl": t.pnl,
                    "exit_reason": t.exit_reason,
                    "usdt_balance": t.usdt_balance,
                    "base_balance": t.base_balance,
                }
                for t in trades
            ]
        except Exception as e:
            logging.error(f"Failed to get trade history: {e}")
            return []
    
    def get_performance_stats(self) -> Dict:
        """
        Get performance statistics from database.
        
        Returns:
            Dictionary with performance metrics
        """
        if not self.enable_database or not self.db_manager:
            return {
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.total_trades - self.winning_trades,
                "win_rate": (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0.0,
                "total_pnl": self.total_pnl,
                "avg_pnl": self.total_pnl / self.total_trades if self.total_trades > 0 else 0.0,
            }
        
        try:
            return self.db_manager.get_trade_stats()
        except Exception as e:
            logging.error(f"Failed to get performance stats: {e}")
            return {}
    
    def get_open_positions_from_db(self) -> List[Dict]:
        """
        Get currently open positions from database.
        
        Returns:
            List of position dictionaries
        """
        if not self.enable_database or not self.db_manager:
            return []
        
        try:
            positions = self.db_manager.get_open_positions()
            return [
                {
                    "id": p.id,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "entry_time": p.entry_time.isoformat(),
                    "amount": p.amount,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                    "trailing_stop": p.trailing_stop,
                }
                for p in positions
            ]
        except Exception as e:
            logging.error(f"Failed to get open positions: {e}")
            return []

