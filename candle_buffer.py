"""The bot's in-memory list of closed candles ([open_ms, o, h, l, c, v]).

Kept to closed candles only, one per open time. On 2026-11-02 the audit
found the exchange's still-forming candle loaded at start-up and the closed
version appended next to it later, so that hour counted twice in the
indicators for about 20 hours after every restart.
"""

from typing import List, Optional


def closed_only(candles, timeframe_ms: int, now_ms: int) -> List[list]:
    """Drop candles that haven't finished yet."""
    return [c for c in (candles or []) if int(c[0]) + int(timeframe_ms) <= int(now_ms)]


def add_closed(buffer: list, candle: list, max_size: Optional[int] = None) -> bool:
    """Put a closed candle in the buffer (in place). A candle with the same
    open time is replaced, not added again. Returns False when it replaced
    one (the candle was already there)."""
    ts = int(candle[0])
    for i in range(len(buffer) - 1, -1, -1):
        t = int(buffer[i][0])
        if t == ts:
            buffer[i] = candle
            return False
        if t < ts:
            buffer.insert(i + 1, candle)
            break
    else:
        buffer.insert(0, candle)
    if max_size:
        del buffer[:max(0, len(buffer) - max_size)]
    return True
