"""Alerts are tried again when delivery fails (two were lost to DNS blips in Oct 2026)."""

import notify

# conftest swaps _send_all_sync out for every test so nothing is really sent;
# keep the real one (taken at import, before that swap) to test the retries.
REAL_SEND = notify._send_all_sync


def test_failed_backend_is_retried_until_it_works(monkeypatch):
    calls = []

    def flaky():
        calls.append(1)
        return len(calls) >= 3  # works on the third try
    monkeypatch.setattr(notify, "_backends", lambda t, b, s: [("telegram", flaky)])
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    REAL_SEND("title", "body", "critical", delays=(1, 1, 1))
    assert len(calls) == 3


def test_working_backends_are_not_sent_twice(monkeypatch):
    sent = {"ok": 0, "bad": 0}

    def ok():
        sent["ok"] += 1
        return True

    def bad():
        sent["bad"] += 1
        return False
    monkeypatch.setattr(notify, "_backends", lambda t, b, s: [("ok", ok), ("bad", bad)])
    monkeypatch.setattr(notify.time, "sleep", lambda s: None)
    REAL_SEND("x", "y", "warning", delays=(1, 1))
    assert sent == {"ok": 1, "bad": 3}
