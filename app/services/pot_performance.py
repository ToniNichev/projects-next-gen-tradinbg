"""
Each money pot's result over time, next to just holding BTC.

One point per closed hourly candle. A pot's value is rebuilt from its trade
records (cash and BTC after each trade) and its cash moves; moves count as
money put in or taken out, so they change what the pot was given, not its
result. Each pot's line starts when the pot began; "holding BTC" starts with
the earliest pot.
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
    closes = [(_ts(c["timestamp"]) + step, float(c["close"])) for c in candles]
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
        for t, price in closes:
            while k < len(events) and events[k][0] <= t + GRACE:
                _, kind, e = events[k]
                if kind == 0:
                    cash, btc = float(e["usdt_balance"]), float(e["base_balance"])
                else:
                    cash += float(e["amount"])
                    invested += float(e["amount"])
                k += 1
            if t + GRACE < pot_start:
                continue
            value = cash + btc * price
            points.append({
                "time": t.isoformat(),
                "pct": round((value / invested - 1) * 100, 4) if invested > 0 else 0.0,
                "value": round(value, 4),
                "invested": round(invested, 4),
                "holding": btc * price >= 1.0,  # dust doesn't count as holding
            })
        out.append({"name": pot["name"], "label": pot["label"], "points": points})
    return {"start_time": closes[0][0].isoformat(), "pots": out, "hold": hold}
