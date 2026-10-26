"""Shared test setup.

Tests exercise code paths that send alerts (emergency stop, reconnects, ...).
Without this, running the suite sends real Telegram/webhook messages using
the settings in .env. Every test gets a notifier that records instead of
sending.
"""

import pytest

import notify


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch):
    sent = []
    monkeypatch.setattr(notify, "_send_all_sync", lambda title, body, severity: sent.append((title, body, severity)))
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
