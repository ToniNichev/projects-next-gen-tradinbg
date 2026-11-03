"""Shared test setup.

Tests exercise code paths that send alerts (emergency stop, reconnects, ...).
Without this, running the suite sends real Telegram/webhook messages using
the settings in .env. Every test gets a notifier that records instead of
sending.
"""

import os

import pytest

import database
import notify
import paper_trader

_REAL_DATA_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "data"))
_real_db_init = database.DatabaseManager.__init__
_real_paper_init = paper_trader.PaperTrader.__init__


@pytest.fixture(autouse=True)
def never_touch_live_data(monkeypatch, tmp_path):
    """Keep tests away from data/ (the live bot's database, vector store and
    logs). On 2026-11-02 a test opened the default data/trading.db and
    re-wrote rows in the live database. Any file-based SQLite URL now goes to
    a fresh file in the test's temp folder; in-memory databases are untouched."""
    def safe_init(self, database_url="sqlite:///data/trading.db"):
        if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
            path = os.path.realpath(database_url[len("sqlite:///"):])
            if not path.startswith(os.path.realpath(str(tmp_path))):
                database_url = f"sqlite:///{tmp_path / 'test.db'}"
        _real_db_init(self, database_url)
    monkeypatch.setattr(database.DatabaseManager, "__init__", safe_init)

    # CSV trade logs (e.g. data/backtest_log.csv) go to the temp folder too
    def safe_paper_init(self, *args, **kwargs):
        _real_paper_init(self, *args, **kwargs)
        if self.log_path:
            self.log_path = str(tmp_path / os.path.basename(self.log_path))
    monkeypatch.setattr(paper_trader.PaperTrader, "__init__", safe_paper_init)
    monkeypatch.setenv("BOT_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("BOT_LLM_RAG_PERSIST_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("BOT_TRADES_LOG_PATH", str(tmp_path / "trade_log.csv"))


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "_send_all_sync", lambda title, body, severity, **_: sent.append((title, body, severity)))
    for key in (
        "BOT_NOTIFY_WEBHOOK_URL",
        "BOT_NOTIFY_NTFY_TOPIC",
        "BOT_NOTIFY_TELEGRAM_BOT_TOKEN",
        "BOT_NOTIFY_TELEGRAM_CHAT_ID",
        "BOT_NOTIFY_PUSHOVER_USER_KEY",
        "BOT_NOTIFY_PUSHOVER_APP_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    return sent
