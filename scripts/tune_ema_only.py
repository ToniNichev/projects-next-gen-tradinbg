#!/usr/bin/env python3
"""
Parameter sweep for the EMA-only strategy across the same 6 non-overlapping
walk-forward windows used in scripts/walk_forward_ema_only.py, searching for
a config with a consistent positive edge (not just a good single window).

Baseline reflects the config actually stored in data/trading.db right now
(DB overrides .env for these fields - see config.py BotConfig.load()):
  min_signal_confidence=0.2, min_trend_strength=5e-05,
  require_volume_confirmation=False, short/long window=12/26,
  stop_loss_pct=0.04, take_profit_pct=0.08, trailing_stop_pct=0.025,
  use_atr_stops=False, order_pct=0.4.

OHLCV fetches are memoized per (symbol, timeframe, since, limit) so re-testing
the same 6 windows across many param combos doesn't re-hit the exchange API
each time - only the first combo pays the network cost.
"""
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ccxt  # noqa: E402
from backtest import run_backtest  # noqa: E402

_real_fetch_ohlcv = ccxt.binanceus.fetch_ohlcv


@lru_cache(maxsize=None)
def _cached_fetch(symbol, timeframe, since, limit):
    exchange = ccxt.binanceus({"enableRateLimit": True})
    return _real_fetch_ohlcv(exchange, symbol, timeframe, since=since, limit=limit)


def _patched_fetch_ohlcv(self, symbol, timeframe="1m", since=None, limit=None, params={}):
    return list(_cached_fetch(symbol, timeframe, since, limit))


ccxt.binanceus.fetch_ohlcv = _patched_fetch_ohlcv

BASELINE = {
    "min_signal_confidence": 0.2,
    "min_trend_strength": 5e-05,
    "require_volume_confirmation": False,
    "require_macd_confirmation": False,
    "short_window": 12,
    "long_window": 26,
    "stop_loss_pct": 0.04,
    "take_profit_pct": 0.08,
    "trailing_stop_pct": 0.025,
    "use_atr_stops": False,
    "use_trailing_stop": True,
    "order_pct": 0.4,
    "max_position_size": 0.5,
    "min_position_size": 0.2,
    "max_trades_per_day": 10,
    "volume_threshold": 1.0,
    "strategy_ema_enabled": True,
    "strategy_rsi_bb_enabled": False,
    "strategy_macd_enabled": False,
    "strategy_llm_enabled": False,
}

# Each variant overrides a subset of BASELINE. "baseline" itself is included
# as variant 0 so it's directly comparable in the same table.
VARIANTS = {
    "baseline": {},
    "conf_0.35": {"min_signal_confidence": 0.35},
    "conf_0.5": {"min_signal_confidence": 0.5},
    "trend_1e-4": {"min_trend_strength": 0.0001},
    "trend_2e-4": {"min_trend_strength": 0.0002},
    "vol_confirm_on": {"require_volume_confirmation": True},
    "wide_ema_20_50": {"short_window": 20, "long_window": 50},
    "tight_ema_8_21": {"short_window": 8, "long_window": 21},
    "wider_tp_0.12": {"take_profit_pct": 0.12},
    "wider_trail_0.04": {"trailing_stop_pct": 0.04},
    "conf_0.35+trend_1e-4": {"min_signal_confidence": 0.35, "min_trend_strength": 0.0001},
    "conf_0.35+vol_on": {"min_signal_confidence": 0.35, "require_volume_confirmation": True},
}

NUM_WINDOWS = 6
DAYS_BACK = 30


def main():
    now = datetime.now(timezone.utc)
    window_ends = [now - timedelta(days=DAYS_BACK * i) for i in range(NUM_WINDOWS)]

    rows = []
    for variant_name, overrides in VARIANTS.items():
        config_overrides = dict(BASELINE)
        config_overrides.update(overrides)

        window_results = []
        for end_date in window_ends:
            result = run_backtest(
                days_back=DAYS_BACK,
                config_overrides=dict(config_overrides),
                save_report=False,
                end_date=end_date,
            )
            window_results.append(result["pnl_pct"])

        avg_pnl = sum(window_results) / len(window_results)
        positive_windows = sum(1 for p in window_results if p > 0)
        rows.append((variant_name, avg_pnl, positive_windows, window_results))
        print(f"{variant_name:<24} avg={avg_pnl:>7.2f}%  positive={positive_windows}/{NUM_WINDOWS}  "
              f"windows={[round(p, 2) for p in window_results]}")

    print("\n" + "=" * 100)
    print("RANKED BY AVERAGE PNL ACROSS 6 WINDOWS")
    print("=" * 100)
    for name, avg_pnl, positive_windows, window_results in sorted(rows, key=lambda r: r[1], reverse=True):
        print(f"{name:<24} avg={avg_pnl:>7.2f}%  positive={positive_windows}/{NUM_WINDOWS}")


if __name__ == "__main__":
    main()
