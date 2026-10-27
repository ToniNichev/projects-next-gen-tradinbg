"""Saving settings must never store an empty trading symbol or timeframe."""

import os

os.environ.setdefault("DASHBOARD_AUTH_ENABLED", "false")

import auth as _auth_module  # noqa: F401  (force import order)

import pytest

from app import create_app
from app.api import strategies as strategies_api
from database import initialize_database


@pytest.fixture
def client_and_db(monkeypatch):
    from auth import get_auth_config
    get_auth_config().enabled = False
    db = initialize_database("sqlite:///:memory:")
    monkeypatch.setattr(strategies_api, "get_database", lambda: db)
    monkeypatch.setattr(strategies_api, "DATABASE_AVAILABLE", True)
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client(), db


@pytest.mark.parametrize("key", ["symbol", "timeframe"])
def test_empty_symbol_or_timeframe_is_rejected(client_and_db, key):
    client, db = client_and_db
    resp = client.post("/api/strategy-config/update", json={key: "", "stop_loss_pct": 0.03})
    assert resp.status_code == 400
    assert db.get_strategy_config("stop_loss_pct") is None  # nothing saved


def test_valid_symbol_is_saved(client_and_db):
    client, db = client_and_db
    resp = client.post("/api/strategy-config/update", json={"symbol": "BTC/USD"})
    assert resp.status_code == 200
    assert db.get_strategy_config("symbol").value == "BTC/USD"
