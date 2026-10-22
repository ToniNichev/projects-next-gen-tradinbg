#!/usr/bin/env python3
"""
Long walk-forward check: run each strategy on its own over many
non-overlapping 30-day windows (default 24, about two years) using the
intrabar exit model, and print a per-window table plus a summary.

Uses BTC/USDT by default: Binance.US BTC/USD history only starts on
2025-02-19, while BTC/USDT goes back years and tracks the same price.

Usage:
    venv/bin/python scripts/walk_forward_long.py                # all strategies, 24 windows
    venv/bin/python scripts/walk_forward_long.py --windows 12 --strategies ema
    venv/bin/python scripts/walk_forward_long.py --save         # also write reports
"""
import argparse
import logging
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest import run_backtest  # noqa: E402

DAYS_BACK = 30
STRATEGIES = {
    "ema": "strategy_ema_enabled",
    "rsi_bb": "strategy_rsi_bb_enabled",
    "macd": "strategy_macd_enabled",
}


def only(strategy: str) -> dict:
    overrides = {flag: (name == strategy) for name, flag in STRATEGIES.items()}
    overrides["strategy_llm_enabled"] = False
    return overrides


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=int, default=24)
    parser.add_argument("--strategies", nargs="+", default=list(STRATEGIES), choices=list(STRATEGIES))
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--save", action="store_true", help="write a report per window to docs/backtest_reports/")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    ends = [now - timedelta(days=DAYS_BACK * i) for i in range(args.windows)]
    results = {s: [] for s in args.strategies}

    for i, end in enumerate(ends):
        for s in args.strategies:
            r = run_backtest(
                days_back=DAYS_BACK, config_overrides={**only(s), "symbol": args.symbol},
                end_date=end, save_report=args.save, intrabar_exits=True,
            )
            results[s].append(r)
            # backtest logs a lot; after the first run keep only warnings
            logging.disable(logging.INFO)
        print(f"window {i + 1}/{args.windows} done (ending {end.date()})", file=sys.stderr)

    bh = [r["buy_hold_pct"] for r in results[args.strategies[0]]]
    header = f"{'window_end':<11} {'B&H%':>7}" + "".join(f" | {s + ' trades':>11} {'pnl%':>6}" for s in args.strategies)
    print(f"\nSymbol: {args.symbol}, {args.windows} x {DAYS_BACK}-day windows, intrabar exits")
    print(header)
    for i, end in enumerate(ends):
        row = f"{str(end.date()):<11} {bh[i]:>7.2f}"
        for s in args.strategies:
            r = results[s][i]
            row += f" | {r['trades']:>11} {r['pnl_pct']:>6.2f}"
        print(row)

    print()
    up = [i for i, x in enumerate(bh) if x > 0]
    down = [i for i, x in enumerate(bh) if x <= 0]
    for s in args.strategies:
        p = [r["pnl_pct"] for r in results[s]]
        total = 1.0
        for x in p:
            total *= 1 + x / 100
        print(
            f"{s:<7} avg {statistics.mean(p):+.2f}%/window, median {statistics.median(p):+.2f}%, "
            f"{sum(x > 0 for x in p)}/{len(p)} positive, compounded {100 * (total - 1):+.2f}%, "
            f"trades {sum(r['trades'] for r in results[s])}, "
            f"avg in up months {statistics.mean([p[i] for i in up]) if up else 0:+.2f}%, "
            f"in down months {statistics.mean([p[i] for i in down]) if down else 0:+.2f}%"
        )
    total_bh = 1.0
    for x in bh:
        total_bh *= 1 + x / 100
    print(f"buy&hold compounded {100 * (total_bh - 1):+.2f}% ({len(up)} up / {len(down)} down months)")


if __name__ == "__main__":
    main()
