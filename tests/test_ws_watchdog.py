"""Tests for the kline stream health check used by the websocket watchdog."""

from datetime import datetime, timezone

from main import stream_problem

H = 3600 * 1000
T0 = int(datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)  # an hour boundary


def check(connected=True, last_closed_open=T0 - H, now=T0 + 30 * 60 * 1000):
    return stream_problem(connected, last_closed_open, now, H, grace_s=180, label="BTC/USD / 1h")


def test_healthy_mid_hour():
    assert check() is None


def test_quiet_market_is_not_a_problem():
    # 50 minutes into the hour with the last close received: fine, however
    # long it's been since the last partial kline
    assert check(now=T0 + 50 * 60 * 1000) is None


def test_connection_down_is_a_problem():
    assert check(connected=False) == "connection closed or errored"


def test_missing_close_within_grace_is_fine():
    # The 14:00 candle closed at 15:00; 2 minutes later it may still be on the way
    assert check(last_closed_open=T0 - H, now=T0 + H + 120 * 1000) is None


def test_missing_close_after_grace_is_a_problem():
    problem = check(last_closed_open=T0 - H, now=T0 + H + 200 * 1000)
    assert "15:00 UTC hasn't arrived" in problem


def test_close_received_is_fine():
    assert check(last_closed_open=T0, now=T0 + H + 200 * 1000) is None
