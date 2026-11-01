"""get_candles: latest N without `since`, first N from `since` with it.

The chart loads older history by asking for candles from a start time; it
used to get the newest candles back, saw nothing new and stopped loading.
"""
from datetime import datetime, timedelta

from database import initialize_database


def _db(tmp_path):
    db = initialize_database(f"sqlite:///{tmp_path / 'c.db'}")
    start = datetime(2026, 10, 1)
    for i in range(48):
        db.add_candle({
            "symbol": "BTC/USD", "timeframe": "1h", "timestamp": start + timedelta(hours=i),
            "open": i, "high": i, "low": i, "close": i, "volume": 1.0,
        })
    return db, start


def test_without_since_returns_latest(tmp_path):
    db, _ = _db(tmp_path)
    rows = db.get_candles("BTC/USD", "1h", limit=5)
    assert [r["close"] for r in rows] == [43, 44, 45, 46, 47]


def test_with_since_returns_first_from_since(tmp_path):
    db, start = _db(tmp_path)
    rows = db.get_candles("BTC/USD", "1h", limit=5, since=start + timedelta(hours=10))
    assert [r["close"] for r in rows] == [10, 11, 12, 13, 14]
