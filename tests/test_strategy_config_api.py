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


# 2026-11-09: a cleared number box on /strategies/all was sent as null and
# stored as "None"; that one row then made every saved setting fall back to
# the .env defaults.

@pytest.mark.parametrize("bad", [None, "", "abc", float("nan"), float("inf"), True])
def test_blank_or_bad_number_is_refused_and_nothing_saved(client_and_db, bad):
    client, db = client_and_db
    resp = client.post("/api/strategy-config/update",
                       json={"llm_cache_minutes": bad, "stop_loss_pct": 0.03})
    assert resp.status_code == 400
    assert "llm_cache_minutes" in resp.get_json()["error"]
    assert db.get_strategy_config("stop_loss_pct") is None
    assert db.get_strategy_config("llm_cache_minutes") is None


def test_whole_number_setting_refuses_a_fraction(client_and_db):
    client, _ = client_and_db
    resp = client.post("/api/strategy-config/update", json={"llm_cache_minutes": 2.5})
    assert resp.status_code == 400


def test_numbers_are_stored_as_their_type(client_and_db):
    client, db = client_and_db
    resp = client.post("/api/strategy-config/update",
                       json={"llm_cache_minutes": "15", "stop_loss_pct": 0.03,
                             "use_trailing_stop": "false"})
    assert resp.status_code == 200, resp.get_json()
    saved = db.get_all_strategy_configs()
    assert saved["llm_cache_minutes"] == 15
    assert saved["stop_loss_pct"] == 0.03
    assert saved["use_trailing_stop"] is False


def test_one_unreadable_row_does_not_drop_the_others(client_and_db):
    _, db = client_and_db
    db.set_strategy_config("stop_loss_pct", 0.03, "float")
    db.set_strategy_config("llm_cache_minutes", "None", "int")  # what the old bug stored
    saved = db.get_all_strategy_configs()
    assert saved["stop_loss_pct"] == 0.03
    assert "llm_cache_minutes" not in saved
