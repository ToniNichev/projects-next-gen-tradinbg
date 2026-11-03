"""After a restart, a strategy's dashboard chart shows the last day at once
(it used to say "Waiting for data…" until two hourly checks had run)."""

import math

from strategies.rsi_bb_strategy import RSIBollingerBandsStrategy
from strategies.strategy_manager import StrategyManager

HOUR = 3_600_000


def candles(n=200, start=1_760_000_000_000):
    out = []
    for i in range(n):
        p = 77000 + 600 * math.sin(i / 7) + 40 * math.sin(i * 1.7)
        out.append([start + i * HOUR, p, p + 50, p - 50, p + 10, 5 + (i % 3)])
    return out


def test_restart_fills_the_last_day_of_the_chart():
    rsi = RSIBollingerBandsStrategy({})
    sm = StrategyManager([rsi])
    data = candles()
    before = dict(vars(rsi))

    added = sm.backfill_history(rsi, None, "BTC/USD", "1h", data)
    sm.compute_signal_for(rsi, None, "BTC/USD", "1h", data)    # the current one
    hist = list(sm.signal_history[rsi.name])
    assert added == 24 and len(hist) == 25
    times = [h["t"] for h in hist]
    assert times == sorted(times) and len(set(times)) == 25     # in order, one per hour
    assert all("rsi" in h["i"] for h in hist)
    assert {k: v for k, v in vars(rsi).items() if k in before} == before  # real strategy untouched


def test_no_backfill_when_history_exists_or_too_few_candles():
    rsi = RSIBollingerBandsStrategy({})
    sm = StrategyManager([rsi])
    assert sm.backfill_history(rsi, None, "BTC/USD", "1h", candles(40)) == 0
    data = candles()
    sm.compute_signal_for(rsi, None, "BTC/USD", "1h", data[:-1])
    sm.compute_signal_for(rsi, None, "BTC/USD", "1h", data)
    assert sm.backfill_history(rsi, None, "BTC/USD", "1h", data) == 0
