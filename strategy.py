from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Literal

import pandas as pd


@dataclass
class StrategySignal:
    direction: Literal["bullish", "bearish", "neutral"]
    price: float
    short_ema: float
    long_ema: float
    trend_strength: float
    timestamp: datetime
    info: Dict[str, float]

    def to_dict(self) -> Dict[str, object]:
        return {
            "direction": self.direction,
            "price": self.price,
            "short_ema": self.short_ema,
            "long_ema": self.long_ema,
            "trend_strength": self.trend_strength,
            "timestamp": self.timestamp.isoformat(),
            "info": self.info,
        }


def compute_signal(
    exchange,
    symbol: str,
    timeframe: str,
    short_window: int = 20,
    long_window: int = 50,
    candle_data: list = None,
) -> StrategySignal:
    # Use buffered candle data if provided, otherwise fetch from exchange
    if candle_data is not None and len(candle_data) > 0:
        ohlcv = candle_data
    else:
        history_limit = max(long_window * 2, 120)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=history_limit)

    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    if len(df) < long_window:
        raise ValueError("not enough candles for the configured long window")

    df["short_ema"] = df["close"].ewm(span=short_window, adjust=False).mean()
    df["long_ema"] = df["close"].ewm(span=long_window, adjust=False).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last.short_ema > last.long_ema and prev.short_ema <= prev.long_ema:
        direction = "bullish"
    elif last.short_ema < last.long_ema and prev.short_ema >= prev.long_ema:
        direction = "bearish"
    else:
        direction = "neutral"

    price = float(last.close)
    trend_strength = abs(last.short_ema - last.long_ema) / price
    info = {
        "short_window": short_window,
        "long_window": long_window,
        "last_timestamp": int(last.timestamp),
    }

    return StrategySignal(
        direction=direction,
        price=price,
        short_ema=float(last.short_ema),
        long_ema=float(last.long_ema),
        trend_strength=trend_strength,
        timestamp=datetime.utcfromtimestamp(int(last.timestamp) / 1000),
        info=info,
    )

