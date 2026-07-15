#!/usr/bin/env python3
"""
Out-of-sample walk-forward check for the EMA-only 1h config (the one
actually wired up live) against a period none of the prior sweeps have
touched.

walk_forward_ema_only.py / walk_forward_macd_only.py / walk_forward_rsi_bb_only.py
all cover the same 6 windows spanning roughly the trailing 180 days from
whenever they were run. This script picks up immediately where that span
ends and runs 6 more non-overlapping 30-day windows further back (roughly
180-360 days back), so the result reflects a genuinely different period/
regime instead of re-testing already-seen data.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest import run_backtest  # noqa: E402

EMA_ONLY_OVERRIDES = {
    "strategy_ema_enabled": True,
    "strategy_rsi_bb_enabled": False,
    "strategy_macd_enabled": False,
    "strategy_llm_enabled": False,
}

NUM_WINDOWS = 6
DAYS_BACK = 30
# Prior sweeps already cover ~0-180 days back; start right after that.
OFFSET_DAYS = 180


def main():
    now = datetime.now(timezone.utc)
    summary = []
    for i in range(NUM_WINDOWS):
        end_date = now - timedelta(days=OFFSET_DAYS + DAYS_BACK * i)
        print(f"\n=== Window {i + 1}/{NUM_WINDOWS}: ending {end_date.date()} ===")
        result = run_backtest(
            days_back=DAYS_BACK,
            config_overrides=dict(EMA_ONLY_OVERRIDES),
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
