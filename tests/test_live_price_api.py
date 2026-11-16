"""The chart's "now" marker reads the live stream price (display only)."""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DASHBOARD_AUTH_ENABLED", "false")

import auth as _auth_module  # noqa: F401  (import order)

import pytest

from app import create_app
from app.api import market
from app.core.state import get_app_state


class Ticker:
    def __init__(self):
        self.calls = 0

    def fetch_ticker(self, symbol):
        self.calls += 1
        return {"last": 65000.5}


@pytest.fixture
def client(monkeypatch):
    from auth import get_auth_config
    get_auth_config().enabled = False
    app = create_app()
    app.config.update(TESTING=True)
    state = get_app_state()
    ex = Ticker()
    monkeypatch.setattr(state, "get_exchange", lambda: ex)
    market._ticker_cache.update(price=None, at=None)
    yield app.test_client(), state, ex
    if hasattr(state, "_live_price"):
        del state._live_price


def test_uses_the_stream_price(client):
    c, state, ex = client
    state.set_live_price(65432.1)
    j = c.get("/api/price/live").get_json()
    assert j["price"] == 65432.1 and j["source"] == "stream"
    assert ex.calls == 0


def test_falls_back_to_the_ticker_when_the_stream_is_quiet(client):
    c, state, ex = client
    state._live_price = (60000.0, datetime.now(timezone.utc) - timedelta(minutes=5))
    j = c.get("/api/price/live").get_json()
    assert j["price"] == 65000.5 and j["source"] == "ticker"
    c.get("/api/price/live")
    assert ex.calls == 1  # cached for a few seconds


def test_ignores_a_zero_price(client):
    _, state, _ = client
    state.set_live_price(0)
    assert state.get_live_price() == (None, None)
