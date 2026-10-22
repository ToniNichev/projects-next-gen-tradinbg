#!/usr/bin/env python3
"""
Test a simple trend-hold rule on daily BTC/USDT, separate from the bot's
strategy framework (which can't see enough history for long averages).

Rule: at each daily close, if price is above its N-day simple moving
average (by more than `band`), hold BTC; if it is below by more than
`band`, hold cash; in between, keep the current state. Trades execute at
the next day's open, so no future information is used. Costs match the
bot (fee 0.075% + slippage 0.05% per side). Position is 100% in or out.

Tuning uses only the "train" year. The chosen setting is then judged on
the "test" year and on earlier years it never saw.

Usage:
    venv/bin/python scripts/trend_hold_test.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SYMBOL = "BTC/USDT"
COST = 0.00075 + 0.0005  # fee + slippage, per side
MA_LENGTHS = [20, 30, 50, 100, 150, 200]
BANDS = [0.0, 0.01, 0.02, 0.03]

TRAIN = ("2024-10-22", "2025-10-22")
TEST = ("2025-10-22", "2026-10-22")
OLDER = [
    ("2020-10-22", "2021-10-22"),
    ("2021-10-22", "2022-10-22"),
    ("2022-10-22", "2023-10-22"),
    ("2023-10-22", "2024-10-22"),
]


def fetch_daily() -> pd.DataFrame:
    ex = ccxt.binanceus({"enableRateLimit": True})
    since = ex.parse8601("2019-01-01T00:00:00Z")
    rows = []
    while True:
        batch = ex.fetch_ohlcv(SYMBOL, "1d", since=since, limit=1000)
        if not batch:
            break
        rows.extend(batch)
        since = batch[-1][0] + 1
        if len(batch) < 1000:
            break
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates("ts").set_index(pd.to_datetime(df["ts"], unit="ms", utc=True).dt.normalize())
    return df[["open", "close"]]


def positions(df: pd.DataFrame, ma_len: int, band: float) -> pd.Series:
    """1 = hold BTC, 0 = cash, decided at each close (acted on next open)."""
    ma = df["close"].rolling(ma_len).mean()
    state, out = 0, []
    for close, m in zip(df["close"], ma):
        if not np.isnan(m):
            if close > m * (1 + band):
                state = 1
            elif close < m * (1 - band):
                state = 0
        out.append(state)
    return pd.Series(out, index=df.index)


def evaluate(df: pd.DataFrame, pos: pd.Series, start: str, end: str) -> dict:
    """Simulate from `start` to `end`: decisions at close, fills at next open."""
    period = df.loc[start:end]
    held = pos.shift(1).loc[start:end].fillna(0)  # yesterday's decision, filled at today's open
    equity, in_btc, trades = 1.0, 0, 0
    values = []
    prev_close = None
    for (day, row), want in zip(period.iterrows(), held):
        if in_btc and prev_close is not None:
            equity *= row["open"] / prev_close  # overnight gap
        if want != in_btc:
            equity *= 1 - COST
            trades += 1
            in_btc = int(want)
        if in_btc:
            equity *= row["close"] / row["open"]
        prev_close = row["close"]
        values.append(equity)
    if in_btc:
        equity *= 1 - COST  # sell at the end so results are comparable
    v = pd.Series(values, index=period.index)
    daily = v.pct_change().dropna()
    sharpe = float(daily.mean() / daily.std() * np.sqrt(365)) if daily.std() > 0 else 0.0
    return {
        "return": 100 * (equity - 1),
        "max_dd": 100 * float((v / v.cummax() - 1).min()),
        "sharpe": sharpe,
        "trades": trades,
        "in_market": 100 * float(held.mean()),
    }


def buy_hold(df: pd.DataFrame, start: str, end: str) -> dict:
    return evaluate(df, pd.Series(1, index=df.index), start, end)


def fmt(r: dict) -> str:
    return (f"return {r['return']:+7.1f}%  max drawdown {r['max_dd']:6.1f}%  "
            f"sharpe {r['sharpe']:5.2f}  trades {r['trades']:3d}  in market {r['in_market']:5.1f}%")


def main():
    df = fetch_daily()
    print(f"{SYMBOL} daily, {df.index[0].date()} to {df.index[-1].date()}, cost {COST * 100:.3f}% per side\n")

    # 1. Tune on the train year only
    print(f"TRAIN {TRAIN[0]} to {TRAIN[1]}   buy & hold: {fmt(buy_hold(df, *TRAIN))}")
    grid = []
    for n in MA_LENGTHS:
        for band in BANDS:
            r = evaluate(df, positions(df, n, band), *TRAIN)
            grid.append((n, band, r))
            print(f"  MA {n:3d}  band {band * 100:3.0f}%   {fmt(r)}")
    best_n, best_band, _ = max(grid, key=lambda g: g[2]["sharpe"])
    print(f"\nChosen on train (best Sharpe): MA {best_n}, band {best_band * 100:.0f}%\n")

    # 2. Judge the chosen setting on data it never saw
    pos = positions(df, best_n, best_band)
    print("OUT-OF-SAMPLE (chosen setting vs buy & hold)")
    for start, end in [TEST] + OLDER:
        tag = "TEST " if (start, end) == TEST else "older"
        print(f"  {tag} {start} to {end}")
        print(f"    trend-hold  {fmt(evaluate(df, pos, start, end))}")
        print(f"    buy & hold  {fmt(buy_hold(df, start, end))}")

    # 3. For context only (not used to choose): every setting on the test year
    print(f"\nCONTEXT ONLY - all settings on the test year {TEST[0]} to {TEST[1]}")
    for n in MA_LENGTHS:
        row = "  ".join(
            f"b{int(b * 100)}% {evaluate(df, positions(df, n, b), *TEST)['return']:+6.1f}%" for b in BANDS
        )
        print(f"  MA {n:3d}: {row}")


if __name__ == "__main__":
    main()
