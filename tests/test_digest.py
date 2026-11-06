"""The daily digest: exact facts from the log/API; the model only writes prose."""

from datetime import datetime

import digest
import pytest

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


def test_gains_table_is_exact():
    import digest
    facts = {"pots": {"pots": [
        {"name": "trend", "label": "Trend Hold", "value": 73.33, "pnl": -1.67, "holding": False},
        {"name": "manual", "label": "Manual", "value": 6.2, "pnl": 0.2, "holding": True}]},
        "trades": [{"pot": "trend", "side": "buy", "pnl": None},
                   {"pot": "trend", "side": "sell", "pnl": -1.64}]}
    rows = digest.gains_table(facts)
    trend, manual, total = rows
    assert trend["put_in"] == pytest.approx(75.0) and trend["pnl_pct"] == pytest.approx(-1.67 / 75 * 100)
    assert trend["period_pnl"] == pytest.approx(-1.64) and trend["trades"] == 2 and trend["status"] == "in cash"
    assert manual["period_pnl"] == 0.0 and manual["trades"] == 0
    assert total["total"] and total["put_in"] == pytest.approx(81.0) and total["pnl"] == pytest.approx(-1.47)
    assert digest.gains_table({"pots": {"error": "down"}, "trades": []}) == []
