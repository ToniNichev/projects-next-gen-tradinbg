from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import trend_alert


def _sig(close, sell=75_000.0, buy=76_500.0, ts=datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)):
    return SimpleNamespace(
        timestamp=ts,
        indicators={"daily_close": close, "sell_below": sell, "buy_above": buy},
    )


def test_closed_day_is_previous_utc_day():
    assert trend_alert.closed_day(_sig(1)) == "2026-11-01"
    midnight = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
    assert trend_alert.closed_day(_sig(1, ts=midnight)) == "2026-11-01"


def test_holding_near_sell_line_alerts():
    title, body = trend_alert.build_alert(_sig(75_600), holding=True, near_pct=1.0)
    assert title == "Trend Hold: close to selling"
    assert "0.8% above the sell line $75,000" in body


def test_holding_far_from_sell_line_is_quiet():
    assert trend_alert.build_alert(_sig(77_445), holding=True, near_pct=1.0) is None


def test_holding_close_below_sell_line_says_it_sells():
    title, _ = trend_alert.build_alert(_sig(74_900), holding=True, near_pct=1.0)
    assert title == "Trend Hold: day closed below the sell line"


def test_cash_near_buy_line_and_crossing():
    title, _ = trend_alert.build_alert(_sig(76_000), holding=False, near_pct=1.0)
    assert title == "Trend Hold: close to buying"
    title, _ = trend_alert.build_alert(_sig(76_600), holding=False, near_pct=1.0)
    assert title == "Trend Hold: day closed above the buy line"
    assert trend_alert.build_alert(_sig(74_000), holding=False, near_pct=1.0) is None


def test_once_per_daily_close_and_survives_restart(tmp_path):
    path = str(tmp_path / "state.json")
    sig = _sig(75_600)
    assert trend_alert.check(sig, True, 1.0, path) is not None
    # Same day again (next hourly check, or after a restart): quiet
    assert trend_alert.check(sig, True, 1.0, path) is None
    # Next day's close: alerts again
    nxt = _sig(75_500, ts=datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc))
    assert trend_alert.check(nxt, True, 1.0, path) is not None


def test_off_or_missing_data_is_quiet(tmp_path):
    path = str(tmp_path / "state.json")
    assert trend_alert.check(_sig(75_600), True, 0, path) is None
    assert trend_alert.check(None, True, 1.0, path) is None
    assert trend_alert.check(SimpleNamespace(timestamp=None, indicators={}), True, 1.0, path) is None
