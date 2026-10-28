"""
How the paper test is going: the bot's account vs. simply holding BTC.

Both series are percentages from the moment of the first paper trade, one
point per closed candle. The bot's value is rebuilt from the trade records
(cash and BTC after each trade) and candle closes; "holding" buys BTC at the
close of the candle the test began on and keeps it.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

# Trades are stamped a moment after the candle that triggered them closes
TRADE_GRACE = timedelta(minutes=5)


def _ts(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _before_first_trade(t: Dict) -> Dict:
    """Cash and BTC just before a trade, from the balances recorded after it."""
    fee = t.get("fee") or 0.0
    notional = t.get("notional") or 0.0
    amount = t.get("amount") or 0.0
    if t["side"] == "buy":
        return {"cash": t["usdt_balance"] + notional + fee, "btc": t["base_balance"] - amount}
    return {"cash": t["usdt_balance"] - (notional - fee), "btc": t["base_balance"] + amount}


def compute_paper_performance(trades: List[Dict], candles: List[Dict], candle_hours: float = 1.0) -> Dict:
    """
    trades:  dicts with timestamp, side, price, amount, notional, fee,
             usdt_balance, base_balance (any order)
    candles: dicts with timestamp (candle open, UTC) and close, oldest first
    """
    if not trades:
        return {"started": False}

    trades = sorted(trades, key=lambda t: _ts(t["timestamp"]))
    step = timedelta(hours=candle_hours)
    start_time = _ts(trades[0]["timestamp"])
    start = _before_first_trade(trades[0])

    # The candle whose close the test began on, then every candle after it
    closes = [(_ts(c["timestamp"]) + step, float(c["close"])) for c in candles]
    first = next((i for i, (t, _) in enumerate(closes) if t + TRADE_GRACE >= start_time), None)
    if first is None:
        return {"started": True, "start_time": start_time.isoformat(), "points": []}
    closes = closes[first:]

    start_price = closes[0][1]
    start_value = start["cash"] + start["btc"] * start_price

    points = []
    cash, btc, k = start["cash"], start["btc"], 0
    for close_time, price in closes:
        while k < len(trades) and _ts(trades[k]["timestamp"]) <= close_time + TRADE_GRACE:
            cash, btc = trades[k]["usdt_balance"], trades[k]["base_balance"]
            k += 1
        value = cash + btc * price
        points.append({
            "time": close_time.isoformat(),
            "price": price,
            "value": round(value, 4),
            "bot_pct": round((value / start_value - 1) * 100, 4),
            "hold_pct": round((price / start_price - 1) * 100, 4),
            "holding_btc": btc > 1e-12,
        })

    last = points[-1]
    return {
        "started": True,
        "start_time": start_time.isoformat(),
        "start_value": round(start_value, 4),
        "start_price": start_price,
        "points": points,
        "latest": {
            "time": last["time"],
            "value": last["value"],
            "bot_pct": last["bot_pct"],
            "hold_pct": last["hold_pct"],
        },
        "trade_count": len(trades),
    }
