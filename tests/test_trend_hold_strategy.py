"""Tests for TrendHoldStrategy (daily close vs N-day average)."""

from datetime import datetime, timezone

import pytest

from config import BotConfig
from strategies import TrendHoldStrategy
from strategies.constants import StrategyNames

DAY = 24 * 3600 * 1000
HOUR = 3600 * 1000
START = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


class FakeExchange:
    """Serves daily candles; closes[i] belongs to day START + i*DAY."""

    def __init__(self, closes):
        self.candles = [[START + i * DAY, c, c, c, c, 1.0] for i, c in enumerate(closes)]
        self.calls = 0

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=1000):
        assert timeframe == "1d"
        self.calls += 1
        return [c for c in self.candles if c[0] >= since][:limit]


def hourly_candle_closing_at(day_index, price=100.0):
    """The 1h candle whose close is the end of day `day_index` (00:00 next day)."""
    open_ts = START + (day_index + 1) * DAY - HOUR
    return [open_ts, price, price, price, price, 1.0]


def strategy(**kw):
    return TrendHoldStrategy({"ma_days": 5, "band": 0.01, **kw})


def test_bullish_above_band():
    ex = FakeExchange([100, 100, 100, 100, 110])  # avg 102, close 110
    sig = strategy().compute_signal(ex, "BTC/USDT", "1h", [hourly_candle_closing_at(4, 111)])
    assert sig.direction == "bullish"
    assert sig.confidence == 1.0
    assert sig.price == 111
    assert sig.position_size == 0.99
    assert sig.indicators["daily_close"] == 110


def test_bearish_below_band():
    ex = FakeExchange([100, 100, 100, 100, 90])  # avg 98, close 90
    sig = strategy().compute_signal(ex, "BTC/USDT", "1h", [hourly_candle_closing_at(4)])
    assert sig.direction == "bearish"


def test_neutral_inside_band():
    ex = FakeExchange([100, 100, 100, 100, 100.5])
    sig = strategy().compute_signal(ex, "BTC/USDT", "1h", [hourly_candle_closing_at(4)])
    assert sig.direction == "neutral"
    assert sig.confidence == 0.0


def test_ignores_days_not_closed_yet():
    # Day 5 is a huge spike, but at the end of day 4 it hasn't happened yet
    ex = FakeExchange([100, 100, 100, 100, 90, 1000])
    sig = strategy().compute_signal(ex, "BTC/USDT", "1h", [hourly_candle_closing_at(4)])
    assert sig.direction == "bearish"
    assert sig.indicators["daily_close"] == 90

    # One hour before day 5 closes, the latest closed day is day 4
    candle = hourly_candle_closing_at(5)
    candle[0] -= HOUR
    ex = FakeExchange([100, 100, 100, 100, 100, 90, 1000])
    sig = strategy().compute_signal(ex, "BTC/USDT", "1h", [candle])
    assert sig.indicators["daily_close"] == 100


def test_caches_daily_candles():
    ex = FakeExchange([100] * 10)
    s = strategy()
    for day in range(5, 9):
        s.compute_signal(ex, "BTC/USDT", "1h", [hourly_candle_closing_at(day)])
    assert ex.calls == 1


def test_not_enough_history_raises():
    ex = FakeExchange([100, 100, 100])
    with pytest.raises(ValueError, match="Not enough daily candles"):
        strategy().compute_signal(ex, "BTC/USDT", "1h", [hourly_candle_closing_at(2)])


def test_stops_are_effectively_off_unless_emergency_stop_set():
    ex = FakeExchange([100, 100, 100, 100, 110])
    candle = [hourly_candle_closing_at(4, 100)]
    sig = strategy().compute_signal(ex, "BTC/USDT", "1h", candle)
    assert 0 < sig.stop_loss < 1
    assert sig.take_profit >= 100 * 100

    sig = strategy(emergency_stop_pct=0.2).compute_signal(FakeExchange([100] * 4 + [110]), "BTC/USDT", "1h", candle)
    assert sig.stop_loss == pytest.approx(80)


def test_registered_in_config_and_names():
    configs = BotConfig(binance_api_key="", binance_api_secret="").get_strategy_configs()
    assert configs["trend_hold"]["ma_days"] == 100
    assert configs["trend_hold"]["enabled"] is False
    assert StrategyNames.TREND_HOLD in StrategyNames.all_names()
    assert StrategyNames.get_config_key(StrategyNames.TREND_HOLD) == "strategy_trend_enabled"
