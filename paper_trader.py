import csv
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from strategy import StrategySignal


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

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class PaperTrader:
    def __init__(
        self,
        initial_usdt: float = 1000.0,
        fee_rate: float = 0.00075,
        slippage: float = 0.0005,
        log_path: str = "trade_log.csv",
    ):
        self.usdt_balance = initial_usdt
        self.base_balance = 0.0
        self.fee_rate = fee_rate
        self.slippage = slippage
        self.log_path = log_path
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
            ]
        )
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="") as f:
                f.write(header + "\n")

    def _log_trade(self, trade: TradeRecord) -> None:
        logging.info(
            "Paper trade -> %s %.4f @ %.2f | usdt=%.2f base=%.6f",
            trade.side,
            trade.amount,
            trade.price,
            trade.usdt_balance,
            trade.base_balance,
        )
        if not self.log_path:
            return
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
                ]
            )

    def get_balances(self) -> Dict[str, float]:
        return {"USDT": self.usdt_balance, "BASE": self.base_balance}

    def handle_signal(
        self, signal: "StrategySignal", order_pct: float
    ) -> Optional[TradeRecord]:
        if signal.direction == "bullish":
            return self._buy(signal.price, order_pct, signal)
        if signal.direction == "bearish":
            return self._sell(signal.price, order_pct, signal)
        return None

    def _buy(self, price: float, order_pct: float, signal) -> Optional[TradeRecord]:
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

        trade = TradeRecord(
            side="buy",
            price=fill_price,
            amount=amount,
            notional=notional,
            fee=fee,
            slippage=fill_price - price,
            usdt_balance=self.usdt_balance,
            base_balance=self.base_balance,
            timestamp=datetime.utcnow().isoformat(),
            signal=signal.to_dict(),
        )
        self._log_trade(trade)
        return trade

    def _sell(self, price: float, order_pct: float, signal) -> Optional[TradeRecord]:
        if self.base_balance <= 0:
            return None
        amount = self.base_balance * order_pct
        if amount <= 0:
            return None

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
            timestamp=datetime.utcnow().isoformat(),
            signal=signal.to_dict(),
        )
        self._log_trade(trade)
        return trade

