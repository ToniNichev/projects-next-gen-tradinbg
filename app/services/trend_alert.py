"""
Trend Hold heads-up alerts.

Once per daily close, tell the user when the bot is close to acting:
- holding BTC and the day closed within `near_pct` % above the sell line
- in cash and the day closed within `near_pct` % below the buy line
and when a close crossed a line (the bot trades on that same check).

The last alerted day is saved to a small JSON file so a restart doesn't
send the same alert twice.
"""

import json
import logging
import os
from datetime import timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = os.path.join("data", "trend_alert_state.json")


def _usd(v: float) -> str:
    return f"${v:,.0f}"


def closed_day(signal) -> Optional[str]:
    """The UTC date of the daily close the signal is based on."""
    ts = getattr(signal, "timestamp", None)
    if ts is None:
        return None
    # The strategy uses the last UTC day that had closed by `timestamp`
    return (ts.date() - timedelta(days=1)).isoformat()


def build_alert(signal, holding: bool, near_pct: float) -> Optional[Tuple[str, str]]:
    """(title, body) if this daily close deserves an alert, else None."""
    ind = getattr(signal, "indicators", None) or {}
    close, sell, buy = ind.get("daily_close"), ind.get("sell_below"), ind.get("buy_above")
    if not close or not sell or not buy:
        return None

    if holding:
        if close < sell:
            return ("Trend Hold: day closed below the sell line",
                    f"Daily close {_usd(close)} is under the sell line {_usd(sell)}. "
                    f"The bot sells its BTC on this check.")
        gap = (close / sell - 1) * 100
        if gap <= near_pct:
            return ("Trend Hold: close to selling",
                    f"Daily close {_usd(close)} is {gap:.1f}% above the sell line {_usd(sell)}. "
                    f"It sells if a day closes below {_usd(sell)}.")
    else:
        if close > buy:
            return ("Trend Hold: day closed above the buy line",
                    f"Daily close {_usd(close)} is over the buy line {_usd(buy)}. "
                    f"The bot buys BTC on this check.")
        gap = (1 - close / buy) * 100
        if gap <= near_pct:
            return ("Trend Hold: close to buying",
                    f"Daily close {_usd(close)} is {gap:.1f}% below the buy line {_usd(buy)}. "
                    f"It buys if a day closes above {_usd(buy)}.")
    return None


def _load(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(path: str, state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Could not save trend alert state: %s", exc)


def check(signal, holding: bool, near_pct: float,
          state_path: str = DEFAULT_STATE_PATH) -> Optional[Tuple[str, str]]:
    """Return an alert at most once per daily close; None otherwise."""
    if signal is None or near_pct <= 0:
        return None
    day = closed_day(signal)
    if day is None:
        return None
    state = _load(state_path)
    if state.get("last_day") == day:
        return None
    alert = build_alert(signal, holding, near_pct)
    if alert:
        _save(state_path, {"last_day": day, "title": alert[0]})
    return alert
