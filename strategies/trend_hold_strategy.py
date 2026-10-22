"""
Trend-Hold Strategy - hold BTC while the daily trend is up, cash when it's down.

Rule (validated out of sample in scripts/trend_hold_test.py):
- Look at the last fully closed daily candle and its N-day simple average.
- Close more than `band` above the average  -> bullish (buy / keep holding)
- Close more than `band` below the average  -> bearish (sell / stay in cash)
- In between                                -> neutral (keep whatever we have)

The bot runs on hourly candles and only keeps a few weeks of them, so this
strategy fetches daily candles itself. It only ever uses days that had fully
closed by the time of the latest hourly candle, so backtests can't see the
future. Daily candles are cached; a closed day never changes.

It is meant to be the only enabled strategy, with the bot's trailing stop
turned off (BOT_USE_TRAILING_STOP=false): exits come from the trend rule.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .base_strategy import BaseStrategy, StrategySignal
from .constants import StrategyNames

logger = logging.getLogger(__name__)

DAY_MS = 24 * 60 * 60 * 1000
_TIMEFRAME_MS = {"m": 60_000, "h": 3_600_000, "d": DAY_MS, "w": 7 * DAY_MS}


def _timeframe_ms(timeframe: str) -> int:
    return int(timeframe[:-1]) * _TIMEFRAME_MS[timeframe[-1]]


class TrendHoldStrategy(BaseStrategy):
    """Daily close vs N-day moving average, all in or all out."""

    def __init__(self, config: dict):
        super().__init__(StrategyNames.TREND_HOLD, config)
        self.ma_days = int(config.get("ma_days", 100))
        self.band = float(config.get("band", 0.01))
        # Share of the USDT balance to buy with. Just under 1.0 so the fee fits.
        self.position_size = float(config.get("position_size", 0.99))
        # Optional disaster stop below entry; 0 = none (the tested rule has none)
        self.emergency_stop_pct = float(config.get("emergency_stop_pct", 0.0))
        self._daily_closes: Dict[int, float] = {}  # day start (ms) -> close

    # ------------------------------------------------------------------ data

    def _completed_days(self, exchange, symbol: str, as_of_ms: int) -> List[float]:
        """Closes of the last `ma_days` days that had closed by `as_of_ms`."""
        last_day = (as_of_ms // DAY_MS) * DAY_MS - DAY_MS  # last day closed by as_of
        first_day = last_day - (self.ma_days - 1) * DAY_MS
        wanted = range(first_day, last_day + 1, DAY_MS)

        if any(d not in self._daily_closes for d in wanted):
            self._fetch(exchange, symbol, first_day)

        closes = [self._daily_closes[d] for d in wanted if d in self._daily_closes]
        if len(closes) < self.ma_days:
            raise ValueError(
                f"Not enough daily candles for {self.name} "
                f"(need {self.ma_days}, got {len(closes)})"
            )
        return closes

    def _fetch(self, exchange, symbol: str, since_ms: int) -> None:
        now_ms = int(time.time() * 1000)
        since = since_ms
        while since < now_ms:
            batch = exchange.fetch_ohlcv(symbol, "1d", since=since, limit=1000)
            if not batch:
                break
            for ts, _o, _h, _l, close, _v in batch:
                # Only cache days that have really finished; today's candle is
                # still moving and would be wrong once the day closes.
                if ts + DAY_MS <= now_ms:
                    self._daily_closes[int(ts)] = float(close)
            since = batch[-1][0] + 1
            if len(batch) < 1000:
                break

    # ---------------------------------------------------------------- signal

    def compute_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        if candle_data:
            last = candle_data[-1]
            as_of_ms = int(last[0]) + _timeframe_ms(timeframe)  # close time of last candle
            price = float(last[4])
        else:
            as_of_ms = int(time.time() * 1000)
            price = float(exchange.fetch_ticker(symbol)["last"])

        closes = self._completed_days(exchange, symbol, as_of_ms)
        ma = sum(closes) / len(closes)
        daily_close = closes[-1]
        distance = daily_close / ma - 1

        if distance > self.band:
            direction, confidence = "bullish", 1.0
        elif distance < -self.band:
            direction, confidence = "bearish", 1.0
        else:
            direction, confidence = "neutral", 0.0

        stop_loss = price * (1 - self.emergency_stop_pct) if self.emergency_stop_pct > 0 else price * 1e-6
        return StrategySignal(
            direction=direction,
            price=price,
            confidence=confidence,
            timestamp=datetime.fromtimestamp(as_of_ms / 1000, tz=timezone.utc),
            strategy_name=self.name,
            # Exits come from the trend rule, so stop/target are effectively off
            stop_loss=stop_loss,
            take_profit=price * 100,
            position_size=self.position_size,
            indicators={
                "daily_close": daily_close,
                f"sma_{self.ma_days}d": ma,
                "distance_pct": distance * 100,
            },
            info={"rule": f"daily close vs {self.ma_days}-day average, band {self.band:.1%}"},
        )

    def get_description(self) -> str:
        return (
            f"Hold BTC while the daily close is more than {self.band:.0%} above its "
            f"{self.ma_days}-day average; move to cash when it is more than {self.band:.0%} below."
        )

    def get_parameters(self) -> Dict[str, object]:
        return {
            "ma_days": self.ma_days,
            "band": self.band,
            "position_size": self.position_size,
            "emergency_stop_pct": self.emergency_stop_pct,
        }
