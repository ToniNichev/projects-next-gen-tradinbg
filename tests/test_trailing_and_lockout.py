"""Tests for trailing-stop persistence in PaperTrader and the login lockout."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from flask import Flask

import auth
from paper_trader import PaperTrader, Position


def _trader_with_position(db):
    trader = PaperTrader(
        log_path="", db_manager=db, enable_database=True,
        enable_csv_logging=False, trailing_stop_pct=0.025,
    )
    trader.open_position = Position(
        side="long", entry_price=100.0, amount=1.0, entry_time="2026-10-20T15:00:00",
        stop_loss=90.0, take_profit=200.0, trailing_stop=97.5,
        initial_trailing_stop_pct=0.025, highest_price=100.0,
    )
    trader.db_position_id = 1
    return trader


def test_trailing_stop_is_saved_when_it_moves_up():
    db = MagicMock()
    db.get_trades.return_value = []
    db.get_open_positions.return_value = []
    trader = _trader_with_position(db)

    assert trader.update_position(110.0) is None

    db.update_position.assert_called_with(1, {
        "trailing_stop": 110.0 * 0.975,
        "highest_price": 110.0,
    })


def test_restore_uses_saved_highest_price():
    db = MagicMock()
    db.get_trades.return_value = []
    db.get_open_positions.return_value = [SimpleNamespace(
        id=1, side="long", entry_price=100.0, amount=1.0,
        entry_time=SimpleNamespace(isoformat=lambda: "2026-10-20T15:00:00"),
        stop_loss=90.0, take_profit=200.0, trailing_stop=107.25,
        highest_price=110.0, strategy_name="Aggregated",
    )]
    trader = PaperTrader(log_path="", db_manager=db, enable_csv_logging=False)

    assert trader.open_position.highest_price == 110.0
    assert trader.open_position.trailing_stop == 107.25


def test_lockout_after_repeated_failures(monkeypatch):
    cfg = auth.get_auth_config()
    monkeypatch.setattr(cfg, "enabled", True)
    monkeypatch.setattr(cfg, "username", "admin")
    monkeypatch.setattr(cfg, "password", "right")
    auth._failed_logins.clear()

    app = Flask(__name__)
    with app.test_request_context(environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        for _ in range(auth.LOCKOUT_MAX_FAILURES):
            assert auth.verify_password("admin", "wrong") is False
        # Locked out now, even with the right password
        assert auth.verify_password("admin", "right") is False

    # A different IP is unaffected
    with app.test_request_context(environ_base={"REMOTE_ADDR": "198.51.100.7"}):
        assert auth.verify_password("admin", "right") is True

    auth._failed_logins.clear()


def test_empty_credentials_are_not_counted(monkeypatch):
    cfg = auth.get_auth_config()
    monkeypatch.setattr(cfg, "enabled", True)
    auth._failed_logins.clear()

    app = Flask(__name__)
    with app.test_request_context(environ_base={"REMOTE_ADDR": "203.0.113.10"}):
        for _ in range(10):
            assert auth.verify_password("", "") is False
    assert auth._failed_logins == {}
