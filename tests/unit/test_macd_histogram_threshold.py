"""
Regression tests for the MACD_Volume_Momentum histogram_threshold bug.

Bug (docs/backtest_reports, 2026-07-08): MACDVolumeStrategy.histogram_threshold
was never read by BotConfig.get_strategy_configs(), so it silently stayed at
the code default of 0.0 regardless of what was configured. A threshold of 0.0
lets the near-zero histogram right at a fresh crossover count as "confirmed",
which caused overtrading and was the main driver of the 3-strategy config
losing money on every backtested window.

The fix does two things, both covered here:
  1. Wires BotConfig.strategy_macd_histogram_threshold through
     get_strategy_configs()["macd_volume"]["histogram_threshold"].
  2. Normalises the comparison to |histogram| / price (matching
     EMACrossoverStrategy's min_trend_strength convention) instead of a raw
     dollar value, so the filter means the same thing regardless of BTC's
     price level.
"""

import numpy as np
import pytest

from config import BotConfig
from strategies.macd_volume_strategy import MACDVolumeStrategy


def _step_candles(base_price: float, step_pct: float, n: int = 150, step_at: int = 147):
    """Flat price series with a clean step near the end (no noise).

    Produces a bullish MACD crossover that is still within the strategy's
    default 3-bar recent-crossover lookback, with histogram still rising
    (histogram_change > 0) at the last bar.
    """
    close = np.full(n, base_price, dtype=float)
    close[step_at:] += base_price * step_pct

    candles = []
    t0 = 1_700_000_000_000
    for i, c in enumerate(close):
        o = close[i - 1] if i > 0 else c
        h = max(o, c) * 1.0005
        l = min(o, c) * 0.9995
        candles.append([t0 + i * 3_600_000, o, h, l, c, 100.0])
    return candles


def _base_config(histogram_threshold: float) -> dict:
    return {
        "histogram_threshold": histogram_threshold,
        "use_volume_filter": False,
        "use_momentum_filter": False,
        "detect_divergence": False,
    }


def test_histogram_threshold_wired_through_config():
    """BotConfig must actually pass its histogram_threshold field through —
    this is the wiring bug itself. Also asserts the new default isn't the
    old buggy 0.0."""
    cfg = BotConfig(binance_api_key="x", binance_api_secret="y")
    macd_cfg = cfg.get_strategy_configs()["macd_volume"]

    assert "histogram_threshold" in macd_cfg
    assert macd_cfg["histogram_threshold"] == cfg.strategy_macd_histogram_threshold
    assert macd_cfg["histogram_threshold"] > 0.0


def test_histogram_threshold_filters_weak_signal():
    """A histogram just under the configured threshold (as a fraction of
    price) must not produce a signal; a histogram clearly over it must."""
    weak = _step_candles(base_price=100.0, step_pct=0.002)   # hist/price ~0.00024, below 0.0003
    strong = _step_candles(base_price=100.0, step_pct=0.005)  # hist/price ~0.00059, above 0.0003

    strat = MACDVolumeStrategy(_base_config(histogram_threshold=0.0003))

    weak_signal = strat.compute_signal(None, "X/Y", "1h", candle_data=weak)
    strong_signal = strat.compute_signal(None, "X/Y", "1h", candle_data=strong)

    assert weak_signal.direction == "neutral"
    assert strong_signal.direction == "bullish"


def test_higher_threshold_suppresses_previously_confirmed_signal():
    """Same data, only the threshold changes — raising it past the
    signal's histogram/price ratio must flip a confirmed signal to neutral."""
    candles = _step_candles(base_price=100.0, step_pct=0.005)  # hist/price ~0.00059

    low_threshold = MACDVolumeStrategy(_base_config(histogram_threshold=0.0003))
    high_threshold = MACDVolumeStrategy(_base_config(histogram_threshold=0.005))

    assert low_threshold.compute_signal(None, "X/Y", "1h", candle_data=candles).direction == "bullish"
    assert high_threshold.compute_signal(None, "X/Y", "1h", candle_data=candles).direction == "neutral"


def test_threshold_is_scale_invariant_across_price_levels():
    """The whole point of comparing histogram/price instead of a raw dollar
    value: the same relative move must trigger identically whether BTC is
    at $100 or $100,000. This is the property a flat-dollar threshold
    (the pre-fix behaviour) would NOT have."""
    strat = MACDVolumeStrategy(_base_config(histogram_threshold=0.0003))

    low_price = _step_candles(base_price=100.0, step_pct=0.005)
    high_price = _step_candles(base_price=100_000.0, step_pct=0.005)

    low_signal = strat.compute_signal(None, "X/Y", "1h", candle_data=low_price)
    high_signal = strat.compute_signal(None, "X/Y", "1h", candle_data=high_price)

    assert low_signal.direction == high_signal.direction == "bullish"
    low_hist_pct = low_signal.indicators["histogram"] / low_signal.price
    high_hist_pct = high_signal.indicators["histogram"] / high_signal.price
    assert low_hist_pct == pytest.approx(high_hist_pct, rel=1e-6)
