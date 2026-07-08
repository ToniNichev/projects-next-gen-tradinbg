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
from typing import Callable, Dict, List, Optional, TYPE_CHECKING
from enum import Enum

import ccxt

if TYPE_CHECKING:
    from strategies.base_strategy import StrategySignal

try:
    from database import DatabaseManager, Trade as DBTrade, Position as DBPosition
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Retry / order-status helpers (module-level so they're easy to unit-test)
# ---------------------------------------------------------------------------

_TRANSIENT_CCXT_ERRORS = (
    ccxt.NetworkError,
    ccxt.RequestTimeout,
    ccxt.ExchangeNotAvailable,
    ccxt.DDoSProtection,
)

# Errors that should NEVER be retried — they indicate a permanent rejection
# (bad credentials, insufficient funds, malformed order).  Listing them
# explicitly so a future ccxt update doesn't silently widen the retry net.
_PERMANENT_CCXT_ERRORS = (
    ccxt.AuthenticationError,
    ccxt.PermissionDenied,
    ccxt.AccountSuspended,
    ccxt.InsufficientFunds,
    ccxt.InvalidOrder,
    ccxt.BadSymbol,
)

_TERMINAL_ORDER_STATUSES = {"closed", "canceled", "expired", "rejected"}

# Persists in ``StrategyConfig`` alongside user strategy keys — internal only.
_PEAK_PORTFOLIO_EQUITY_KEY = "BOT_INTERNAL_PEAK_PORTFOLIO_EQUITY"


def _retry_call(
    fn: Callable,
    *args,
    attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    logger: Optional[logging.Logger] = None,
    description: str = "exchange call",
    **kwargs,
):
    """
    Run ``fn(*args, **kwargs)`` retrying on transient ccxt errors only.

    Permanent errors (auth, insufficient funds, invalid order) are re-raised
    immediately so the caller can surface a clean failure to the operator
    instead of silently waiting through retries.

    Backoff is exponential: ``delay * backoff**attempt`` capped at the final
    iteration.  This is the same shape ``BOT_API_RETRY_*`` config implies.
    """
    log = logger or logging.getLogger(__name__)
    last_exc: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            return fn(*args, **kwargs)
        except _PERMANENT_CCXT_ERRORS as exc:
            log.error("%s rejected by exchange (permanent): %s", description, exc)
            raise
        except _TRANSIENT_CCXT_ERRORS as exc:
            last_exc = exc
            if attempt == attempts:
                log.error(
                    "%s failed after %d attempts: %s",
                    description, attempts, exc,
                )
                raise
            sleep_for = delay * (backoff ** (attempt - 1))
            log.warning(
                "%s transient error on attempt %d/%d (%s); retrying in %.1fs",
                description, attempt, attempts, exc, sleep_for,
            )
            time.sleep(sleep_for)

    # Defensive — should be unreachable because of the raise inside the loop.
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{description} failed without a captured exception")


def _wait_for_order_terminal(
    exchange,
    order_id: str,
    symbol: str,
    *,
    timeout_seconds: float = 10.0,
    poll_interval: float = 0.5,
    retry_attempts: int = 3,
    retry_delay: float = 1.0,
    logger: Optional[logging.Logger] = None,
) -> Dict:
    """
    Poll ``fetch_order`` until the order reaches a terminal state.

    Market orders on Binance.US usually fill instantly, but the response to
    ``create_market_*_order`` can return *before* all fills are accounted
    for, leaving ``filled`` < ``amount`` and ``status='open'``.  This helper
    waits up to ``timeout_seconds`` for the order to settle so callers always
    work with the final fill price and amount.

    Returns the final order dict from ccxt.  If the timeout elapses, returns
    the latest snapshot (the caller decides what to do — partial-fill is a
    valid live state and must not silently be treated as full).
    """
    log = logger or logging.getLogger(__name__)
    deadline = time.monotonic() + timeout_seconds
    last_order: Optional[Dict] = None

    while True:
        last_order = _retry_call(
            exchange.fetch_order,
            order_id, symbol,
            attempts=retry_attempts,
            delay=retry_delay,
            logger=log,
            description=f"fetch_order({order_id})",
        )
        status = (last_order or {}).get("status")
        if status in _TERMINAL_ORDER_STATUSES:
            return last_order
        if time.monotonic() >= deadline:
            log.warning(
                "Order %s still %s after %.1fs (filled=%.8f / %.8f); "
                "returning latest snapshot",
                order_id, status, timeout_seconds,
                float((last_order or {}).get("filled", 0.0)),
                float((last_order or {}).get("amount", 0.0)),
            )
            return last_order
        time.sleep(poll_interval)


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
    # Binance STOP_LOSS_LIMIT order id — cancelled before any intentional market sell
    exchange_stop_order_id: Optional[str] = None


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

        # Retry / partial-fill polling settings (read from config so the
        # operator can tune them without code changes; sane defaults match
        # ``BOT_API_RETRY_*`` documented in env.example).
        self.retry_attempts: int = int(getattr(config, "api_retry_attempts", 3) or 3)
        self.retry_delay: float = float(getattr(config, "api_retry_delay_seconds", 1.0) or 1.0)
        self.order_poll_timeout: float = float(getattr(config, "order_poll_timeout_seconds", 10.0) or 10.0)
        self.order_poll_interval: float = float(getattr(config, "order_poll_interval_seconds", 0.5) or 0.5)

        # DB-row id for the current open position so we can update it as the
        # trailing stop ratchets and close it cleanly on exit.
        self.db_position_id: Optional[int] = None

        # When true, ``validate_trade`` rejects new *buys* only (drawdown rule).
        # Sells that reduce risk remain permitted.
        self.portfolio_buy_halt: bool = False

        self.logger.info(f"LiveTrader initialized in {mode.value} mode")

        # Try to restore an existing open position from the database before
        # any other startup sync.  This is the source of truth for what the
        # bot considers "its own" — see ``sync_positions`` for the orphan-
        # balance guard that depends on this.
        if self.db_manager:
            try:
                self._restore_position_from_db()
            except Exception as exc:
                self.logger.warning(
                    "Could not restore open position from DB: %s", exc,
                )

        if (
            self.mode == TradingMode.LIVE
            and self.open_position
            and getattr(self.config, "exchange_stop_loss_enabled", True)
        ):
            try:
                self._sync_exchange_protective_stop()
            except Exception as exc:
                self.logger.warning(
                    "Could not re-arm exchange protective stop after startup restore: %s",
                    exc,
                )

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
        Synchronise the in-memory position with persistent state.

        Source-of-truth order:

        1. If the bot has an open position record in the database, that is
           the authoritative state — including stop-loss, take-profit and
           the current trailing-stop level.  We restore it and only verify
           that the exchange still holds enough base currency to back it.
        2. If there is **no** DB-tracked open position but the exchange
           account holds base currency above the minimum order size, we
           do **not** auto-adopt that balance.  It almost certainly came
           from outside the bot (manual trade, deposit, another tool) and
           selling it on a stop-loss could destroy user funds.  We log a
           loud warning and return ``None``.  An operator who explicitly
           wants the bot to take ownership can use a dedicated
           "claim_orphan_balance" flow (not yet implemented) or open a
           position via the dashboard.
        """
        try:
            self.sync_balances()
            base_currency = self.config.symbol.split("/")[0]
            min_position = self.get_min_order_size()

            # 1. Prefer DB state.
            db_position = self._restore_position_from_db()
            if db_position is not None:
                if self.base_balance + 1e-8 < db_position.amount:
                    self.logger.error(
                        "Exchange %s balance (%.8f) is less than the bot's "
                        "tracked position (%.8f). The position will be "
                        "trimmed to the available balance to avoid an "
                        "oversold attempt; investigate immediately.",
                        base_currency, self.base_balance, db_position.amount,
                    )
                    db_position.amount = self.base_balance
                return db_position

            # 2. No DB record.  Refuse to adopt any pre-existing balance.
            if self.base_balance > min_position:
                self.logger.warning(
                    "Exchange holds %.8f %s but bot has no recorded position. "
                    "NOT auto-adopting this balance; trading will only act on "
                    "positions opened by the bot itself.",
                    self.base_balance, base_currency,
                )

            self.open_position = None
            self.db_position_id = None
            return None

        except Exception as e:
            self.logger.error(f"Failed to sync positions: {e}")
            return None

    # ------------------------------------------------------------------
    # Database persistence
    # ------------------------------------------------------------------

    def _restore_position_from_db(self) -> Optional[LivePosition]:
        """If the DB has an open position row, hydrate it into ``self``."""
        if not self.db_manager:
            return None
        try:
            open_positions = self.db_manager.get_open_positions()
        except Exception as exc:
            self.logger.error("Failed to read open positions from DB: %s", exc)
            return None

        if not open_positions:
            return None

        # Multiple open positions are not supported in spot mode; close all
        # but the most recent in the DB to converge on a single source of
        # truth.  This is conservative — we only update flags, not balances.
        if len(open_positions) > 1:
            self.logger.warning(
                "%d open positions in DB; using the most recent and closing "
                "the others as orphaned.", len(open_positions),
            )
            for stale in open_positions[:-1]:
                try:
                    self.db_manager.update_position(
                        stale.id,
                        {"is_open": False, "exit_reason": "orphan_cleanup"},
                    )
                except Exception as exc:
                    self.logger.error(
                        "Could not flag stale DB position %s as closed: %s",
                        stale.id, exc,
                    )

        db_pos = open_positions[-1]
        raw_stop_oid = getattr(db_pos, "exchange_stop_order_id", None)
        stop_oid = raw_stop_oid.strip() if isinstance(raw_stop_oid, str) else raw_stop_oid
        stop_oid = stop_oid or None

        position = LivePosition(
            side=db_pos.side or "long",
            entry_price=float(db_pos.entry_price),
            amount=float(db_pos.amount),
            entry_time=db_pos.entry_time.isoformat() if db_pos.entry_time else datetime.now(timezone.utc).isoformat(),
            stop_loss=float(db_pos.stop_loss) if db_pos.stop_loss else 0.0,
            take_profit=float(db_pos.take_profit) if db_pos.take_profit else 0.0,
            trailing_stop=float(db_pos.trailing_stop) if db_pos.trailing_stop else 0.0,
            initial_trailing_stop_pct=self.config.trailing_stop_pct,
            entry_order_id=None,
            highest_price=float(db_pos.highest_price or db_pos.entry_price),
            lowest_price=float(db_pos.lowest_price or 0.0),
            exchange_stop_order_id=stop_oid,
        )
        self.open_position = position
        self.db_position_id = db_pos.id
        self.logger.info(
            "Restored open position from DB: %s %.8f @ $%.2f "
            "(SL=$%.2f TP=$%.2f trailing=$%.2f) row_id=%s exchange_stop=%s",
            position.side, position.amount, position.entry_price,
            position.stop_loss, position.take_profit, position.trailing_stop,
            db_pos.id,
            stop_oid or "none",
        )
        return position

    def _save_position_to_db(self, position: LivePosition) -> None:
        """Insert a new open position row and remember its id."""
        if not self.db_manager:
            return
        try:
            entry_time = position.entry_time
            if isinstance(entry_time, str):
                try:
                    entry_time = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
                except ValueError:
                    entry_time = datetime.now(timezone.utc)

            row = self.db_manager.add_position({
                "side": position.side,
                "entry_price": position.entry_price,
                "entry_time": entry_time,
                "amount": position.amount,
                "stop_loss": position.stop_loss,
                "take_profit": position.take_profit,
                "trailing_stop": position.trailing_stop,
                "highest_price": position.highest_price,
                "lowest_price": position.lowest_price,
                "is_open": True,
                "strategy_name": "live_trader",
                "exchange_stop_order_id": position.exchange_stop_order_id,
            })
            self.db_position_id = row.id
            self.logger.debug("Saved open position to DB row %s", row.id)
        except Exception as exc:
            # DB failure must not abort a real order that already executed.
            self.logger.error("Failed to persist open position: %s", exc, exc_info=True)

    def _update_open_position_in_db(self) -> None:
        """Push current trailing-stop / highest_price back to the DB row."""
        if not self.db_manager or not self.db_position_id or not self.open_position:
            return
        try:
            self.db_manager.update_position(self.db_position_id, {
                "trailing_stop": self.open_position.trailing_stop,
                "highest_price": self.open_position.highest_price,
                "stop_loss": self.open_position.stop_loss,
                "take_profit": self.open_position.take_profit,
                "amount": self.open_position.amount,
                "exchange_stop_order_id": self.open_position.exchange_stop_order_id,
            })
        except Exception as exc:
            self.logger.error("Failed to update open position in DB: %s", exc)

    def _close_position_in_db(
        self,
        exit_price: float,
        exit_reason: str,
        pnl: Optional[float],
    ) -> None:
        """Mark the DB row closed with exit price + P&L."""
        if not self.db_manager or not self.db_position_id:
            return
        try:
            entry_cost = 0.0
            if self.open_position:
                entry_cost = self.open_position.amount * self.open_position.entry_price
            pnl_pct = (pnl / entry_cost * 100.0) if (pnl is not None and entry_cost > 0) else None

            self.db_manager.update_position(self.db_position_id, {
                "exit_price": exit_price,
                "exit_time": datetime.now(timezone.utc),
                "exit_reason": exit_reason,
                "pnl": pnl,
                "pnl_percent": pnl_pct,
                "is_open": False,
                "exchange_stop_order_id": None,
            })
        except Exception as exc:
            self.logger.error("Failed to mark DB position closed: %s", exc)
        finally:
            self.db_position_id = None

    # ------------------------------------------------------------------
    # Exchange-native protective stop (Binance spot STOP_LOSS_LIMIT)
    # ------------------------------------------------------------------

    def _effective_protective_trigger(self, pos: LivePosition) -> float:
        """Price level at which a protective sell should trigger (long)."""
        return max(float(pos.stop_loss), float(pos.trailing_stop))

    def _cancel_exchange_protective_stop(self) -> None:
        """Cancel the optional STOP_LOSS_LIMIT resting on the exchange."""
        if not self.open_position or not self.open_position.exchange_stop_order_id:
            return
        oid = self.open_position.exchange_stop_order_id
        sym = self.config.symbol
        try:
            _retry_call(
                self.exchange.cancel_order,
                oid, sym,
                attempts=self.retry_attempts,
                delay=self.retry_delay,
                logger=self.logger,
                description=f"cancel_protective_stop({oid})",
            )
            self.logger.info("Cancelled exchange protective stop order %s", oid)
        except Exception as exc:
            self.logger.warning(
                "Could not cancel protective stop %s (may already be filled): %s",
                oid, exc,
            )
        finally:
            self.open_position.exchange_stop_order_id = None
            self._update_open_position_in_db()

    def _sync_exchange_protective_stop(self) -> None:
        """
        Place a STOP_LOSS_LIMIT sell that mirrors the higher of the fixed
        stop-loss and the trailed stop.  Only in LIVE mode with the feature
        flag enabled.

        Failure logs a warning but does not unwind the spot position — the
        in-process ``update_position`` loop remains the last line of defence.
        """
        if self.mode != TradingMode.LIVE:
            return
        if not getattr(self.config, "exchange_stop_loss_enabled", True):
            return
        if not self.open_position or self.open_position.side != "long":
            return

        pos = self.open_position
        trigger = self._effective_protective_trigger(pos)
        trigger = self.round_price(trigger)
        # Binance requires limit < stop for auction — sell limit slightly
        # below the trigger so that when the stop fires, the limit rests
        # inside executable range.
        limit_px = self.round_price(trigger * 0.998)
        if limit_px >= trigger:
            limit_px = self.round_price(trigger * 0.995)

        qty = self.round_amount(pos.amount)
        if qty <= 0:
            return

        # Replace existing bracket
        self._cancel_exchange_protective_stop()

        try:
            order = _retry_call(
                self.exchange.create_order,
                self.config.symbol,
                "STOP_LOSS_LIMIT",
                "sell",
                qty,
                limit_px,
                {"stopPrice": trigger, "timeInForce": "GTC"},
                attempts=self.retry_attempts,
                delay=self.retry_delay,
                logger=self.logger,
                description="STOP_LOSS_LIMIT protective sell",
            )
            oid = str(order.get("id", "") or "")
            if oid:
                pos.exchange_stop_order_id = oid
            self._update_open_position_in_db()
            self.logger.info(
                "Exchange protective stop armed: qty=%.8f trigger=$%.4f limit=$%.4f order=%s",
                qty, trigger, limit_px, oid or "?",
            )
        except Exception as exc:
            self.logger.error(
                "Failed to place exchange protective STOP_LOSS_LIMIT: %s. "
                "Software stops still active.",
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Peak portfolio equity → drawdown kill-switch (buys only)
    # ------------------------------------------------------------------

    def _check_portfolio_peak_drawdown(self, side: str, price: float) -> tuple[bool, str]:
        if side != "buy":
            return True, ""
        if not getattr(self.config, "portfolio_drawdown_kill_enabled", True):
            return True, ""
        if not self.db_manager:
            return True, ""
        try:
            row = self.db_manager.get_strategy_config(_PEAK_PORTFOLIO_EQUITY_KEY)
            peak = float(row.value) if row and row.value else 0.0
        except Exception as exc:
            self.logger.debug("Could not read peak equity: %s", exc)
            return True, ""

        equity = float(self.usdt_balance) + float(self.base_balance) * float(price)
        if peak <= 0 or equity > peak:
            peak = max(peak, equity) if peak > 0 else equity
            try:
                self.db_manager.set_strategy_config(
                    _PEAK_PORTFOLIO_EQUITY_KEY,
                    str(peak),
                    "float",
                    "risk",
                    "Internal: peak portfolio equity (USDT) for drawdown limit",
                )
            except Exception as exc:
                self.logger.warning("Could not persist peak equity: %s", exc)

        if peak <= 0:
            return True, ""
        dd = (peak - equity) / peak
        max_dd = float(self.config.max_portfolio_drawdown)
        if dd >= max_dd:
            self.portfolio_buy_halt = True
            try:
                from notify import send_notification

                send_notification(
                    "Portfolio drawdown halt",
                    f"Peak ${peak:.2f}  current equity ${equity:.2f}  "
                    f"DD {dd * 100:.2f}% (limit {max_dd * 100:.2f}%). "
                    f"New buys disabled; sells still allowed.",
                    severity="critical",
                )
            except Exception:
                pass
            return (
                False,
                f"Portfolio drawdown {dd * 100:.2f}% from peak exceeds "
                f"{max_dd * 100:.2f}% — new buys disabled",
            )
        return True, ""
    
    # =========================================================================
    # Pre-Trade Validation
    # =========================================================================
    
    def validate_trade(
        self,
        side: str,
        amount: float,
        price: float,
        *,
        is_closing_sell: bool = False,
        is_emergency_close: bool = False,
    ) -> tuple[bool, str]:
        """
        Validate trade before execution.

        Args:
            side: 'buy' or 'sell'
            amount: Amount to trade
            price: Current price
            is_closing_sell: True for any sell that reduces or closes an
                existing position — software stop-loss/take-profit/trailing
                -stop exits, a signal-reversal close, or a manual sell.
                Bypasses the entry-side risk gates (trading_enabled, daily
                trade/loss limits, max-single-trade cap, confirmation
                threshold): those exist to stop *new* risk from being taken,
                not to trap the risk engine — or the operator — inside a
                position it is trying to exit. Does NOT bypass
                emergency_stop; once that is set, only the emergency-stop's
                own close (``is_emergency_close``) may sell.
            is_emergency_close: True only for the single closing sell issued
                by ``trigger_emergency_stop``. Implies ``is_closing_sell``
                and additionally bypasses ``emergency_stop`` itself — without
                this the panic button would be a no-op, since it always
                fires while ``self.emergency_stop`` is already True. Balance
                and minimum-size checks still apply in all cases since those
                reflect what the exchange will actually accept.

        Returns:
            (is_valid, error_message)
        """
        bypass_entry_gates = is_closing_sell or is_emergency_close

        if not is_emergency_close:
            # Check emergency stop
            if self.emergency_stop:
                return False, "Emergency stop is active"

        if not bypass_entry_gates:
            # Check if trading is enabled
            if not self.trading_enabled:
                return False, "Trading is disabled"

        if side == "buy" and self.portfolio_buy_halt:
            return (
                False,
                "New buys halted — portfolio drawdown reached the configured limit earlier",
            )

        ok_peak, peak_msg = self._check_portfolio_peak_drawdown(side, price)
        if not ok_peak:
            return False, peak_msg

        # Check daily reset
        self._check_daily_reset()

        if not bypass_entry_gates:
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

        if not bypass_entry_gates:
            # Hard cap on single-trade USD size. Documented in env.example as
            # BOT_MAX_SINGLE_TRADE_USD. Enforced here so that automated signals
            # cannot ever submit an order larger than the operator-configured
            # ceiling, even if a strategy mis-sizes a position.
            max_single_trade_usd = getattr(self.config, "max_single_trade_usd", 0.0) or 0.0
            if max_single_trade_usd > 0 and notional > max_single_trade_usd:
                return False, (
                    f"Notional ${notional:.2f} exceeds max single-trade cap "
                    f"${max_single_trade_usd:.2f} (BOT_MAX_SINGLE_TRADE_USD)"
                )

            # Confirmation gate. In the absence of an interactive confirmation
            # channel, BOT_REQUIRE_TRADE_CONFIRMATION=true blocks any automated
            # trade above BOT_CONFIRMATION_THRESHOLD_USD; the operator must
            # explicitly raise the threshold or disable confirmation before
            # such a trade can run unattended.
            require_confirmation = getattr(self.config, "require_trade_confirmation", False)
            confirmation_threshold = getattr(self.config, "confirmation_threshold_usd", 0.0) or 0.0
            if require_confirmation and notional > confirmation_threshold:
                return False, (
                    f"Notional ${notional:.2f} exceeds confirmation threshold "
                    f"${confirmation_threshold:.2f} (BOT_REQUIRE_TRADE_CONFIRMATION=true). "
                    f"Lower position size, raise BOT_CONFIRMATION_THRESHOLD_USD, or set "
                    f"BOT_REQUIRE_TRADE_CONFIRMATION=false."
                )

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

            order = _retry_call(
                self.exchange.create_market_buy_order,
                symbol=symbol,
                amount=amount,
                attempts=self.retry_attempts,
                delay=self.retry_delay,
                logger=self.logger,
                description=f"create_market_buy_order({amount} {symbol})",
            )

            order_record = self._parse_order(order)

            # Poll until the order reaches a terminal state so partial fills
            # are accounted for instead of silently treated as full.
            order_id = order_record.order_id
            if order_id:
                try:
                    final_order = _wait_for_order_terminal(
                        self.exchange, order_id, symbol,
                        timeout_seconds=self.order_poll_timeout,
                        poll_interval=self.order_poll_interval,
                        retry_attempts=self.retry_attempts,
                        retry_delay=self.retry_delay,
                        logger=self.logger,
                    )
                    order = final_order or order
                    order_record = self._parse_order(order)
                except Exception as exc:
                    self.logger.warning(
                        "Could not poll order %s to terminal state (%s); "
                        "proceeding with initial response.",
                        order_id, exc,
                    )

            self.completed_orders.append(order_record)

            # Use exchange-reported fills; fall back to requested amount only
            # if the exchange returned no fill data at all.
            fill_price = float(order.get("average") or order.get("price") or current_price)
            filled_amount = float(order.get("filled") or 0.0)
            requested_amount = amount

            if filled_amount <= 0.0:
                self.logger.error(
                    "Market BUY for %s reported zero fills (status=%s). "
                    "Treating as failed; no position opened.",
                    symbol, order.get("status"),
                )
                # Refresh balances anyway so state isn't stale.
                try:
                    self.sync_balances()
                except Exception:
                    pass
                return None

            if filled_amount + 1e-12 < requested_amount:
                self.logger.warning(
                    "Partial fill: requested %.8f, got %.8f (%.2f%%). "
                    "Position opened for the filled amount only.",
                    requested_amount, filled_amount,
                    100.0 * filled_amount / requested_amount,
                )

            # Refresh USDT/BASE balances after the fill.
            self.sync_balances()

            fee_info = order.get("fee") or {}
            fee = float(fee_info.get("cost") or filled_amount * fill_price * self.config.fee_rate)
            notional = filled_amount * fill_price
            slippage = fill_price - current_price

            trade = TradeRecord(
                side="buy",
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

            # Open + persist position (uses the actual filled amount, not
            # the requested amount).
            self._open_long_position(fill_price, filled_amount, signal, order_record.order_id)

            self._sync_exchange_protective_stop()

            self.daily_trades += 1
            self.total_trades += 1
            self._log_trade(trade)

            self.logger.info(
                "BUY executed: %.8f @ $%.2f (fee=$%.4f slippage=$%.4f)",
                filled_amount, fill_price, fee, slippage,
            )
            return trade

        except _PERMANENT_CCXT_ERRORS as exc:
            # Permanent rejection — surface as a clean failure, not a crash.
            self.logger.error("Market BUY rejected by exchange: %s", exc)
            return None
        except Exception as e:
            self.logger.error(f"Market buy failed: {e}", exc_info=True)
            raise
    
    def execute_market_sell(
        self,
        amount: float,
        signal: Optional["StrategySignal"] = None,
        exit_reason: str = "signal",
        is_closing_sell: bool = False,
        is_emergency_close: bool = False,
    ) -> Optional[TradeRecord]:
        """
        Execute a market sell order.

        Args:
            amount: Amount of base currency to sell
            signal: Optional strategy signal
            exit_reason: Reason for exit (signal, stop_loss, take_profit, etc.)
            is_closing_sell: True for any sell that reduces/closes an
                existing position — see ``validate_trade``.
            is_emergency_close: True only for the closing sell issued by
                ``trigger_emergency_stop`` — see ``validate_trade``.

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
        is_valid, error_msg = self.validate_trade(
            'sell', amount, current_price,
            is_closing_sell=is_closing_sell,
            is_emergency_close=is_emergency_close,
        )
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

            # Release coins locked by the resting STOP_LOSS_LIMIT before we
            # submit a market sell for the same asset.
            self._cancel_exchange_protective_stop()

            order = _retry_call(
                self.exchange.create_market_sell_order,
                symbol=symbol,
                amount=amount,
                attempts=self.retry_attempts,
                delay=self.retry_delay,
                logger=self.logger,
                description=f"create_market_sell_order({amount} {symbol})",
            )

            order_record = self._parse_order(order)

            # Poll until the order is terminal so we use real fill data.
            order_id = order_record.order_id
            if order_id:
                try:
                    final_order = _wait_for_order_terminal(
                        self.exchange, order_id, symbol,
                        timeout_seconds=self.order_poll_timeout,
                        poll_interval=self.order_poll_interval,
                        retry_attempts=self.retry_attempts,
                        retry_delay=self.retry_delay,
                        logger=self.logger,
                    )
                    order = final_order or order
                    order_record = self._parse_order(order)
                except Exception as exc:
                    self.logger.warning(
                        "Could not poll sell order %s to terminal state (%s); "
                        "proceeding with initial response.",
                        order_id, exc,
                    )

            self.completed_orders.append(order_record)

            fill_price = float(order.get("average") or order.get("price") or current_price)
            filled_amount = float(order.get("filled") or 0.0)
            if filled_amount <= 0.0:
                self.logger.error(
                    "Market SELL for %s reported zero fills (status=%s). "
                    "Position state preserved; investigate before retrying.",
                    symbol, order.get("status"),
                )
                return None
            if filled_amount + 1e-12 < amount:
                self.logger.warning(
                    "Partial sell: requested %.8f, got %.8f (%.2f%%). "
                    "Open position will be reduced by the filled amount only.",
                    amount, filled_amount, 100.0 * filled_amount / amount,
                )

            fee_info = order.get("fee") or {}
            fee = float(fee_info.get("cost") or filled_amount * fill_price * self.config.fee_rate)

            notional = filled_amount * fill_price
            slippage = current_price - fill_price

            # Realised P&L on *this fill*'s cost basis only.
            pnl = None
            if self.open_position and self.open_position.side == "long":
                cost_basis = self.open_position.entry_price * filled_amount
                exit_value = filled_amount * fill_price
                pnl = exit_value - cost_basis - fee
                self.total_pnl += pnl
                self.daily_pnl += pnl
                if pnl > 0:
                    self.winning_trades += 1

            # Balances for logging reflect the exchange state post-fill.
            self.sync_balances()

            trade = TradeRecord(
                side="sell",
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

            pos = self.open_position
            is_full_exit = pos is None or filled_amount + 1e-10 >= pos.amount

            if is_full_exit:
                self._close_position_in_db(fill_price, exit_reason, pnl)
                self.open_position = None
            else:
                if pos:
                    pos.amount -= filled_amount
                    pos.amount = self.round_amount(max(pos.amount, 0.0))
                self._update_open_position_in_db()
                self._sync_exchange_protective_stop()

            self.daily_trades += 1
            self.total_trades += 1
            self._log_trade(trade)

            pnl_for_log = pnl if pnl is not None else 0.0
            self.logger.info(
                "SELL executed: %.8f @ $%.2f (fee=$%.4f P&L=$%.2f reason=%s)",
                filled_amount, fill_price, fee, pnl_for_log, exit_reason,
            )
            return trade

        except _PERMANENT_CCXT_ERRORS as exc:
            self.logger.error("Market SELL rejected by exchange: %s", exc)
            return None
        except Exception as e:
            self.logger.error(f"Market sell failed: {e}", exc_info=True)
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
        """Open a new long position and persist it to the DB."""
        stop_loss = signal.stop_loss if signal and signal.stop_loss > 0 else entry_price * (1 - self.config.stop_loss_pct)
        take_profit = signal.take_profit if signal and signal.take_profit > 0 else entry_price * (1 + self.config.take_profit_pct)
        trailing_stop = entry_price * (1 - self.config.trailing_stop_pct)

        self.open_position = LivePosition(
            side="long",
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

        # Persist immediately so a crash between buy fill and the next
        # update_position() call does not lose SL/TP/trailing-stop levels.
        self._save_position_to_db(self.open_position)

        self.logger.info(
            "Position opened: LONG %.8f @ $%.2f | SL=$%.2f TP=$%.2f trailing=$%.2f db_id=%s",
            amount, entry_price, stop_loss, take_profit, trailing_stop,
            self.db_position_id,
        )

    def _alert_protective_exit_failed(self, exit_reason: str, price: float) -> None:
        """
        A stop-loss/take-profit/trailing-stop/signal exit was rejected by
        validate_trade (e.g. insufficient balance) and the position remains
        open. This should be rare now that closing sells bypass the
        entry-side risk gates, but it's exactly the moment an operator needs
        to know about, so alert loudly instead of leaving it as a WARNING
        buried in the log.
        """
        self.logger.critical(
            "Protective exit (%s) FAILED at $%.2f — position remains open. "
            "Manual intervention required.",
            exit_reason, price,
        )
        try:
            from notify import send_notification

            send_notification(
                f"🚨 Protective exit failed ({exit_reason})",
                f"{self.config.symbol}: attempted {exit_reason} exit at "
                f"${price:.2f} but the sell was rejected. Position remains "
                f"open — manual intervention required.",
                severity="critical",
            )
        except Exception:
            pass

    def update_position(self, current_price: float) -> Optional[TradeRecord]:
        """
        Update the open position and check for exit conditions.

        When the trailing stop ratchets up we also persist the new level so
        a restart resumes from the protected high-water mark instead of
        rolling back to the original entry-based level.
        """
        if not self.open_position:
            return None

        pos = self.open_position
        exit_reason = None
        ratcheted = False

        if pos.side == "long":
            if self.config.use_trailing_stop:
                if current_price > pos.highest_price:
                    pos.highest_price = current_price
                    new_trailing = current_price * (1 - pos.initial_trailing_stop_pct)
                    if new_trailing > pos.trailing_stop:
                        pos.trailing_stop = new_trailing
                        ratcheted = True
                        self.logger.debug(
                            "Trailing stop ratcheted to $%.2f (high $%.2f)",
                            pos.trailing_stop, pos.highest_price,
                        )

            if current_price <= pos.stop_loss:
                exit_reason = "stop_loss"
            elif current_price >= pos.take_profit:
                exit_reason = "take_profit"
            elif self.config.use_trailing_stop and current_price <= pos.trailing_stop:
                exit_reason = "trailing_stop"

        if ratcheted and not exit_reason:
            self._update_open_position_in_db()
            if getattr(self.config, "exchange_stop_update_on_trailing", True):
                self._sync_exchange_protective_stop()

        if exit_reason:
            self.logger.info("Exit triggered: %s at $%.2f", exit_reason, current_price)
            trade = self.execute_market_sell(
                amount=pos.amount,
                signal=None,
                exit_reason=exit_reason,
                is_closing_sell=True,
            )
            if trade is None:
                self._alert_protective_exit_failed(exit_reason, current_price)
            return trade

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
                trade = self.execute_market_sell(
                    amount=self.open_position.amount,
                    signal=signal,
                    exit_reason="signal",
                    is_closing_sell=True,
                )
                if trade is None:
                    self._alert_protective_exit_failed("signal", signal.price)
                return trade

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
                is_closing_sell=True,
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
        if self.open_position and self.open_position.side == "long":
            entry_cost = self.open_position.amount * self.open_position.entry_price
            pnl = (notional - fee) - entry_cost
            self.total_pnl += pnl
            self.daily_pnl += pnl
            if pnl > 0:
                self.winning_trades += 1

        self.base_balance -= amount
        self.usdt_balance += (notional - fee)

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
            signal=signal.to_dict() if signal else {},
            exit_reason=exit_reason,
            pnl=pnl,
        )

        # Mark the open DB row as closed before clearing the in-memory ref.
        self._close_position_in_db(fill_price, exit_reason, pnl)
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
                        "strategy_name": trade.signal.get("strategy_name"),
                        "signal_confidence": trade.signal.get("confidence"),
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

        try:
            from notify import send_notification
            pos_info = (
                f" Open position: {self.open_position.amount} {self.config.symbol} will be closed."
                if close_positions and self.open_position else ""
            )
            send_notification(
                "🚨 Emergency stop triggered",
                f"All trading halted on {self.config.symbol}.{pos_info} Manual reset required.",
                severity="critical",
            )
        except Exception:
            pass

        if close_positions and self.open_position:
            self.logger.info("Closing all positions...")
            try:
                trade = self.execute_market_sell(
                    amount=self.open_position.amount,
                    signal=None,
                    exit_reason="emergency_stop",
                    is_emergency_close=True,
                )
                if trade is None:
                    self.logger.critical(
                        "Emergency stop: position close FAILED — manual "
                        "intervention required. The exchange-side protective "
                        "stop (if armed) is the only remaining defence."
                    )
                    try:
                        from notify import send_notification

                        send_notification(
                            "🚨 Emergency stop: close FAILED",
                            f"Could not close open position on {self.config.symbol} "
                            f"during emergency stop. Manual intervention required.",
                            severity="critical",
                        )
                    except Exception:
                        pass
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
