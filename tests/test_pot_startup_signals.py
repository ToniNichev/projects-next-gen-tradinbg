"""After a restart, every pot's signal is known right away.

On 2026-11-02 the RSI + Bollinger Bands card said "No signal yet" for up to
an hour after each restart: at startup only strategies switched on in
Strategies were computed (just Trend Hold), not the strategies pots run.
"""

import time

from database import initialize_database
from pots import POT_INTRADAY, POT_MANUAL, POT_TREND, _timeframe_ms
from tests.test_pots import live_pots


def test_timeframe_ms():
    assert _timeframe_ms("1h") == 3_600_000
    assert _timeframe_ms("15m") == 900_000
    assert _timeframe_ms("1d") == 86_400_000
    assert _timeframe_ms("weird") is None


def test_startup_computes_every_pots_signal_without_trading():
    db = initialize_database("sqlite:///:memory:")
    pots, trend, intraday, sm, exchange = live_pots(db)
    trend.direction = "bullish"
    intraday.direction = "bullish"   # would buy on a real check
    seen = []
    real = intraday.compute_signal
    intraday.compute_signal = lambda ex, sym, tf, candles=None: seen.append(candles) or real(ex, sym, tf, candles)

    hour = 3_600_000
    now = int(time.time() * 1000) // hour * hour
    candles = [[now - 2 * hour, 1, 1, 1, 1, 1], [now - hour, 1, 1, 1, 1, 1], [now, 1, 1, 1, 1, 1]]  # last one still forming
    pots.prime_signals(sm, exchange, "BTC/USD", "1h", candles)

    assert pots.get(POT_TREND).last_signal.direction == "bullish"
    assert pots.get(POT_INTRADAY).last_signal.direction == "bullish"
    assert pots.get(POT_MANUAL).last_signal is None          # traded by you: no strategy
    assert set(sm.last_signals) >= {trend.name, intraday.name}  # the Strategy Signals cards
    assert len(seen[0]) == 2                                  # closed candles only
    assert not pots.get(POT_INTRADAY).holding and not pots.get(POT_TREND).holding  # nothing bought
    assert not db.get_trades()
