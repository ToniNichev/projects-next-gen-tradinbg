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
