"""
Each money pot's result over time, next to just holding BTC.

One point per closed hourly candle. A pot's value is rebuilt from its trade
records (cash and BTC after each trade) and its cash moves. Each pot's line
starts when the pot began; "holding BTC" starts with the earliest pot.

The % is time-weighted: each hour's change leaves out money moved in or out
that hour, and the hours are chained. Before (2026-11-17) it was value / money
put in, so moving $48 into a $6 pot that was down $0.69 made its line jump
from -11% to -1%. A pot's % now compares straight with BTC's own change over
the same time ("hold_pct"). The dollar result (value - money put in) is sent
too, as "gain".
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

# Trades are stamped a moment after the candle that triggered them closes
GRACE = timedelta(minutes=5)


def _ts(value) -> datetime:
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_pot_performance(pots: List[Dict], candles: List[Dict], candle_hours: float = 1.0) -> Dict:
    """
    pots:    dicts with name, label, start_time, start_cash,
             trades [{timestamp, usdt_balance, base_balance}],
             moves [{timestamp, amount}]  (+ into the pot, - out of it)
    candles: dicts with timestamp (candle open, UTC) and close, oldest first
    """
    if not pots or not candles:
        return {"pots": [], "hold": []}
    step = timedelta(hours=candle_hours)
    now = datetime.now(timezone.utc)
    # Only candles that have closed (the history can include the one still forming)
    closes = [(_ts(c["timestamp"]) + step, float(c["close"])) for c in candles
              if _ts(c["timestamp"]) + step <= now]
    if not closes:
        return {"pots": [], "hold": []}
    start = min(_ts(p["start_time"]) for p in pots)
    first = next((i for i, (t, _) in enumerate(closes) if t + GRACE >= start), None)
    if first is None:
        return {"pots": [], "hold": []}
    closes = closes[first:]
    hold_price = closes[0][1]
    hold = [{"time": t.isoformat(), "pct": round((p / hold_price - 1) * 100, 4), "price": p}
            for t, p in closes]

    out = []
    for pot in pots:
        events = [(_ts(t["timestamp"]), 0, t) for t in pot.get("trades", [])]
        events += [(_ts(m["timestamp"]), 1, m) for m in pot.get("moves", [])]
        events.sort(key=lambda e: (e[0], e[1]))
        cash = invested = float(pot["start_cash"])
        btc, k = 0.0, 0
        pot_start = _ts(pot["start_time"])
        points = []
        growth = 1.0                        # chained hourly growth (time-weighted)
        prev_value = float(pot["start_cash"])
        moved = 0.0                         # money moved in (+) / out (-) since the last point
        for t, price in closes:
            while k < len(events) and events[k][0] <= t + GRACE:
                _, kind, e = events[k]
                if kind == 0:
                    cash, btc = float(e["usdt_balance"]), float(e["base_balance"])
                else:
                    cash += float(e["amount"])
                    invested += float(e["amount"])
                    moved += float(e["amount"])
                k += 1
            if t + GRACE < pot_start:
                # Before the pot began nothing counts as a result yet
                prev_value = cash + btc * price
                moved = 0.0
                continue
            value = cash + btc * price
            # This hour's change without the money moved in or out. An
            # (almost) empty pot has no change to measure.
            if prev_value > 0.01:
                growth *= (value - moved) / prev_value
            prev_value = value
            points.append({
                "time": t.isoformat(),
                "pct": round((growth - 1) * 100, 4),
                "value": round(value, 4),
                "invested": round(invested, 4),
                "gain": round(value - invested, 4),
                "moved": round(moved, 4),
                "holding": btc * price >= 1.0,  # dust doesn't count as holding
            })
            moved = 0.0
        hold_pct = None
        if points:
            first_price = dict((t.isoformat(), p) for t, p in closes)[points[0]["time"]]
            hold_pct = round((closes[-1][1] / first_price - 1) * 100, 4)
        out.append({"name": pot["name"], "label": pot["label"], "points": points,
                    "hold_pct": hold_pct})
    return {"start_time": closes[0][0].isoformat(), "pots": out, "hold": hold}
