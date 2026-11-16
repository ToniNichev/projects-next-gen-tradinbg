"""The startup seed must not save the candle that is still forming."""

from seed_history import seed_candle_history

HOUR = 3600 * 1000


class FakeExchange:
    def __init__(self, now_ms):
        self.now = now_ms

    def milliseconds(self):
        return self.now

    def parse_timeframe(self, tf):
        return 3600

    def fetch_ohlcv(self, symbol, tf, since=None, limit=1000):
        first = (since // HOUR + 1) * HOUR
        out, t = [], first
        while t <= self.now and len(out) < limit:
            out.append([t, 1.0, 2.0, 0.5, 1.5, 3.0])
            t += HOUR
        return out


class FakeDB:
    def __init__(self):
        self.saved = []

    def add_candle(self, row):
        self.saved.append(row)


def test_forming_candle_is_not_saved():
    now = 1_794_838_500_000  # 14:15 UTC on 2026-11-16, 15 minutes into the 14:00 candle
    db = FakeDB()
    seed_candle_history(FakeExchange(now), db, "BTC/USD", "1h", days_back=1)
    assert db.saved
    last = max(r["timestamp"] for r in db.saved)
    assert last.strftime("%H:%M") == "13:00"  # 13:00 closed at 14:00; 14:00 is still forming
