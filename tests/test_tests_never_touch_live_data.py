"""Guard: tests must never open the live database in data/."""

import os

from database import DatabaseManager, initialize_database


def test_default_database_goes_to_a_temp_file(tmp_path):
    db = initialize_database()  # the default would be data/trading.db
    assert str(tmp_path) in db.database_url
    assert "data/trading.db" not in db.database_url


def test_explicit_live_path_is_redirected(tmp_path):
    live = os.path.join(os.path.dirname(__file__), "..", "data", "trading.db")
    db = DatabaseManager(f"sqlite:///{live}")
    assert str(tmp_path) in db.database_url


def test_memory_database_is_left_alone():
    assert DatabaseManager("sqlite:///:memory:").database_url == "sqlite:///:memory:"
