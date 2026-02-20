"""
Trading Manager Service Module

Provides business logic for trading operations:
- Manual buy and sell execution with validation
- Trading enable/disable controls
- Emergency stop functionality
- Exchange state synchronization
- Price fetching and signal creation
"""

import logging
from typing import Dict, Optional, Any
from datetime import datetime

from config import BotConfig


class TradingManager:
    """
    Manages trading operations and business logic.
    
    This class handles all trading operations by delegating to the trader instance
    while managing application state updates. All operations are atomic - either
    fully succeed or fully fail with no partial state changes.
    
    Features:
    - Manual buy/sell execution with validation
    - Trading enable/disable controls
    - Emergency stop with position closing
    - Exchange state synchronization
    - Atomic operations (all-or-nothing)
    """
    
    def __init__(self, app_state, config: BotConfig):
        """
        Initialize TradingManager.
        
        Args:
            app_state: ApplicationState instance
            config: BotConfig instance
        """
        self.app_state = app_state
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def execute_manual_buy(self, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute manual buy order.
        
        This method validates inputs, executes the trade via the trader instance,
        updates application state, and logs to database. If any step fails, no
        state changes occur (atomic operation).
        
        Args:
            amount: Amount to buy (in base currency or percentage)
            price: Optional limit price (not currently used for market orders)
            
        Returns:
            Trade result dictionary with success status and trade data or error
            
        Validates: Requirements 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
        """
        # Step 1: Validate amount
        if amount <= 0:
            self.logger.warning(f"Invalid buy amount: {amount}")
            return {
                "success": False,
                "error": "Amount must be greater than 0",
                "message": "Invalid trade amount"
            }
        
        # Step 2: Get trader instance
        trader = self.app_state.get_trader()
        if trader is None:
            self.logger.error("Trader instance not initialized")
            return {
                "success": False,
                "error": "Trader not initialized",
                "message": "Trading system not ready"
            }
        
        # Step 3: Validate trading is enabled
        trading_state = self.app_state.get_trading_state()
        if not trading_state.trading_enabled:
            self.logger.warning("Manual buy rejected: trading is disabled")
            return {
                "success": False,
                "error": "Trading is disabled",
                "message": "Enable trading before executing trades"
            }
        
        # Step 4: Check emergency stop
        if trading_state.emergency_stop:
            self.logger.warning("Manual buy rejected: emergency stop is active")
            return {
                "success": False,
                "error": "Emergency stop is active",
                "message": "Clear emergency stop before trading"
            }
        
        # Step 5: Create manual signal
        try:
            signal = self.create_manual_signal('bullish', amount)
        except Exception as e:
            self.logger.error(f"Failed to create manual signal: {e}")
            return {
                "success": False,
                "error": f"Signal creation failed: {str(e)}",
                "message": "Failed to prepare trade"
            }
        
        # Step 6: Execute trade
        try:
            self.logger.info(f"Executing manual buy: amount={amount}")
            
            # Execute via trader instance
            trade = trader.execute_market_buy(amount=amount, signal=signal)
            
            if trade is None:
                self.logger.warning("Trade execution returned None (validation failed)")
                return {
                    "success": False,
                    "error": "Trade validation failed",
                    "message": "Trade could not be executed (check logs for details)"
                }
            
            # Step 7: Update application state
            self.app_state.update_trading_state(
                usdt_balance=trader.usdt_balance,
                base_balance=trader.base_balance,
                current_price=trade.price,
                position_open=trader.open_position is not None,
                position_entry_price=trader.open_position.entry_price if trader.open_position else 0.0,
                position_amount=trader.open_position.amount if trader.open_position else 0.0,
                position_side='long' if trader.open_position else 'none',
                stop_loss=trader.open_position.stop_loss if trader.open_position else 0.0,
                take_profit=trader.open_position.take_profit if trader.open_position else 0.0,
                trailing_stop=trader.open_position.trailing_stop if trader.open_position else 0.0,
            )
            
            # Step 8: Add to history
            history_record = {
                "type": "manual_buy",
                "side": "buy",
                "amount": trade.amount,
                "price": trade.price,
                "notional": trade.notional,
                "fee": trade.fee,
                "usdt_balance": trade.usdt_balance,
                "base_balance": trade.base_balance,
                "timestamp": trade.timestamp,
            }
            self.app_state.add_history_record(history_record)
            
            self.logger.info(f"Manual buy executed successfully: {trade.amount} @ ${trade.price:.2f}")
            
            return {
                "success": True,
                "data": {
                    "side": trade.side,
                    "amount": trade.amount,
                    "price": trade.price,
                    "notional": trade.notional,
                    "fee": trade.fee,
                    "slippage": trade.slippage,
                    "usdt_balance": trade.usdt_balance,
                    "base_balance": trade.base_balance,
                    "timestamp": trade.timestamp,
                },
                "message": f"Buy order executed: {trade.amount:.8f} @ ${trade.price:.2f}"
            }
            
        except Exception as e:
            self.logger.error(f"Manual buy failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "Trade execution failed"
            }
    
    def execute_manual_sell(self, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute manual sell order.
        
        This method validates inputs, executes the trade via the trader instance,
        updates application state, and logs to database. If any step fails, no
        state changes occur (atomic operation).
        
        Args:
            amount: Amount to sell (in base currency or percentage)
            price: Optional limit price (not currently used for market orders)
            
        Returns:
            Trade result dictionary with success status and trade data or error
            
        Validates: Requirements 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
        """
        # Step 1: Validate amount
        if amount <= 0:
            self.logger.warning(f"Invalid sell amount: {amount}")
            return {
                "success": False,
                "error": "Amount must be greater than 0",
                "message": "Invalid trade amount"
            }
        
        # Step 2: Get trader instance
        trader = self.app_state.get_trader()
        if trader is None:
            self.logger.error("Trader instance not initialized")
            return {
                "success": False,
                "error": "Trader not initialized",
                "message": "Trading system not ready"
            }
        
        # Step 3: Validate trading is enabled
        trading_state = self.app_state.get_trading_state()
        if not trading_state.trading_enabled:
            self.logger.warning("Manual sell rejected: trading is disabled")
            return {
                "success": False,
                "error": "Trading is disabled",
                "message": "Enable trading before executing trades"
            }
        
        # Step 4: Check emergency stop
        if trading_state.emergency_stop:
            self.logger.warning("Manual sell rejected: emergency stop is active")
            return {
                "success": False,
                "error": "Emergency stop is active",
                "message": "Clear emergency stop before trading"
            }
        
        # Step 5: Create manual signal
        try:
            signal = self.create_manual_signal('bearish', amount)
        except Exception as e:
            self.logger.error(f"Failed to create manual signal: {e}")
            return {
                "success": False,
                "error": f"Signal creation failed: {str(e)}",
                "message": "Failed to prepare trade"
            }
        
        # Step 6: Execute trade
        try:
            self.logger.info(f"Executing manual sell: amount={amount}")
            
            # Execute via trader instance
            trade = trader.execute_market_sell(
                amount=amount,
                signal=signal,
                exit_reason="manual"
            )
            
            if trade is None:
                self.logger.warning("Trade execution returned None (validation failed)")
                return {
                    "success": False,
                    "error": "Trade validation failed",
                    "message": "Trade could not be executed (check logs for details)"
                }
            
            # Step 7: Update application state
            self.app_state.update_trading_state(
                usdt_balance=trader.usdt_balance,
                base_balance=trader.base_balance,
                current_price=trade.price,
                position_open=trader.open_position is not None,
                position_entry_price=trader.open_position.entry_price if trader.open_position else 0.0,
                position_amount=trader.open_position.amount if trader.open_position else 0.0,
                position_side='long' if trader.open_position else 'none',
                stop_loss=trader.open_position.stop_loss if trader.open_position else 0.0,
                take_profit=trader.open_position.take_profit if trader.open_position else 0.0,
                trailing_stop=trader.open_position.trailing_stop if trader.open_position else 0.0,
            )
            
            # Step 8: Add to history
            history_record = {
                "type": "manual_sell",
                "side": "sell",
                "amount": trade.amount,
                "price": trade.price,
                "notional": trade.notional,
                "fee": trade.fee,
                "pnl": trade.pnl,
                "exit_reason": trade.exit_reason,
                "usdt_balance": trade.usdt_balance,
                "base_balance": trade.base_balance,
                "timestamp": trade.timestamp,
            }
            self.app_state.add_history_record(history_record)
            
            pnl_str = f", P&L: ${trade.pnl:.2f}" if trade.pnl is not None else ""
            self.logger.info(f"Manual sell executed successfully: {trade.amount} @ ${trade.price:.2f}{pnl_str}")
            
            return {
                "success": True,
                "data": {
                    "side": trade.side,
                    "amount": trade.amount,
                    "price": trade.price,
                    "notional": trade.notional,
                    "fee": trade.fee,
                    "slippage": trade.slippage,
                    "pnl": trade.pnl,
                    "exit_reason": trade.exit_reason,
                    "usdt_balance": trade.usdt_balance,
                    "base_balance": trade.base_balance,
                    "timestamp": trade.timestamp,
                },
                "message": f"Sell order executed: {trade.amount:.8f} @ ${trade.price:.2f}{pnl_str}"
            }
            
        except Exception as e:
            self.logger.error(f"Manual sell failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "Trade execution failed"
            }
    
    def enable_trading(self) -> Dict[str, bool]:
        """
        Enable automated trading.
        
        Updates the trading_enabled flag in application state to allow
        trading operations to proceed.
        
        Returns:
            Dictionary with success status and trading_enabled state
            
        Validates: Requirement 4.11
        """
        try:
            self.app_state.update_trading_state(trading_enabled=True)
            self.logger.info("Trading enabled")
            
            # Also enable on trader instance if available
            trader = self.app_state.get_trader()
            if trader:
                trader.enable_trading()
            
            return {
                "success": True,
                "trading_enabled": True,
                "message": "Trading enabled successfully"
            }
        except Exception as e:
            self.logger.error(f"Failed to enable trading: {e}")
            return {
                "success": False,
                "trading_enabled": False,
                "error": str(e),
                "message": "Failed to enable trading"
            }
    
    def disable_trading(self) -> Dict[str, bool]:
        """
        Disable automated trading.
        
        Updates the trading_enabled flag in application state to prevent
        trading operations from executing.
        
        Returns:
            Dictionary with success status and trading_enabled state
            
        Validates: Requirement 4.12
        """
        try:
            self.app_state.update_trading_state(trading_enabled=False)
            self.logger.info("Trading disabled")
            
            # Also disable on trader instance if available
            trader = self.app_state.get_trader()
            if trader:
                trader.disable_trading()
            
            return {
                "success": True,
                "trading_enabled": False,
                "message": "Trading disabled successfully"
            }
        except Exception as e:
            self.logger.error(f"Failed to disable trading: {e}")
            return {
                "success": False,
                "trading_enabled": True,
                "error": str(e),
                "message": "Failed to disable trading"
            }
    
    def trigger_emergency_stop(self) -> Dict[str, Any]:
        """
        Trigger emergency stop and close all positions.
        
        This method:
        1. Sets emergency_stop flag to true
        2. Disables automated trading
        3. Attempts to close all open positions
        
        Returns:
            Dictionary with success status and emergency stop details
            
        Validates: Requirements 20.1, 20.2, 20.3, 20.4
        """
        try:
            self.logger.critical("🚨 EMERGENCY STOP TRIGGERED 🚨")
            
            # Step 1: Set emergency stop flag and disable trading
            self.app_state.update_trading_state(
                emergency_stop=True,
                trading_enabled=False
            )
            
            # Step 2: Get trader instance
            trader = self.app_state.get_trader()
            if trader is None:
                self.logger.warning("Trader not initialized, cannot close positions")
                return {
                    "success": True,
                    "emergency_stop": True,
                    "trading_enabled": False,
                    "positions_closed": False,
                    "message": "Emergency stop activated (no trader instance to close positions)"
                }
            
            # Step 3: Trigger emergency stop on trader (closes positions)
            trader.trigger_emergency_stop(close_positions=True)
            
            # Step 4: Update state after position closure
            self.app_state.update_trading_state(
                usdt_balance=trader.usdt_balance,
                base_balance=trader.base_balance,
                position_open=False,
                position_entry_price=0.0,
                position_amount=0.0,
                position_side='none',
                stop_loss=0.0,
                take_profit=0.0,
                trailing_stop=0.0,
            )
            
            # Step 5: Add to history
            history_record = {
                "type": "emergency_stop",
                "timestamp": datetime.utcnow().isoformat(),
                "message": "Emergency stop triggered - all positions closed"
            }
            self.app_state.add_history_record(history_record)
            
            self.logger.info("Emergency stop completed successfully")
            
            return {
                "success": True,
                "emergency_stop": True,
                "trading_enabled": False,
                "positions_closed": True,
                "message": "Emergency stop activated - all positions closed"
            }
            
        except Exception as e:
            self.logger.error(f"Emergency stop failed: {e}", exc_info=True)
            return {
                "success": False,
                "emergency_stop": True,
                "trading_enabled": False,
                "error": str(e),
                "message": "Emergency stop activated but position closure failed"
            }
    
    def sync_exchange_state(self) -> Dict[str, Any]:
        """
        Sync state with exchange (balances, positions).
        
        For live trading, this fetches current balances and positions from
        the exchange and updates application state. For paper trading, this
        returns current paper trading state.
        
        Returns:
            Dictionary with success status and synced state data
            
        Validates: Requirements 17.8
        """
        try:
            # Get trader instance
            trader = self.app_state.get_trader()
            if trader is None:
                self.logger.warning("Trader not initialized, cannot sync state")
                return {
                    "success": False,
                    "error": "Trader not initialized",
                    "message": "Cannot sync state without trader instance"
                }
            
            # Sync balances from exchange (or get paper trading balances)
            balances = trader.sync_balances() if hasattr(trader, 'sync_balances') else trader.get_balances()
            
            # Sync positions (if supported)
            position = None
            if hasattr(trader, 'sync_positions'):
                position = trader.sync_positions()
            elif hasattr(trader, 'open_position'):
                position = trader.open_position
            
            # Update application state
            self.app_state.update_trading_state(
                usdt_balance=trader.usdt_balance,
                base_balance=trader.base_balance,
                position_open=position is not None,
                position_entry_price=position.entry_price if position else 0.0,
                position_amount=position.amount if position else 0.0,
                position_side='long' if position else 'none',
                stop_loss=position.stop_loss if position else 0.0,
                take_profit=position.take_profit if position else 0.0,
                trailing_stop=position.trailing_stop if position else 0.0,
            )
            
            self.logger.info(f"State synced: USDT={trader.usdt_balance:.2f}, BASE={trader.base_balance:.8f}")
            
            return {
                "success": True,
                "data": {
                    "usdt_balance": trader.usdt_balance,
                    "base_balance": trader.base_balance,
                    "position_open": position is not None,
                    "position_entry_price": position.entry_price if position else 0.0,
                    "position_amount": position.amount if position else 0.0,
                },
                "message": "State synchronized successfully"
            }
            
        except Exception as e:
            self.logger.error(f"State sync failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to sync state with exchange"
            }
    
    def get_current_price(self) -> float:
        """
        Get current market price.
        
        Fetches the current market price from the exchange via the trader instance.
        
        Returns:
            Current market price as float
            
        Raises:
            Exception: If price fetch fails or trader not initialized
        """
        trader = self.app_state.get_trader()
        if trader is None:
            raise Exception("Trader not initialized")
        
        exchange = self.app_state.get_exchange()
        if exchange is None:
            raise Exception("Exchange not initialized")
        
        try:
            ticker = exchange.fetch_ticker(self.config.symbol)
            current_price = float(ticker['last'])
            self.logger.debug(f"Current price: ${current_price:.2f}")
            return current_price
        except Exception as e:
            self.logger.error(f"Failed to fetch current price: {e}")
            raise
    
    def create_manual_signal(self, direction: str, amount: float) -> Any:
        """
        Create manual trading signal.
        
        Creates a StrategySignal object for manual trades with appropriate
        stop loss and take profit levels based on configuration.
        
        Args:
            direction: Signal direction ('bullish' or 'bearish')
            amount: Trade amount
            
        Returns:
            StrategySignal object
            
        Raises:
            Exception: If signal creation fails
        """
        try:
            # Import StrategySignal (avoid circular import)
            from strategies.base import StrategySignal
            
            # Get current price
            current_price = self.get_current_price()
            
            # Calculate stop loss and take profit based on direction
            if direction == 'bullish':
                stop_loss = current_price * (1 - self.config.stop_loss_pct)
                take_profit = current_price * (1 + self.config.take_profit_pct)
            else:  # bearish
                stop_loss = current_price * (1 + self.config.stop_loss_pct)
                take_profit = current_price * (1 - self.config.take_profit_pct)
            
            # Create signal
            signal = StrategySignal(
                direction=direction,
                price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size=self.config.order_pct,
                confidence=1.0,  # Manual trades have full confidence
                strategy_name="manual",
                timestamp=datetime.utcnow().isoformat(),
                metadata={"type": "manual_trade", "amount": amount}
            )
            
            self.logger.debug(f"Created manual signal: {direction} @ ${current_price:.2f}")
            return signal
            
        except Exception as e:
            self.logger.error(f"Failed to create manual signal: {e}")
            raise

