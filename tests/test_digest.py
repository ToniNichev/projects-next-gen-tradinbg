"""The daily digest: exact facts from the log/API; the model only writes prose."""

from datetime import datetime

import digest

LOG = """\
2026-11-03 09:00:01,207 INFO root Pot trend: signal=neutral conf=0.00
2026-11-03 10:00:01,207 INFO root Pot trend: signal=neutral conf=0.00
2026-11-03 10:20:00,000 WARNING root WebSocket closed: None None
2026-11-03 10:20:05,000 WARNING root ================================================================================
2026-11-03 10:20:05,000 WARNING root ⚠️  LIVE TRADING MODE ENABLED - REAL MONEY AT RISK! ⚠️
2026-11-03 10:40:00,000 WARNING root WebSocket closed: None None
2026-11-03 10:41:00,000 ERROR live_trader fetch_order(stop 123) failed after 3 attempts
2026-11-03 10:42:00,000 ERROR live_trader fetch_order(stop 456) failed after 3 attempts
2026-11-02 01:00:00,000 ERROR root too old to count
"""


def test_log_is_counted_exactly(tmp_path):
    path = tmp_path / "app.log"
    path.write_text(LOG)
    out = digest.read_log(datetime(2026, 11, 3, 0, 0), str(path))
    assert out["checks"] == 2 and out["restarts"] == 1
    assert out["reconnects"] == 1                 # the drop at 10:20 was the restart
    (key, n), = out["problems"].items()           # banners aren't problems; IDs grouped
    assert key[0] == "ERROR" and n == 2


def test_made_up_numbers_are_flagged():
    sheet = "value $75.04, price $77,785.99, trades: 2"
    assert digest.numbers_not_in("$75.04 at $77,785.99, 2 trades", sheet) == []
    assert digest.numbers_not_in("3 trades", sheet) == ["3"]


def test_attention_flag():
    ok = {"health": {"trading_enabled": True}, "pots": {"pots": []},
          "log": {"problems": {}}, "disk": {"free_gb": 50}}
    assert not digest.needs_attention(ok)
    assert digest.needs_attention({**ok, "health": {"trading_enabled": True, "checks_late": True}})
    assert digest.needs_attention({**ok, "disk": {"free_gb": 5}})


def test_dashboard_summary_endpoint(monkeypatch):
    import threading
    import auth as _auth_module  # noqa: F401
    from app import create_app
    from app.api import routes
    from auth import get_auth_config
    get_auth_config().enabled = False
    seen = {}

    def fake_run(hours, ai, label="now", timeout=240):
        seen.update(hours=hours, ai=ai)
        return {"title": "t", "summary": "s", "sheet": "f", "attention": False, "text": "s\n\nf",
                "made_at": "2026-11-03T00:00:00+00:00"}
    monkeypatch.setattr(routes, "run_digest", fake_run)
    app = create_app()
    app.config.update(TESTING=True)
    c = app.test_client()
    r = c.post("/api/digest", json={"hours": 6, "ai": False})
    assert r.status_code == 200 and r.get_json()["data"]["sheet"] == "f"
    assert seen == {"hours": 6.0, "ai": False}
    # One at a time
    routes._digest_running.acquire()
    try:
        assert c.post("/api/digest", json={}).status_code == 409
    finally:
        routes._digest_running.release()
