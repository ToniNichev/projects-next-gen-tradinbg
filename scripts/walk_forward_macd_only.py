#!/usr/bin/env python3
"""
Walk-forward validation of MACD-only 1h, isolating it from the 3-strategy
combo tested in 60964b0 (which only checked 3 windows and mixed in EMA/RSI_BB).

Runs the same 6 non-overlapping 30-day windows as walk_forward_ema_only.py
for a direct comparison, now that histogram_threshold is actually wired
through config (60964b0) instead of stuck at 0.0.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest import run_backtest  # noqa: E402

MACD_ONLY_OVERRIDES = {
    "strategy_ema_enabled": False,
    "strategy_rsi_bb_enabled": False,
    "strategy_macd_enabled": True,
    "strategy_llm_enabled": False,
}

NUM_WINDOWS = 6
DAYS_BACK = 30


def main():
    now = datetime.now(timezone.utc)
    summary = []
    for i in range(NUM_WINDOWS):
        end_date = now - timedelta(days=DAYS_BACK * i)
        print(f"\n=== Window {i + 1}/{NUM_WINDOWS}: ending {end_date.date()} ===")
        result = run_backtest(
            days_back=DAYS_BACK,
            config_overrides=dict(MACD_ONLY_OVERRIDES),
            save_report=True,
            end_date=end_date,
        )
        summary.append({
            "window_end": end_date.date().isoformat(),
            "trades": result["trades"],
            "pnl_pct": result["pnl_pct"],
            "buy_hold_pct": result["buy_hold_pct"],
            "max_drawdown_pct": result["max_drawdown_pct"],
            "sharpe_ratio": result["sharpe_ratio"],
        })

    print("\n" + "=" * 100)
    print(f"{'window_end':<12} {'trades':>7} {'pnl_pct':>10} {'buy_hold_pct':>13} {'max_dd_pct':>11} {'sharpe':>8}")
    for row in summary:
        print(
            f"{row['window_end']:<12} {row['trades']:>7} {row['pnl_pct']:>10.2f} "
            f"{row['buy_hold_pct']:>13.2f} {row['max_drawdown_pct']:>11.2f} {row['sharpe_ratio']:>8.2f}"
        )

    avg_pnl = sum(r["pnl_pct"] for r in summary) / len(summary)
    positive = sum(1 for r in summary if r["pnl_pct"] > 0)
    print(f"\nAverage pnl_pct: {avg_pnl:.2f}  |  Positive windows: {positive}/{len(summary)}")


if __name__ == "__main__":
    main()
