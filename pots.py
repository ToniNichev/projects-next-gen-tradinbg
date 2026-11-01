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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from paper_trader import PaperTrader
from strategies.constants import StrategyNames

try:
    from live_trader import LiveTrader, TradingMode
    LIVE_TRADER_AVAILABLE = True
except ImportError:  # pragma: no cover
    LIVE_TRADER_AVAILABLE = False
    LiveTrader = object  # type: ignore

logger = logging.getLogger(__name__)

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

    def __init__(self, exchange, config, mode, db_manager, pot: str, budget: float):
        self.pot = pot
        self.pot_budget = float(budget)
        self.exchange_balances: Optional[Dict[str, float]] = None
        self._exchange_synced_at = 0.0
        super().__init__(exchange, config, mode=mode, db_manager=db_manager)
        self.initial_usdt = self.pot_budget
        self.usdt_balance, self.base_balance = self._restore_ledger()
        self.reserved_balance = self.usdt_balance * 0.001
        self.logger.info(
            "Pot %s: cash $%.2f, BTC %.8f (budget $%.2f)",
            self.pot, self.usdt_balance, self.base_balance, self.pot_budget,
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

    def on_candle(self, price, strategy_manager, exchange, symbol, timeframe, candle_data) -> Dict[str, dict]:
        """Run every pot on a closed candle: stops/targets first, then the
        pot's strategy. Returns what happened per pot."""
        results = {}
        for pot in self.pots.values():
            r = {"holding_before": pot.holding, "signal": None, "exit": None,
                 "trade": None, "note": None}
            try:
                r["exit"] = pot.trader.update_position(price)
                if pot.strategy is not None:
                    sig = strategy_manager.compute_signal_for(
                        pot.strategy, exchange, symbol, timeframe, candle_data,
                    )
                    r["signal"] = pot.last_signal = sig
                    if sig.direction == "bullish" and not pot.holding and self.cap_reached(pot):
                        r["note"] = f"skipped buy: {pot.max_buys_per_day} buys today already"
                        logger.info("Pot %s: %s", pot.name, r["note"])
                    else:
                        r["trade"] = pot.trader.handle_signal(sig, pot.order_pct)
            except Exception as exc:
                logger.exception("Pot %s failed on this candle: %s", pot.name, exc)
                r["note"] = f"error: {exc}"
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

    # ------------------------------------------------------------ cash moves

    def _real_money(self) -> bool:
        traders = [t for t in self.traders() if isinstance(t, PotLiveTrader)]
        return bool(traders) and traders[0].mode == TradingMode.LIVE

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

        label = lambda p, name: p.label if p else ("new money" if name == source else "unassigned")
        message = f"Moved ${amount:.2f} from {label(src, source)} to {label(dst, target)}"
        logger.info("Pots: %s", message)
        return {"message": message, "move": move}

    # ------------------------------------------------------- live safety check

    def reconcile(self) -> List[str]:
        """Live only: do the pots claim more cash or BTC than the exchange
        holds? Alerts once when that starts; returns the problems."""
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
        problems = []
        if cash > ex.get("USDT_total", 0.0) + max(0.5, cash * 0.01):
            problems.append(f"pots hold ${cash:.2f} cash but the exchange has ${ex.get('USDT_total', 0.0):.2f}")
        if btc > ex.get("BASE_total", 0.0) + 2e-05:
            problems.append(f"pots hold {btc:.8f} BTC but the exchange has {ex.get('BASE_total', 0.0):.8f}")
        if problems and not self._mismatch_alerted:
            self._mismatch_alerted = True
            logger.critical("Pot check: %s", "; ".join(problems))
            if self.notify:
                self.notify("🚨 Pots don't match the exchange", "; ".join(problems).capitalize()
                            + ". Check the account before the next trade.", severity="critical")
        elif not problems:
            self._mismatch_alerted = False
        return problems

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
    manager.restore_transfers()
    return manager
