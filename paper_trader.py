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
    """Tracks an open long position with risk management levels (spot trading only)"""
    side: str  # 'long' only (spot trading doesn't support shorts)
    entry_price: float
    amount: float
    entry_time: str
    stop_loss: float
    take_profit: float
    trailing_stop: float
    initial_trailing_stop_pct: float
    highest_price: float = 0.0  # For trailing stop tracking
    lowest_price: float = 0.0   # Unused in spot-only mode (kept for database compatibility)
    strategy_name: Optional[str] = None  # Track which strategy opened this position


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
        
        # Restore balance from database if available
        if self.enable_database:
            self._restore_from_database()
        
        if self.enable_csv_logging:
            self._ensure_log_file()

    def _restore_from_database(self) -> None:
        """Restore balance and open position from database"""
        try:
            # Get the most recent trade to restore balance
            recent_trades = self.db_manager.get_trades(limit=1)
            if recent_trades:
                last_trade = recent_trades[0]
                self.usdt_balance = float(last_trade.usdt_balance)
                self.base_balance = float(last_trade.base_balance)
                logging.info(f"📊 Restored balance from database: USDT={self.usdt_balance:.2f}, BASE={self.base_balance:.6f}")
            
            # Get any open positions
            open_positions = self.db_manager.get_open_positions()
            if open_positions:
                db_pos = open_positions[0]  # Should only be one open position
                self.open_position = Position(
                    side=db_pos.side,
                    entry_price=float(db_pos.entry_price),
                    amount=float(db_pos.amount),
                    entry_time=db_pos.entry_time.isoformat(),
                    stop_loss=float(db_pos.stop_loss) if db_pos.stop_loss else 0.0,
                    take_profit=float(db_pos.take_profit) if db_pos.take_profit else 0.0,
                    trailing_stop=float(db_pos.trailing_stop) if db_pos.trailing_stop else 0.0,
                    initial_trailing_stop_pct=self.trailing_stop_pct,
                    highest_price=float(db_pos.entry_price),
                    strategy_name=db_pos.strategy_name if hasattr(db_pos, 'strategy_name') else None,
                )
                self.db_position_id = db_pos.id
                logging.info(f"📊 Restored open position: {db_pos.side} {db_pos.amount:.6f} @ ${db_pos.entry_price:.2f}")
        except Exception as e:
            logging.warning(f"Could not restore from database: {e}")

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
                    # Get indicators from signal or info
                    indicators = trade.signal.get("indicators", {})
                    info = trade.signal.get("info", {})
                    
                    trade_data.update({
                        "signal_direction": trade.signal.get("direction"),
                        "signal_price": trade.signal.get("price"),
                        "short_ema": indicators.get("short_ema") or trade.signal.get("short_ema"),
                        "long_ema": indicators.get("long_ema") or trade.signal.get("long_ema"),
                        "trend_strength": indicators.get("trend_strength") or trade.signal.get("trend_strength"),
                        "rsi": indicators.get("rsi") or info.get("rsi"),
                        "atr": indicators.get("atr") or trade.signal.get("atr"),
                        "position_size": trade.signal.get("position_size"),
                        "stop_loss": trade.signal.get("stop_loss"),
                        "take_profit": trade.signal.get("take_profit"),
                        "strategy_name": trade.signal.get("strategy_name"),
                        "signal_confidence": trade.signal.get("confidence"),
                    })
                
                self.db_manager.add_trade(trade_data)
                logging.debug(f"✓ Saved {trade.side} trade to database: {trade.amount:.6f} @ ${trade.price:.2f}")
            except Exception as e:
                logging.error(f"Failed to save trade to database: {e}", exc_info=True)
        
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
        
        # Only long positions supported (spot trading)
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
        else:
            # Should never happen in spot-only mode
            logging.warning(f"Invalid position side: {pos.side}. Only 'long' supported in spot trading.")
            return None
        
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
                    "strategy_name": position.strategy_name,
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
                logging.debug(f"✓ Closed position {self.db_position_id} in database: {exit_reason}")
            except Exception as e:
                logging.error(f"Failed to update position in database: {e}", exc_info=True)

    def _close_position(self, current_price: float, exit_reason: str) -> Optional[TradeRecord]:
        """Close the current open long position (spot trading only)"""
        if not self.open_position:
            return None
        
        pos = self.open_position
        
        # Only long positions supported in spot trading
        if pos.side != "long":
            logging.warning(f"Cannot close {pos.side} position in spot-only mode")
            return None
        
        # Sell to close long position
        fill_price = current_price * (1 - self.slippage)
        notional = pos.amount * fill_price
        fee = notional * self.fee_rate
        self.base_balance -= pos.amount
        self.usdt_balance += notional - fee
        
        # Calculate P&L
        entry_cost = pos.amount * pos.entry_price
        pnl = (notional - fee) - entry_cost
        
        # Update stats
        self.total_trades += 1
        self.total_pnl += pnl
        if pnl > 0:
            self.winning_trades += 1
        
        # Update position in database
        self._close_position_in_db(fill_price, exit_reason, pnl)
        
        trade = TradeRecord(
            side="sell",
            price=fill_price,
            amount=pos.amount,
            notional=notional,
            fee=fee,
            slippage=abs(fill_price - current_price),
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.now(timezone.utc).isoformat(),
            signal={"strategy_name": pos.strategy_name} if pos.strategy_name else {},
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
        
        # Spot trading logic: Long positions only
        if self.open_position:
            # Close long position on bearish signal
            if self.open_position.side == "long" and signal.direction == "bearish":
                return self._close_position(signal.price, "signal")
        
        # Open new long position on bullish signal (only if no position)
        if signal.direction == "bullish" and not self.open_position:
            return self._buy(signal.price, order_pct, signal)
        elif signal.direction == "bearish" and not self.open_position:
            # In spot trading, can't open short positions
            # Bearish signals without a position are ignored
            logging.debug(f"Bearish signal ignored - no position to exit (spot trading mode)")
            return None
        
        return None

    def _buy(self, price: float, order_pct: float, signal) -> Optional[TradeRecord]:
        """Open a long position or add to existing long position (scale in)"""
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

        # Check if we're adding to an existing long position
        if self.open_position and self.open_position.side == "long":
            # Scale in: calculate new average entry price
            old_position = self.open_position
            old_cost = old_position.entry_price * old_position.amount
            new_cost = fill_price * amount
            total_amount = old_position.amount + amount
            avg_entry_price = (old_cost + new_cost) / total_amount
            
            # Update position with new average entry price and amount
            self.open_position.amount = total_amount
            self.open_position.entry_price = avg_entry_price
            
            # Recalculate stop loss and take profit based on new average entry
            # Keep the same percentage distance from the new average entry price
            old_sl_pct = (old_position.entry_price - old_position.stop_loss) / old_position.entry_price
            old_tp_pct = (old_position.take_profit - old_position.entry_price) / old_position.entry_price
            
            self.open_position.stop_loss = avg_entry_price * (1 - old_sl_pct)
            self.open_position.take_profit = avg_entry_price * (1 + old_tp_pct)
            
            # Update trailing stop based on new average entry
            self.open_position.trailing_stop = max(
                old_position.trailing_stop,  # Keep current trailing stop if higher
                avg_entry_price * (1 - self.trailing_stop_pct)
            )
            
            # Update database position
            if self.enable_database and self.db_manager and self.db_position_id:
                try:
                    updates = {
                        "entry_price": avg_entry_price,
                        "amount": total_amount,
                        "stop_loss": self.open_position.stop_loss,
                        "take_profit": self.open_position.take_profit,
                        "trailing_stop": self.open_position.trailing_stop,
                    }
                    self.db_manager.update_position(self.db_position_id, updates)
                    logging.info(f"🔼 Scaled into long position: {amount:.6f} BTC @ ${fill_price:.2f} | New avg entry: ${avg_entry_price:.2f} | Total: {total_amount:.6f} BTC")
                except Exception as e:
                    logging.error(f"Failed to update position in database: {e}")
        else:
            # Create new position with risk management levels
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
                strategy_name=signal.to_dict().get("strategy_name", "Unknown"),
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
        Sell owned BTC (spot trading only - no shorting).
        Can only sell if you have BTC to sell.
        """
        # Spot trading: can only sell what you own
        if self.base_balance <= 0:
            logging.info(f"Cannot sell - no BTC position to exit (balance: {self.base_balance})")
            return None
        
        # Calculate amount to sell
        amount = self.base_balance * order_pct
        
        fill_price = price * (1 - self.slippage)
        notional = amount * fill_price
        fee = notional * self.fee_rate
        self.base_balance -= amount
        self.usdt_balance += notional - fee

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
    
    # ------------------------------------------------------------------
    # Public trading interface (matches LiveTrader's API so that
    # TradingManager can work with either trader without special-casing)
    # ------------------------------------------------------------------

    def execute_market_buy(self, amount: float, signal) -> Optional[TradeRecord]:
        """
        Execute a market buy.

        ``amount`` is the BASE-currency amount to buy (e.g. BTC), matching
        :py:meth:`live_trader.LiveTrader.execute_market_buy` so callers can
        switch traders without changing the API contract.

        Returns the resulting :class:`TradeRecord` or ``None`` if the trade
        was rejected (zero/negative amount, no funds, would over-spend).
        """
        if amount <= 0:
            return None
        if self.usdt_balance <= 0:
            logging.info("execute_market_buy: no USDT balance")
            return None

        price = signal.price
        if price <= 0:
            logging.info("execute_market_buy: invalid signal price %s", price)
            return None

        # Project what _buy() will do so we can validate before any state
        # mutation.  _buy uses (usdt_balance * order_pct) as the pre-fee
        # notional and adds fee on top, then derives BTC amount from the
        # post-slippage fill price.  Inverting that:
        fill_price = price * (1 + self.slippage)
        notional_required = amount * fill_price
        total_cost = notional_required * (1 + self.fee_rate)

        if total_cost > self.usdt_balance:
            logging.info(
                "execute_market_buy: insufficient USDT (need %.2f for %.8f BASE, have %.2f)",
                total_cost,
                amount,
                self.usdt_balance,
            )
            return None

        order_pct = notional_required / self.usdt_balance
        return self._buy(price, order_pct, signal)

    def execute_market_sell(
        self, amount: float, signal, exit_reason: str = "manual"
    ) -> Optional[TradeRecord]:
        """
        Execute a market sell.

        ``amount`` is the BASE-currency amount to sell.  In spot paper
        trading we only support closing the entire open long position,
        so ``amount`` must be approximately equal to the open position's
        size (within 1e-8 to absorb float noise).  Anything else is
        rejected to keep the API honest about its capabilities.
        """
        if not self.open_position:
            logging.info("execute_market_sell: no open position to close")
            return None

        if amount <= 0:
            return None

        # Tolerate tiny float drift between the caller and the trader's
        # bookkeeping (e.g. JSON round-trip).
        if abs(amount - self.open_position.amount) > 1e-8:
            logging.info(
                "execute_market_sell: partial sells not supported in paper "
                "spot mode (requested %.8f, position %.8f)",
                amount,
                self.open_position.amount,
            )
            return None

        return self._close_position(signal.price, exit_reason)

    def enable_trading(self) -> None:
        """No-op — included for interface compatibility with LiveTrader."""

    def disable_trading(self) -> None:
        """No-op — included for interface compatibility with LiveTrader."""

    def trigger_emergency_stop(self, close_positions: bool = True) -> None:
        """
        Emergency stop.  If ``close_positions`` is True and a long position
        is open, it is closed immediately at its entry price (best-effort
        estimate when no live feed is available at stop time).
        """
        logging.critical("PaperTrader: emergency stop triggered")
        if close_positions and self.open_position:
            close_price = self.open_position.entry_price
            self._close_position(close_price, "emergency_stop")

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

