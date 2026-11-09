"""A pot whose hourly check keeps failing must be noticed (2026-11-05 review).

Before: the error went only to the log and the pot's dashboard note, while
/api/health and the watchdog still reported a healthy hourly check. A holding
Trend Hold pot (no stop on the exchange) could miss its sell for hours.
"""

import pytest

from pots import POT_INTRADAY, POT_TREND
from tests.test_pots import candle, live_pots


def failing_pots(monkeypatch, name=POT_TREND):
    pots, trend, intraday, sm, exchange = live_pots()
    sent = []
    pots.notify = lambda title, body, severity="info": sent.append((title, body, severity))
    strat = {POT_TREND: trend, POT_INTRADAY: intraday}[name]

    def boom(*a, **k):
        raise RuntimeError("Not enough daily candles")
    monkeypatch.setattr(strat, "compute_signal", boom)
    return pots, trend, intraday, sm, sent


def test_alert_after_two_failures_in_a_row_then_all_clear(monkeypatch):
    pots, trend, intraday, sm, sent = failing_pots(monkeypatch)
    candle(pots, sm)
    assert sent == [] and pots.failing() == []          # one failure can be a blip
    candle(pots, sm)
    assert pots.failing() == [POT_TREND]
    (title, body, sev), = sent
    assert "Trend Hold" in title and sev == "critical" and "Not enough daily candles" in body
    candle(pots, sm)
    assert len(sent) == 1                                # not every hour

    monkeypatch.undo()
    candle(pots, sm)
    assert pots.failing() == [] and "working again" in sent[-1][0]
    assert pots.get(POT_TREND).failed_checks == 0


def test_the_alert_says_whether_the_pot_is_protected(monkeypatch):
    pots, trend, intraday, sm, exchange = live_pots()
    trend.direction = "bullish"
    candle(pots, sm)
    assert pots.get(POT_TREND).holding
    sent = []
    pots.notify = lambda title, body, severity="info": sent.append(body)
    monkeypatch.setattr(trend, "compute_signal", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    candle(pots, sm)
    candle(pots, sm)
    assert "no stop order on the exchange" in sent[0]


def test_other_pots_keep_trading(monkeypatch):
    pots, trend, intraday, sm, sent = failing_pots(monkeypatch)
    intraday.direction = "bullish"
    candle(pots, sm)
    assert pots.get(POT_INTRADAY).holding


def test_health_and_watchdog_report_it(monkeypatch):
    import watchdog
    pots, *_ = failing_pots(monkeypatch)
    from app.api.routes import _pots_failing
    pots.get(POT_TREND).failed_checks = 2
    assert _pots_failing(pots) == [POT_TREND]
    assert _pots_failing(None) == []

    class Resp:
        def __init__(self, data): self.data = data
        def read(self): return self.data
        def __enter__(self): return self
        def __exit__(self, *a): return False
    import json
    body = json.dumps({"data": {"minutes_since_check": 5, "pots_failing": ["trend"]}}).encode()
    monkeypatch.setattr(watchdog.urllib.request, "urlopen", lambda *a, **k: Resp(body))
    ok, why = watchdog.check(3010)
    assert not ok and "trend" in why


def test_live_trader_refuses_a_buy_on_top_of_a_position():
    pots, trend, intraday, sm, exchange = live_pots()
    intraday.direction = "bullish"
    candle(pots, sm)
    t = pots.get(POT_INTRADAY).trader
    orders = exchange.create_market_buy_order.call_count
    assert t.execute_market_buy(amount=0.00002) is None
    assert "already holds" in t.last_refusal
    assert exchange.create_market_buy_order.call_count == orders
