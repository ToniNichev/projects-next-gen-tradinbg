"""The outside watchdog alerts when the bot stops its hourly checks."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import watchdog


def serve(payload):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"success": True, "data": payload}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_recent_check_is_ok():
    srv = serve({"minutes_since_check": 12.0})
    try:
        assert watchdog.check(srv.server_port) == (True, "")
    finally:
        srv.shutdown()


def test_late_check_is_a_problem():
    srv = serve({"minutes_since_check": 130.0, "last_check_at": "2026-11-03T10:00:01+00:00"})
    try:
        ok, why = watchdog.check(srv.server_port)
        assert not ok and "130 minutes" in why
    finally:
        srv.shutdown()


def test_no_answer_is_a_problem():
    ok, why = watchdog.check(1, timeout=1)  # nothing listens on port 1
    assert not ok and "isn't answering" in why


def test_alerts_once_then_says_when_it_is_back(tmp_path, monkeypatch, no_real_notifications):
    monkeypatch.setattr(watchdog, "STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setattr(watchdog, "_load_env", lambda: None)
    monkeypatch.setattr(watchdog, "chores", lambda *a, **k: None)  # no real backup
    monkeypatch.setenv("BOT_DASHBOARD_PORT", "1")  # bot down
    watchdog.main()
    watchdog.main()                                 # still down: no second alert yet
    titles = [n[0] for n in no_real_notifications]
    assert titles.count("🚨 Trading bot needs attention") == 1
    srv = serve({"minutes_since_check": 3.0})
    try:
        monkeypatch.setenv("BOT_DASHBOARD_PORT", str(srv.server_port))
        watchdog.main()
    finally:
        srv.shutdown()
    assert "✅ Trading bot is back" in [n[0] for n in no_real_notifications]



# ------------------------------------------------- daily backup, disk space

def test_backup_failure_and_low_disk_alert_once_a_day():
    sent, state = [], {}
    send = lambda title, body, sev: sent.append(title)
    fail = lambda: (None, "database not found")
    low = lambda: (False, 2.5)
    watchdog.chores(state, 1000, send, backup=fail, disk=low)
    watchdog.chores(state, 1600, send, backup=fail, disk=low)   # 10 minutes later: quiet
    assert sent == ["⚠️ Trading bot backup failed", "⚠️ Disk almost full"]
    watchdog.chores(state, 1000 + 25 * 3600, send, backup=fail, disk=low)   # a day later
    assert len(sent) == 4
    watchdog.chores(state, 1000 + 26 * 3600, send, backup=lambda: ("x", None), disk=lambda: (True, 40.0))
    assert sent[-1] == "✅ Disk space OK again" and "disk_alerted_at" not in state
