"""
Money pots: separate shares of one account, each with its own cash and BTC.

    trend     Trend Hold, as it runs on its own
    intraday  one shorter-term strategy, capped at N buys per UTC day
    manual    trades placed from the dashboard

A pot only ever trades its own coins, so Trend Hold can't sell the intraday
strategy's BTC, and a manual sell isn't bought back at the next check.

Every trade and position row in the database is tagged with its pot. A pot's
cash and BTC are restored from its latest trade (or start at its budget). In
live mode each pot keeps its own ledger inside the one exchange account, can
spend no more than that ledger or than the exchange has free, and the pots
are checked every hour against what the exchange really holds.

Live and paper pots use different tags ("live-trend" vs "trend") so going
live starts the live pots fresh instead of from the paper balances.
"""

import logging
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from paper_trader import PaperTrader
from strategies.constants import StrategyNames

try:
    from live_trader import LiveTrader, TradingMode, _PEAK_PORTFOLIO_EQUITY_KEY as PEAK_EQUITY_KEY
    LIVE_TRADER_AVAILABLE = True
except ImportError:  # pragma: no cover
    PEAK_EQUITY_KEY = "BOT_INTERNAL_PEAK_PORTFOLIO_EQUITY"
    LIVE_TRADER_AVAILABLE = False
    LiveTrader = object  # type: ignore

logger = logging.getLogger(__name__)


def _timeframe_ms(timeframe: str) -> Optional[int]:
    """'1h' -> 3600000 (None if unknown)."""
    m = re.fullmatch(r"(\d+)([mhdw])", str(timeframe or ""))
    if not m:
        return None
    return int(m.group(1)) * {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}[m.group(2)]

POT_TREND = "trend"
POT_INTRADAY = "intraday"
POT_MANUAL = "manual"
LIVE_TAG_PREFIX = "live-"
# Cash on the exchange that belongs to no pot (new deposits, or money taken
# out of a pot); in paper mode, "new paper money"
UNASSIGNED = "unassigned"

# BOT_POT_INTRADAY_STRATEGY value -> strategy name
INTRADAY_STRATEGIES = {
    "rsi_bb": StrategyNames.RSI_BB_MEAN_REVERSION,
    "ema_crossover": StrategyNames.EMA_CROSSOVER,
    "ema": StrategyNames.EMA_CROSSOVER,
    "macd_volume": StrategyNames.MACD_VOLUME_MOMENTUM,
    "macd": StrategyNames.MACD_VOLUME_MOMENTUM,
}

# Strategies an added pot can run (BOT_POTS_EXTRA / dashboard key -> name).
# Not the AI pattern strategy: it can take a minute per check.
POT_STRATEGIES = {"trend_hold": StrategyNames.TREND_HOLD, **INTRADAY_STRATEGIES}
# One key per strategy, for the dashboard's list
POT_STRATEGY_CHOICES = ["trend_hold", "rsi_bb", "ema_crossover", "macd_volume"]

BUILTIN_POTS = (POT_TREND, POT_INTRADAY, POT_MANUAL)
_POT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,11}$")
POT_COLORS = {POT_TREND: "#FFD700", POT_INTRADAY: "#FF6B9D", POT_MANUAL: "#00D9FF"}
_EXTRA_COLORS = ["#7EE787", "#B392F0", "#FFA657", "#56D4DD", "#F778BA", "#D2A8FF", "#E3B341", "#A5D6FF"]
_POT_LETTERS = {POT_TREND: "T", POT_INTRADAY: "I", POT_MANUAL: "M"}

# A stop more than 80% below entry is a "no stop" placeholder (Trend Hold)
_NO_STOP_FRACTION = 0.2


def pot_tag(name: str, live: bool) -> str:
    """Database tag for a pot; live pots are kept apart from paper ones."""
    return f"{LIVE_TAG_PREFIX}{name}" if live else name


def _utc_day_start() -> datetime:
    """Start of today (UTC), naive, the way trade timestamps are stored."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


# ---------------------------------------------------------------------------
# Live trader that keeps one pot's share of the exchange account
# ---------------------------------------------------------------------------

class PotLiveTrader(LiveTrader):
    """A LiveTrader whose cash and BTC are its pot's ledger, not the whole
    exchange balance. Orders still go to the real exchange."""

    # Re-read the exchange's free cash before spending if older than this
    EXCHANGE_REFRESH_SECONDS = 30.0
    # The stop check at start-up waits until the pot's books are complete
    # (PotManager.startup_stop_sync, run by build_pots)
    DEFER_STARTUP_STOP_SYNC = True

    def __init__(self, exchange, config, mode, db_manager, pot: str, budget: float):
        self.pot = pot
        self.pot_budget = float(budget)
        self.exchange_balances: Optional[Dict[str, float]] = None
        self._exchange_synced_at = 0.0
        super().__init__(exchange, config, mode=mode, db_manager=db_manager)
        self.initial_usdt = self.pot_budget
        self.usdt_balance, self.base_balance = self._restore_ledger()
        self.reserved_balance = self.usdt_balance * 0.001
        self.needs_check = self._read_needs_check()
        self.logger.info(
            "Pot %s: cash $%.2f, BTC %.8f (budget $%.2f)",
            self.pot, self.usdt_balance, self.base_balance, self.pot_budget,
        )
        if self.needs_check:
            self.logger.critical("Pot %s: trading stopped until checked: %s", self.pot, self.needs_check)

    def _full_close_amount(self, amount: float) -> float:
        """A sell that closes the position sells all of this pot's BTC that
        the exchange will take, not only the last purchase. Each buy leaves
        a sliver below the exchange's 0.00001 BTC step (the fee is taken in
        BTC and sells round down); before, those slivers piled up in the pot,
        about $0.77 per round trip, and no sell ever included them."""
        pos = self.open_position
        if pos is None or amount + 1e-12 < self.round_amount(pos.amount):
            return amount  # nothing open, or selling only part of it
        return max(amount, self.round_amount(self.base_balance))

    def _needs_check_key(self) -> str:
        return f"BOT_INTERNAL_POT_NEEDS_CHECK_{self.pot}"

    def _read_needs_check(self) -> Optional[str]:
        if not self.db_manager:
            return None
        try:
            row = self.db_manager.get_strategy_config(self._needs_check_key())
            return (str(row.value) or None) if row and row.value else None
        except Exception as exc:
            self.logger.error("Pot %s: could not read its 'needs check' flag: %s", self.pot, exc)
            return None

    def _save_needs_check(self) -> None:
        if self.db_manager:
            self.db_manager.set_strategy_config(
                self._needs_check_key(), self.needs_check or "", "str", "pots",
                "Internal: an order went through but wasn't recorded; trading stopped until checked",
            )

    def _restore_ledger(self):
        """(cash, btc) from this pot's latest trade, else its budget."""
        if self.db_manager:
            try:
                last = self.db_manager.get_trades(limit=1, pot=self.pot)
                if last:
                    return float(last[0].usdt_balance), float(last[0].base_balance)
            except Exception as exc:
                self.logger.error("Pot %s: could not read its trades: %s", self.pot, exc)
        return self.pot_budget, 0.0

    def _currencies(self):
        base, quote = self.config.symbol.split("/")
        return base.upper(), quote.upper()

    def sync_balances(self) -> Dict[str, float]:
        """Read the exchange balance (for limits and checks); the pot's own
        cash and BTC stay as booked."""
        if self.mode == TradingMode.DRY_RUN:
            return super().sync_balances()
        balance = self.exchange.fetch_balance()
        base, quote = self._currencies()
        q, b = balance.get(quote, {}) or {}, balance.get(base, {}) or {}
        self.exchange_balances = {
            "USDT_free": float(q.get("free") or 0.0),
            "USDT_total": float(q.get("total") or 0.0),
            "BASE_free": float(b.get("free") or 0.0),
            "BASE_total": float(b.get("total") or 0.0),
        }
        self._exchange_synced_at = time.monotonic()
        self.reserved_balance = self.usdt_balance * 0.001
        return {
            "USDT": self.usdt_balance,
            "BASE": self.base_balance,
            **{f"exchange_{k}": v for k, v in self.exchange_balances.items()},
        }

    def get_available_usdt(self) -> float:
        """The pot's cash, but never more than the exchange has free."""
        own = max(0.0, self.usdt_balance - self.reserved_balance)
        if self.mode == TradingMode.DRY_RUN:
            return own
        if time.monotonic() - self._exchange_synced_at > self.EXCHANGE_REFRESH_SECONDS:
            try:
                self.sync_balances()
            except Exception as exc:
                self.logger.warning("Pot %s: exchange balance unavailable (%s); not buying", self.pot, exc)
                return 0.0
        free = (self.exchange_balances or {}).get("USDT_free", 0.0)
        return max(0.0, min(own, free * 0.999))

    def _apply_fill(self, side, filled_amount, notional, fee, fee_currency, position_amount) -> None:
        base, quote = self._currencies()
        fee_cur = (fee_currency or quote).upper()
        fee_in_quote = fee if fee_cur == quote else 0.0
        if side == "buy":
            cost = notional + fee_in_quote
            if cost > self.usdt_balance + 0.01:
                self.logger.warning(
                    "Pot %s: buy cost $%.2f is more than its cash $%.2f",
                    self.pot, cost, self.usdt_balance,
                )
            self.usdt_balance = max(0.0, self.usdt_balance - cost)
            self.base_balance += position_amount  # already net of a BTC fee
        else:
            self.usdt_balance += notional - fee_in_quote
            self.base_balance -= filled_amount
            if fee_cur == base:
                self.base_balance -= fee
            self.base_balance = max(0.0, self.base_balance)
        self.reserved_balance = self.usdt_balance * 0.001


# ---------------------------------------------------------------------------
# Pots and the manager that runs them
# ---------------------------------------------------------------------------

@dataclass
class Pot:
    name: str
    label: str
    trader: object
    budget: float
    start_value: float
    strategy: Optional[object] = None      # None = manual only
    order_pct: Optional[float] = None      # None = use the signal's size
    max_buys_per_day: int = 0              # 0 = no cap
    last_signal: Optional[object] = None
    last_note: Optional[str] = None
    start_time: Optional[datetime] = None  # when the pot began (UTC, naive)
    paused: bool = False                   # True = no new buys until resumed
    source: str = "builtin"                # builtin | env (BOT_POTS_EXTRA) | dashboard
    _buys: Dict[str, int] = field(default_factory=dict)  # no-DB fallback

    @property
    def tag(self) -> str:
        return self.trader.pot

    @property
    def holding(self) -> bool:
        return self.trader.open_position is not None

    def balances(self) -> Dict[str, float]:
        return self.trader.get_balances()

    def value(self, price: float) -> float:
        b = self.balances()
        return float(b["USDT"]) + float(b["BASE"]) * float(price)


class PotActionError(ValueError):
    """A sell-now / pause request that can't be done (shown to the user)."""


class TransferError(ValueError):
    """A cash move that isn't allowed (shown to the user as is)."""


class PotManager:
    def __init__(
        self,
        pots: List[Pot],
        *,
        live: bool,
        notify: Optional[Callable] = None,
        trade_alerts: bool = True,
        db=None,
    ):
        self.pots: Dict[str, Pot] = {p.name: p for p in pots}
        self.live = live
        self.notify = notify
        self.trade_alerts = trade_alerts
        self.db = db  # where cash moves are saved (None in a dry run)
        self._transfers: List[Dict] = []  # this run's moves when there's no db
        self._mismatch_alerted = False
        self._excess_alerted = False
        # Pots don't match the exchange: {"cash", "btc", "text", "since"}.
        # Stays until a person clears it (clear_mismatch), even if the
        # numbers later agree, and survives a restart.
        self.mismatch: Optional[Dict] = None
        # Set by build_pots so pots can be added while the bot runs
        self._make_trader: Optional[Callable] = None
        self._strategy_manager = None

    def get(self, name: str) -> Optional[Pot]:
        return self.pots.get(name)

    def traders(self) -> List[object]:
        return [p.trader for p in self.pots.values()]

    # -------------------------------------------------------------- daily cap

    def buys_today(self, pot: Pot) -> int:
        db = getattr(pot.trader, "db_manager", None)
        if db is not None and getattr(pot.trader, "enable_database", True):
            try:
                return db.count_trades(pot=pot.tag, side="buy", since=_utc_day_start())
            except Exception as exc:
                logger.warning("Pot %s: could not count today's buys: %s", pot.name, exc)
        return pot._buys.get(_utc_day_start().date().isoformat(), 0)

    def cap_reached(self, pot: Pot) -> bool:
        return pot.max_buys_per_day > 0 and self.buys_today(pot) >= pot.max_buys_per_day

    # ----------------------------------------------------------- every candle

    def prime_signals(self, strategy_manager, exchange, symbol, timeframe, candle_data) -> None:
        """At startup: compute each pot's signal for the dashboard. Never trades.
        Uses closed candles only, like the hourly check."""
        step_ms = _timeframe_ms(timeframe)
        now_ms = time.time() * 1000
        closed = [c for c in (candle_data or []) if c[0] + step_ms <= now_ms] if step_ms else list(candle_data or [])
        done = set()
        for pot in self.pots.values():
            if pot.strategy is None:
                continue
            try:
                if pot.strategy.name in done:
                    pot.last_signal = strategy_manager.last_signals.get(pot.strategy.name)
                    continue
                pot.last_signal = strategy_manager.compute_signal_for(
                    pot.strategy, exchange, symbol, timeframe, closed,
                )
                done.add(pot.strategy.name)
            except Exception as exc:
                logger.warning("Pot %s: could not compute its starting signal: %s", pot.name, exc)

    def on_candle(self, price, strategy_manager, exchange, symbol, timeframe, candle_data) -> Dict[str, dict]:
        """Run every pot on a closed candle: stops/targets first, then the
        pot's strategy. Returns what happened per pot."""
        results = {}
        if self.live:
            # Book stop orders that sold since the last check first: until
            # then the pots still count those coins, which would look like
            # missing BTC. Then compare with the exchange before trading, so
            # a mismatch stops this hour's buys.
            stop_sales = self.book_stop_fills()
            self.seed_peaks(price)
            try:
                self.reconcile()
            except Exception as exc:
                logger.warning("Pot check before trading failed: %s", exc)
        else:
            stop_sales = {}
        for pot in self.pots.values():
            r = {"holding_before": pot.holding, "signal": None, "exit": None,
                 "trade": None, "note": None}
            if getattr(pot.trader, "needs_check", None):
                r["note"] = f"stopped until you check it: {pot.trader.needs_check}"
                r["exit"] = stop_sales.get(pot.name)
                pot.last_note = r["note"]
                logger.warning("Pot %s: %s", pot.name, r["note"])
                if r["exit"]:
                    self.record_trade(pot, r["exit"])
                results[pot.name] = r
                continue
            try:
                r["exit"] = stop_sales.get(pot.name) or pot.trader.update_position(price)
                if pot.strategy is not None:
                    sig = strategy_manager.compute_signal_for(
                        pot.strategy, exchange, symbol, timeframe, candle_data,
                    )
                    r["signal"] = pot.last_signal = sig
                    if sig.direction == "bullish" and not pot.holding and pot.paused:
                        r["note"] = "paused: not buying until you resume it"
                        logger.info("Pot %s: %s", pot.name, r["note"])
                    elif (sig.direction == "bullish" and not pot.holding
                          and float(pot.balances()["USDT"]) < 1.0):
                        r["note"] = "no cash to buy with: move money into this pot"
                    elif sig.direction == "bullish" and not pot.holding and self.cap_reached(pot):
                        r["note"] = f"skipped buy: {pot.max_buys_per_day} buys today already"
                        logger.info("Pot %s: %s", pot.name, r["note"])
                    else:
                        r["trade"] = pot.trader.handle_signal(sig, pot.order_pct)
            except Exception as exc:
                logger.exception("Pot %s failed on this candle: %s", pot.name, exc)
                reason = str(exc).strip().splitlines()[0][:120] if str(exc).strip() else type(exc).__name__
                r["note"] = f"couldn't trade on the last check: {reason} (details in the bot log)"
            pot.last_note = r["note"]
            for trade in (r["exit"], r["trade"]):
                if trade:
                    self.record_trade(pot, trade)
            results[pot.name] = r
        return results

    def record_trade(self, pot: Pot, trade) -> None:
        """Count a trade toward the daily cap and send the Telegram note."""
        if trade.side == "buy":
            day = _utc_day_start().date().isoformat()
            pot._buys[day] = pot._buys.get(day, 0) + 1
        if not (self.trade_alerts and self.notify):
            return
        try:
            b = pot.balances()
            verb = "Bought" if trade.side == "buy" else "Sold"
            body = f"{verb} {trade.amount:.6f} BTC at ${trade.price:,.2f} (${trade.notional:,.2f})."
            if trade.pnl is not None:
                body += f" Result: {'+' if trade.pnl >= 0 else '-'}${abs(trade.pnl):.2f}."
            if trade.exit_reason and trade.side == "sell":
                body += f" Why: {trade.exit_reason.replace('_', ' ')}."
            body += f" Pot now: ${b['USDT']:.2f} cash + {b['BASE']:.6f} BTC."
            mode = "" if self.live else " (paper)"
            self.notify(f"{pot.label} pot{mode}: {verb.lower()} BTC", body, severity="info")
        except Exception as exc:
            logger.warning("Pot trade alert failed: %s", exc)

    # ------------------------------------------------------- sell now / pause

    def sell_now(self, name: str, pause: bool = False):
        """Sell all of one pot's BTC at the market price, booked to that pot.
        pause=True also stops the pot buying again until resumed.
        Returns the trade. Raises PotActionError when there's nothing to sell."""
        pot = self.get(name)
        if pot is None:
            raise PotActionError(f"Unknown pot '{name}'")
        pos = pot.trader.open_position
        if pos is None:
            raise PotActionError(f"The {pot.label} pot holds no BTC to sell")
        if pause and pot.strategy is not None:
            self.set_paused(name, True)  # first, so a failed sell still stops new buys
        pot.trader.last_refusal = None
        trade = pot.trader.execute_market_sell(
            pos.amount, None, exit_reason="manual", is_closing_sell=True,
        )
        if trade is None:
            why = getattr(pot.trader, "last_refusal", None)
            raise PotActionError(
                f"The {pot.label} pot didn't sell: {why}" if why else
                f"The exchange did not take the sell for the {pot.label} pot (see the bot log)")
        pot.last_note = "sold by you" + (" · paused" if pot.paused else "")
        self.record_trade(pot, trade)
        logger.info("Pot %s: sold by you (%.8f BTC @ $%.2f)%s", pot.name,
                    trade.amount, trade.price, " and paused" if pot.paused else "")
        return trade

    def set_paused(self, name: str, paused: bool) -> None:
        """Pause (no new buys) or resume a pot; remembered across restarts."""
        pot = self.get(name)
        if pot is None:
            raise PotActionError(f"Unknown pot '{name}'")
        if pot.strategy is None:
            raise PotActionError("The Manual pot only trades when you click, so it has nothing to pause")
        pot.paused = bool(paused)
        pot.last_note = "paused: not buying until you resume it" if paused else "resumed"
        if self.db is not None:
            try:
                self.db.set_strategy_config(
                    f"BOT_INTERNAL_POT_PAUSED_{pot.tag}", "true" if paused else "false",
                    "str", "pots", "Internal: pot paused by the user (no new buys)",
                )
            except Exception as exc:
                logger.error("Pot %s: could not save pause state: %s", pot.name, exc)
        logger.info("Pot %s: %s", pot.name, "paused" if paused else "resumed")

    # ------------------------------------------------- loss limit (drawdown)
    # A live pot stops buying once its value falls max_portfolio_drawdown
    # below the best value seen at a buy (LiveTrader._check_portfolio_peak_
    # drawdown). The best value is kept per pot in strategy_config.

    def _peak_key(self, pot: "Pot") -> str:
        return f"{PEAK_EQUITY_KEY}_{pot.tag}"

    def _read_peak(self, pot: "Pot") -> Optional[float]:
        if self.db is None:
            return None
        try:
            row = self.db.get_strategy_config(self._peak_key(pot))
            value = float(row.value) if row and row.value else 0.0
            return value if value > 0 else None
        except Exception as exc:
            logger.debug("Pot %s: could not read its best value: %s", pot.name, exc)
            return None

    def _write_peak(self, pot: "Pot", value: float) -> None:
        if self.db is None:
            return
        self.db.set_strategy_config(self._peak_key(pot), str(max(0.0, float(value))), "float", "risk",
                                    "Internal: peak portfolio equity (USDT) for drawdown limit")

    def seed_peaks(self, price: float) -> None:
        """Give every live pot a best value for its loss limit. It used to
        be taken only when a buy passed the bot's checks, so a buy recovered
        by hand (Trend Hold, 2026-11-02) left the pot with none: the
        dashboard couldn't show how far it was from its best. The money put
        in counts as its value at the start."""
        if self.db is None or not self.live:
            return
        for pot in self.pots.values():
            if not isinstance(pot.trader, PotLiveTrader) or self._read_peak(pot) is not None:
                continue
            try:
                value = pot.value(price)
                put_in = pot.start_value + self.net_in(pot)
                self._write_peak(pot, max(value, put_in))
                logger.info("Pot %s: loss limit now counts from $%.2f", pot.name, max(value, put_in))
            except Exception as exc:
                logger.warning("Pot %s: could not set its best value: %s", pot.name, exc)

    def _shift_peak(self, pot: "Pot", delta: float) -> None:
        """Money moved in or out isn't a gain or loss: move the best value with it."""
        peak = self._read_peak(pot)
        if peak is None:
            return  # none yet: it's taken at the pot's next buy
        try:
            self._write_peak(pot, peak + delta)
        except Exception as exc:
            logger.warning("Pot %s: could not adjust its best value: %s", pot.name, exc)

    def loss_limit(self, pot: "Pot", price: float) -> Dict:
        """Where a pot stands against the loss limits that stop new buys."""
        trader = pot.trader
        cfg = getattr(trader, "config", None)  # practice (paper) pots have none and no limit
        enabled = bool(getattr(cfg, "portfolio_drawdown_kill_enabled", False)) and self.live
        limit = float(getattr(cfg, "max_portfolio_drawdown", 0.0) or 0.0) if cfg is not None else 0.0
        equity = float(trader.usdt_balance) + float(trader.base_balance) * float(price)
        peak = self._read_peak(pot) if enabled else None
        drop = max(0.0, (peak - equity) / peak) if peak else None
        halted = bool(getattr(trader, "portfolio_buy_halt", False))
        # Daily loss limit: losses booked today beyond limit x starting money
        daily_hit = False
        daily_pnl = float(getattr(trader, "daily_pnl", 0.0) or 0.0)
        reset_at = getattr(trader, "daily_reset_time", None)
        if reset_at is not None and datetime.now(timezone.utc) >= reset_at:
            daily_pnl = 0.0  # a new day has started; the trader resets on its next check
        initial = float(getattr(trader, "initial_usdt", 0.0) or 0.0)
        if self.live and limit > 0 and initial > 0 and daily_pnl < -initial * limit:
            daily_hit = True
        return {
            "enabled": enabled,
            "limit_pct": limit * 100,
            "peak": peak,
            "value": equity,
            "drop_pct": drop * 100 if drop is not None else None,
            "halted": enabled and halted,
            "daily_loss_hit": daily_hit,
            "daily_pnl": daily_pnl,
        }

    def reset_loss_limit(self, name: str, price: float) -> Dict:
        """Let a pot stopped by the loss limit buy again. Its value now
        becomes its new best value, so the limit counts from here."""
        pot = self.get(name)
        if pot is None:
            raise PotActionError(f"Unknown pot '{name}'")
        if pot.strategy is None:
            raise PotActionError("The Manual pot only buys when you click")
        status = self.loss_limit(pot, price)
        if not status["halted"]:
            raise PotActionError(f"{pot.label} isn't stopped by the loss limit")
        old_peak = status["peak"]
        self._write_peak(pot, status["value"])
        pot.trader.portfolio_buy_halt = False
        pot.last_note = "loss limit reset by you: it counts from today's value"
        logger.warning("Pot %s: loss limit reset by the user (best value $%.2f -> $%.2f)",
                       pot.name, old_peak or 0.0, status["value"])
        return {"old_peak": old_peak, "new_peak": status["value"]}

    def restore_paused(self) -> None:
        if self.db is None:
            return
        for pot in self.pots.values():
            try:
                row = self.db.get_strategy_config(f"BOT_INTERNAL_POT_PAUSED_{pot.tag}")
                pot.paused = bool(row and str(row.value).lower() == "true")
            except Exception as exc:
                logger.warning("Pot %s: could not read pause state: %s", pot.name, exc)
            if pot.paused:
                logger.info("Pot %s: paused (not buying until resumed)", pot.name)

    # ------------------------------------------------------- add / remove pots

    def strategy_choices(self) -> List[Dict]:
        return [{"key": k, "label": StrategyNames.get_display_name(POT_STRATEGIES[k])}
                for k in POT_STRATEGY_CHOICES]

    def add_pot(self, name: str, strategy: str, max_buys_per_day=3, order_pct=0.95,
                label: str = "", source: str = "dashboard") -> Pot:
        """Add a pot that starts with $0 (fund it with a cash move). From the
        dashboard it is saved, so it's back after a restart. Call with the
        trader lock held. Raises PotActionError if not allowed."""
        if self._make_trader is None or self._strategy_manager is None:
            raise PotActionError("Pots can't be added in this mode")
        name = str(name or "").strip().lower()
        if not _POT_NAME_RE.match(name):
            raise PotActionError("Name: start with a letter, then letters, digits or _ (up to 12)")
        if name in self.pots or name in BUILTIN_POTS or name == UNASSIGNED:
            raise PotActionError(f"There is already a pot called '{name}'")
        key = str(strategy or "").strip().lower()
        if key not in POT_STRATEGIES:
            raise PotActionError(f"Unknown strategy '{strategy}' (use one of: {', '.join(POT_STRATEGY_CHOICES)})")
        strat = self._strategy_manager.get_strategy(POT_STRATEGIES[key])
        if strat is None:
            raise PotActionError(f"The strategy '{key}' isn't available")
        try:
            max_buys = int(max_buys_per_day)
            pct = float(order_pct)
        except (TypeError, ValueError):
            raise PotActionError("Buys per day and spend per buy must be numbers")
        if not 0 <= max_buys <= 24:
            raise PotActionError("Buys per day: 0 (no limit) to 24")
        if not 0.1 <= pct <= 1.0:
            raise PotActionError("Spend per buy: 10% to 100% of the pot's cash")
        label = (str(label or "").strip() or name.replace("_", " ").title())[:40]
        if source == "dashboard" and self.db is not None:
            if self.db.pot_name_used(name):
                raise PotActionError(
                    f"The name '{name}' was used before; pick a new one so the new pot "
                    f"doesn't inherit old trades")
            self.db.add_pot_definition(name, label, key, max_buys, pct)

        pot = Pot(name, label, self._make_trader(name, 0.0), budget=0.0, start_value=0.0,
                  strategy=strat, order_pct=pct, max_buys_per_day=max_buys, source=source)
        # A new dict, so readers iterating the old one are never disturbed
        self.pots = {**self.pots, name: pot}
        self.restore_start_times(only=[pot])
        self.refresh_limits(pot)
        logger.info("Pot %s added (%s, %s, max %d buys/day, %.0f%% per buy)", name, source,
                    StrategyNames.get_display_name(strat.name), max_buys, pct * 100)
        return pot

    def remove_pot(self, name: str, price: float) -> None:
        """Remove a pot added from the dashboard. Only when it holds nothing:
        no BTC (a sliver too small to sell may stay on the exchange) and no
        cash (move it out first). Call with the trader lock held."""
        pot = self.get(name)
        if pot is None:
            raise PotActionError(f"Unknown pot '{name}'")
        if pot.source == "builtin":
            raise PotActionError(f"The {pot.label} pot is built in and can't be removed")
        if pot.source == "env":
            raise PotActionError(f"The {pot.label} pot is listed in BOT_POTS_EXTRA in .env; remove it there")
        b = pot.balances()
        if pot.holding or float(b["BASE"]) * price >= 1.0:
            raise PotActionError(f"The {pot.label} pot holds BTC: sell it first")
        if float(b["USDT"]) >= 0.01:
            raise PotActionError(
                f"The {pot.label} pot has ${float(b['USDT']):.2f} cash: move it to another pot first")
        if self.db is not None and not self.db.remove_pot_definition(name):
            raise PotActionError(f"Could not find the saved pot '{name}'")
        self.pots = {k: v for k, v in self.pots.items() if k != name}
        logger.info("Pot %s removed", name)

    def pot_style(self, name: str) -> Dict[str, str]:
        """Color and chart letter for a pot (built-in ones keep theirs)."""
        names = list(self.pots)
        if name in POT_COLORS:
            color = POT_COLORS[name]
        else:
            extras = [n for n in names if n not in POT_COLORS]
            color = _EXTRA_COLORS[extras.index(name) % len(_EXTRA_COLORS)] if name in extras else "#8B949E"
        letter = _POT_LETTERS.get(name)
        if letter is None:
            pot = self.pots.get(name)
            word = re.sub(r"[^A-Za-z0-9]", "", pot.label if pot else name) or name
            taken = {self.pot_style(n)["letter"] for n in names[:names.index(name)]} if name in names else set()
            letter = word[0].upper()
            if letter in taken:
                letter = (word[:2]).title()
        return {"color": color, "letter": letter}

    # ------------------------------------------------------------ cash moves

    def _real_money(self) -> bool:
        traders = [t for t in self.traders() if isinstance(t, PotLiveTrader)]
        return bool(traders) and traders[0].mode == TradingMode.LIVE

    def refresh_limits(self, pot: Optional[Pot] = None) -> None:
        """A live pot's daily loss limit is a share of the money put in. An
        added pot starts at $0, so follow what was moved in since."""
        for p in ([pot] if pot else self.pots.values()):
            if isinstance(p.trader, PotLiveTrader):
                put_in = p.start_value + self.net_in(p)
                p.trader.initial_usdt = max(p.budget, put_in)

    def restore_transfers(self) -> None:
        """At start-up: add cash moved in/out of each pot since its last trade
        (a trade row records the pot's cash, so older moves are already in it)."""
        if self.db is None:
            return
        for pot in self.pots.values():
            try:
                last = self.db.get_trades(limit=1, pot=pot.tag)
                since = last[0].timestamp if last else None
                moved = self.db.net_pot_transfers(pot.tag, since=since)
            except Exception as exc:
                logger.error("Pot %s: could not read cash moves: %s", pot.name, exc)
                continue
            if moved:
                self._set_cash(pot, pot.trader.usdt_balance + moved)
                logger.info("Pot %s: %+.2f cash moved since its last trade", pot.name, moved)

    def restore_start_times(self, only: Optional[List[Pot]] = None) -> None:
        """When each pot began: saved the first time it runs, or the time of
        its first trade/move if earlier (the paper Trend Hold pot carries on
        an account that started before pots existed)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for pot in (only if only is not None else self.pots.values()):
            key = f"BOT_INTERNAL_POT_START_{pot.tag}"
            saved = None
            if self.db is not None:
                try:
                    row = self.db.get_strategy_config(key)
                    saved = datetime.fromisoformat(row.value) if row and row.value else None
                except Exception as exc:
                    logger.warning("Pot %s: could not read its start time: %s", pot.name, exc)
            if saved is None and self.db is not None:
                firsts = [now]
                try:
                    trades = self.db.get_trades(limit=100000, pot=pot.tag)
                    if trades:
                        firsts.append(trades[-1].timestamp)
                    moves = self.db.get_pot_transfers(limit=100000, pot=pot.tag)
                    if moves:
                        firsts.append(moves[-1].timestamp)
                    saved = min(firsts)
                    self.db.set_strategy_config(
                        key, saved.isoformat(), "str", "pots", "Internal: when this money pot began",
                    )
                except Exception as exc:
                    logger.warning("Pot %s: could not save its start time: %s", pot.name, exc)
            pot.start_time = saved or now

    def net_in(self, pot: Pot) -> float:
        """All cash moved into this pot minus all moved out, ever."""
        if self.db is not None:
            try:
                return self.db.net_pot_transfers(pot.tag)
            except Exception as exc:
                logger.warning("Pot %s: could not total cash moves: %s", pot.name, exc)
        return sum(t["amount"] for t in self._transfers if t["to"] == pot.name) - sum(
            t["amount"] for t in self._transfers if t["from"] == pot.name
        )

    def unassigned_cash(self) -> Optional[float]:
        """Live: exchange cash that belongs to no pot. None when not real money."""
        if not self._real_money():
            return None
        trader = self.traders()[0]
        trader.sync_balances()
        free = (trader.exchange_balances or {}).get("USDT_free", 0.0)
        return max(0.0, free - sum(t.usdt_balance for t in self.traders()))

    def recent_transfers(self, limit: int = 10) -> List[Dict]:
        tags = {p.tag: p.name for p in self.pots.values()}
        if self.db is not None:
            try:
                rows = self.db.get_pot_transfers(limit=limit * 3)
                moves = []
                for r in rows:
                    src = tags.get(r.from_pot, None) if r.from_pot else UNASSIGNED
                    dst = tags.get(r.to_pot, None) if r.to_pot else UNASSIGNED
                    if src is None or dst is None:
                        continue  # another mode's pots (paper vs live)
                    moves.append({"time": r.timestamp.replace(tzinfo=timezone.utc).isoformat(),
                                  "from": src, "to": dst, "amount": float(r.amount), "note": r.note})
                return moves[:limit]
            except Exception as exc:
                logger.warning("Could not read cash moves: %s", exc)
        return list(reversed(self._transfers))[:limit]

    @staticmethod
    def _set_cash(pot: Pot, cash: float) -> None:
        pot.trader.usdt_balance = float(cash)
        if hasattr(pot.trader, "reserved_balance"):
            pot.trader.reserved_balance = pot.trader.usdt_balance * 0.001

    def transfer(self, source: str, target: str, amount, note: str = "") -> Dict:
        """Move uninvested cash between pots, or from/to unassigned cash.
        Call with the trader lock held. Raises TransferError if not allowed."""
        try:
            amount = round(float(amount), 2)
        except (TypeError, ValueError):
            raise TransferError("Amount must be a number")
        if not math.isfinite(amount) or amount <= 0:
            raise TransferError("Amount must be more than $0")
        if source == target:
            raise TransferError("Pick two different places")
        names = set(self.pots) | {UNASSIGNED}
        if source not in names or target not in names:
            raise TransferError("Unknown pot")
        src, dst = self.pots.get(source), self.pots.get(target)

        if src is not None and amount > src.trader.usdt_balance + 1e-9:
            raise TransferError(
                f"{src.label} has only ${src.trader.usdt_balance:.2f} in cash "
                f"(BTC it holds can't be moved; it moves when the pot sells)"
            )
        if src is None and self._real_money():
            free = self.unassigned_cash() or 0.0
            if amount > free + 1e-9:
                raise TransferError(f"Only ${free:.2f} on the exchange isn't in a pot yet")

        if src is not None:
            self._set_cash(src, src.trader.usdt_balance - amount)
        if dst is not None:
            self._set_cash(dst, dst.trader.usdt_balance + amount)

        move = {"time": datetime.now(timezone.utc).isoformat(), "from": source, "to": target,
                "amount": amount, "note": note or None}
        if self.db is not None:
            try:
                self.db.add_pot_transfer(src.tag if src else None, dst.tag if dst else None,
                                         amount, note)
            except Exception:
                # Undo, so memory and the database never disagree
                if src is not None:
                    self._set_cash(src, src.trader.usdt_balance + amount)
                if dst is not None:
                    self._set_cash(dst, dst.trader.usdt_balance - amount)
                raise
        else:
            self._transfers.append(move)

        for p in (src, dst):
            if p is not None:
                self.refresh_limits(p)
        # Moved money isn't a loss or a gain for the loss limit either
        if src is not None:
            self._shift_peak(src, -amount)
        if dst is not None:
            self._shift_peak(dst, amount)
        label = lambda p, name: p.label if p else ("new money" if name == source else "unassigned")
        message = f"Moved ${amount:.2f} from {label(src, source)} to {label(dst, target)}"
        logger.info("Pots: %s", message)
        return {"message": message, "move": move}

    # ------------------------------------------------------- live safety check

    def reconcile(self) -> List[str]:
        """Live only: do the pots claim more cash or BTC than the exchange
        holds? Then buying stops in every pot (and selling too when BTC is
        short), until a person checks the account and clears it. Returns the
        problems found now."""
        traders = [t for t in self.traders() if isinstance(t, PotLiveTrader)]
        if not traders or traders[0].mode != TradingMode.LIVE:
            return []
        try:
            traders[0].sync_balances()
        except Exception as exc:
            logger.warning("Pot check: exchange balance unavailable: %s", exc)
            return []
        ex = traders[0].exchange_balances or {}
        cash = sum(t.usdt_balance for t in traders)
        btc = sum(t.base_balance for t in traders)
        ex_cash, ex_btc = ex.get("USDT_total", 0.0), ex.get("BASE_total", 0.0)
        problems = []
        cash_short = cash > ex_cash + max(0.5, cash * 0.01)
        btc_short = btc > ex_btc + 2e-05
        if cash_short:
            problems.append(f"pots hold ${cash:.2f} cash but the exchange has ${ex_cash:.2f}")
        if btc_short:
            problems.append(f"pots hold {btc:.8f} BTC but the exchange has {ex_btc:.8f}")
        if problems:
            text = "; ".join(problems)
            old = self.mismatch or {}
            self._set_mismatch({
                "cash": bool(old.get("cash")) or cash_short,
                "btc": bool(old.get("btc")) or btc_short,
                "text": text,
                "since": old.get("since") or datetime.now(timezone.utc).isoformat(),
            })
            if not self._mismatch_alerted:
                self._mismatch_alerted = True
                logger.critical("Pot check: %s. Buying stopped%s until you clear it.",
                                text, " and selling" if btc_short else "")
                if self.notify:
                    stopped = "Buying and selling are" if self.mismatch.get("btc") else "Buying is"
                    self.notify("🚨 Pots don't match the exchange", text.capitalize()
                                + f". {stopped} stopped in every pot until you check the account "
                                + "and clear it on the dashboard.", severity="critical")
        else:
            self._mismatch_alerted = False

        # More BTC on the exchange than all pots own: an order that went
        # through twice, or coins added by hand. Alert once; nothing stops.
        extra = ex_btc - btc
        if extra > 2e-05:
            if not self._excess_alerted:
                self._excess_alerted = True
                logger.warning("Pot check: the exchange has %.8f BTC that no pot owns", extra)
                if self.notify:
                    self.notify("Unowned BTC on the exchange",
                                f"The account holds {extra:.8f} BTC more than all pots together. "
                                "If you didn't add it yourself, an order may have gone through twice.",
                                severity="warning")
        else:
            self._excess_alerted = False
        return problems

    def _set_mismatch(self, m: Optional[Dict]) -> None:
        self.mismatch = m
        for t in self.traders():
            t.pots_mismatch = dict(m) if m else None
        if self.db is not None:
            try:
                import json
                self.db.set_strategy_config(
                    "BOT_INTERNAL_POTS_MISMATCH", json.dumps(m) if m else "", "str", "pots",
                    "Internal: pots didn't match the exchange; buying stopped until cleared",
                )
            except Exception as exc:
                logger.error("Could not save the pots-mismatch stop: %s", exc)

    def restore_mismatch(self) -> None:
        if self.db is None:
            return
        try:
            import json
            row = self.db.get_strategy_config("BOT_INTERNAL_POTS_MISMATCH")
            if row and row.value:
                self.mismatch = json.loads(row.value)
                for t in self.traders():
                    t.pots_mismatch = dict(self.mismatch)
                self._mismatch_alerted = True  # already told
                logger.critical("Pots-mismatch stop still on from %s: %s",
                                self.mismatch.get("since"), self.mismatch.get("text"))
        except Exception as exc:
            logger.error("Could not read the pots-mismatch stop: %s", exc)

    def clear_mismatch(self) -> None:
        """A person checked the account. Only clears when the pots match the
        exchange now."""
        if self.mismatch is None:
            return
        self._mismatch_alerted = True  # don't alert on this re-check
        self.book_stop_fills()
        problems = self.reconcile()
        if problems:
            raise PotActionError("The pots still don't match the exchange: " + "; ".join(problems))
        self._mismatch_alerted = False
        self._set_mismatch(None)
        logger.info("Pots-mismatch stop cleared by the user")

    def clear_needs_check(self, name: str) -> None:
        """A person checked a pot after an order that wasn't recorded."""
        pot = self.get(name)
        if pot is None:
            raise PotActionError(f"Unknown pot '{name}'")
        if not getattr(pot.trader, "needs_check", None):
            return
        self.book_stop_fills()
        problems = self.reconcile()
        if problems:
            raise PotActionError("The pots don't match the exchange yet: " + "; ".join(problems))
        pot.trader.clear_needs_check()
        pot.last_note = "checked by you: trading again"
        logger.info("Pot %s: 'needs check' cleared by the user", pot.name)

    def book_stop_fills(self) -> Dict[str, object]:
        """Record any exchange stop order that sold a pot's coins.
        Returns {pot name: the booked sale}."""
        sold = {}
        for pot in self.pots.values():
            t = pot.trader
            if isinstance(t, PotLiveTrader) and t.open_position is not None:
                try:
                    trade = t.check_exchange_stop_filled()
                    t._stop_checked_this_candle = True  # update_position needn't ask again
                    if trade is not None:
                        sold[pot.name] = trade
                except Exception as exc:
                    logger.warning("Pot %s: could not check its exchange stop: %s", t.pot, exc)
        return sold

    def startup_stop_sync(self) -> None:
        """At start-up, once every pot's books are complete: book any
        exchange stop that sold while the bot was down, then re-arm stops."""
        for t in self.traders():
            if isinstance(t, PotLiveTrader):
                try:
                    t.startup_stop_sync()
                except Exception as exc:
                    logger.error("Pot %s: start-up stop check failed: %s", t.pot, exc)

    def account_check(self) -> Optional[Dict]:
        """Live: what the exchange account holds next to what the pots book.

        Uses the balance read by the last sync (unassigned_cash() or
        reconcile() refresh it). None when not real money or never synced.
        "Left over" is money in the account that no pot owns: unassigned
        cash, and BTC dust left by fees and rounding.
        """
        if not self._real_money():
            return None
        traders = self.traders()
        ex = traders[0].exchange_balances if traders else None
        if not ex:
            return None
        pots_cash = sum(t.usdt_balance for t in traders)
        pots_btc = sum(t.base_balance for t in traders)
        usd, btc = float(ex.get("USDT_total", 0.0)), float(ex.get("BASE_total", 0.0))
        cash_short = pots_cash - usd > max(0.5, pots_cash * 0.01)
        btc_short = pots_btc - btc > 2e-05
        return {
            "usd": usd,
            "btc": btc,
            "btc_locked": max(0.0, btc - float(ex.get("BASE_free", btc))),
            "pots_usd": pots_cash,
            "pots_btc": pots_btc,
            "left_usd": max(0.0, usd - pots_cash),
            "left_btc": max(0.0, btc - pots_btc),
            "matches": not (cash_short or btc_short),
        }

    # -------------------------------------------------------------- dashboard

    def summary(self, price: float) -> Dict:
        rows = []
        for pot in self.pots.values():
            b = pot.balances()
            cash, btc = float(b["USDT"]), float(b["BASE"])
            value = cash + btc * price
            pos = pot.trader.open_position
            stop = take = None
            if pos is not None:
                stop = None if pos.stop_loss < pos.entry_price * _NO_STOP_FRACTION else float(pos.stop_loss)
                take = None if pos.take_profit > pos.entry_price * 10 else float(pos.take_profit)
            sig = pot.last_signal
            net_in = self.net_in(pot)
            invested = pot.start_value + net_in
            rows.append({
                "name": pot.name,
                "label": pot.label,
                "tag": pot.tag,
                "strategy": StrategyNames.get_display_name(pot.strategy.name) if pot.strategy else "You",
                "budget": pot.budget,
                "start_value": pot.start_value,
                "cash": cash,
                "btc": btc,
                "value": value,
                "net_in": net_in,
                "invested": invested,
                "pnl": value - invested,
                "pnl_pct": (value / invested - 1) * 100 if invested > 0 else 0.0,
                "holding": pos is not None,
                "entry_price": float(pos.entry_price) if pos else None,
                "stop_loss": stop,
                "take_profit": take,
                "buys_today": self.buys_today(pot),
                "paused": pot.paused,
                "needs_check": getattr(pot.trader, "needs_check", None),
                "loss_limit": self.loss_limit(pot, price),
                "source": pot.source,
                **self.pot_style(pot.name),
                "max_buys_per_day": pot.max_buys_per_day,
                "last_signal": {
                    "direction": sig.direction,
                    "confidence": float(sig.confidence),
                    "time": sig.timestamp.isoformat() if sig.timestamp else None,
                } if sig is not None else None,
                "note": pot.last_note,
            })
        invested = sum(r["invested"] for r in rows)
        value = sum(r["value"] for r in rows)
        return {
            "live": self.live,
            "real_money": self._real_money(),
            "mismatch": self.mismatch,
            "strategy_choices": self.strategy_choices(),
            "price": price,
            "pots": rows,
            "total": {
                "invested": invested,
                "value": value,
                "pnl": value - invested,
                "pnl_pct": (value / invested - 1) * 100 if invested > 0 else 0.0,
            },
        }


# ---------------------------------------------------------------------------
# Building the pots from the config
# ---------------------------------------------------------------------------

def _paper_start(db_manager, config) -> float:
    """Cash the paper Trend Hold account had before its first trade."""
    try:
        first = db_manager.get_trades(limit=100000, pot=POT_TREND)[-1] if db_manager else None
    except Exception:
        first = None
    if first is None:
        return float(config.pot_trend_usd)
    if first.side == "buy":
        return float(first.usdt_balance) + float(first.notional) + float(first.fee or 0.0)
    return float(first.usdt_balance) - float(first.notional) + float(first.fee or 0.0)


def build_pots(config, *, exchange, db_manager, strategy_manager, trading_mode: str,
               notify: Optional[Callable] = None) -> PotManager:
    trading_mode = trading_mode.lower()
    live = trading_mode in ("live", "dry_run")
    if live and not LIVE_TRADER_AVAILABLE:
        raise RuntimeError("live trading module unavailable")

    trend = strategy_manager.get_strategy(StrategyNames.TREND_HOLD)
    if trend is None:
        raise ValueError("Trend Hold strategy not found")
    intraday_name = INTRADAY_STRATEGIES.get(config.pot_intraday_strategy)
    if intraday_name is None:
        raise ValueError(
            f"Unknown BOT_POT_INTRADAY_STRATEGY '{config.pot_intraday_strategy}' "
            f"(use one of: {', '.join(sorted(INTRADAY_STRATEGIES))})"
        )
    intraday = strategy_manager.get_strategy(intraday_name)
    if intraday is None:
        raise ValueError(f"Strategy {intraday_name} not found")

    def trader(name: str, budget: float, csv: bool = False):
        tag = pot_tag(name, live)
        if live:
            mode = TradingMode.LIVE if trading_mode == "live" else TradingMode.DRY_RUN
            return PotLiveTrader(exchange, config, mode, db_manager, pot=tag, budget=budget)
        return PaperTrader(
            initial_usdt=budget,
            fee_rate=config.fee_rate,
            slippage=config.slippage,
            log_path=config.trades_log_path,
            use_trailing_stop=config.use_trailing_stop,
            trailing_stop_pct=config.trailing_stop_pct,
            db_manager=db_manager,
            enable_database=config.enable_database,
            enable_csv_logging=config.enable_csv_logging and csv,
            pot=tag,
        )

    # The paper Trend Hold pot carries on the existing paper account, so it
    # started with whatever that account had; every other pot at its budget.
    trend_start = config.pot_trend_usd if live else _paper_start(db_manager, config)
    pots = [
        Pot(POT_TREND, "Trend Hold", trader(POT_TREND, config.pot_trend_usd, csv=True),
            budget=config.pot_trend_usd, start_value=trend_start, strategy=trend),
        Pot(POT_INTRADAY, StrategyNames.get_display_name(intraday_name),
            trader(POT_INTRADAY, config.pot_intraday_usd),
            budget=config.pot_intraday_usd, start_value=config.pot_intraday_usd,
            strategy=intraday, order_pct=config.pot_intraday_order_pct,
            max_buys_per_day=config.pot_intraday_max_buys_per_day),
        Pot(POT_MANUAL, "Manual", trader(POT_MANUAL, config.pot_manual_usd),
            budget=config.pot_manual_usd, start_value=config.pot_manual_usd),
    ]
    manager = PotManager(
        pots, live=live, notify=notify, trade_alerts=config.pot_trade_alerts,
        db=None if trading_mode == "dry_run" else db_manager,
    )
    manager._make_trader = trader
    manager._strategy_manager = strategy_manager
    # Extra pots come after the built-in three and never change them. One
    # that can't be set up is skipped with an error; the bot keeps running.
    specs, errors = parse_extra_pots(getattr(config, "pots_extra", "") or "")
    for err in errors:
        logger.error("BOT_POTS_EXTRA: %s", err)
    for spec in specs:
        try:
            manager.add_pot(source="env", **spec)
        except Exception as exc:
            logger.error("BOT_POTS_EXTRA: pot '%s' skipped: %s", spec.get("name"), exc)
    if db_manager is not None:
        try:
            saved = db_manager.get_pot_definitions()
        except Exception as exc:
            logger.error("Could not read pots added from the dashboard: %s", exc)
            saved = []
        for d in saved:
            if d["name"] in manager.pots:
                logger.warning("Pot '%s' from the dashboard skipped: a pot with that name exists", d["name"])
                continue
            try:
                manager.add_pot(d["name"], d["strategy"], d["max_buys_per_day"], d["order_pct"],
                                label=d["label"], source="restored")
                manager.pots[d["name"]].source = "dashboard"
            except Exception as exc:
                logger.error("Pot '%s' from the dashboard skipped: %s", d["name"], exc)
    manager.restore_transfers()
    manager.restore_start_times()
    manager.restore_paused()
    manager.restore_mismatch()
    manager.refresh_limits()
    manager.startup_stop_sync()
    return manager


def parse_extra_pots(text: str):
    """BOT_POTS_EXTRA -> ([{name, strategy, max_buys_per_day, order_pct}], [errors]).
    Each item: name:strategy[:max_buys_per_day[:order_pct]]"""
    specs, errors = [], []
    for item in (text or "").split(","):
        item = item.strip()
        if not item:
            continue
        parts = [x.strip() for x in item.split(":")]
        if len(parts) < 2 or len(parts) > 4:
            errors.append(f"'{item}' should be name:strategy[:max_buys[:order_pct]]")
            continue
        spec = {"name": parts[0].lower(), "strategy": parts[1].lower()}
        try:
            if len(parts) > 2 and parts[2]:
                spec["max_buys_per_day"] = int(parts[2])
            if len(parts) > 3 and parts[3]:
                spec["order_pct"] = float(parts[3])
        except ValueError:
            errors.append(f"'{item}': buys per day and order % must be numbers")
            continue
        specs.append(spec)
    return specs, errors
