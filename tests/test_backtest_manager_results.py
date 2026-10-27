"""What the Backtest page gets back from a run: risk numbers, the date
window, the strategies actually used, and a record when a run fails."""

from datetime import datetime, timezone

import backtest
from app.core.state import ApplicationState
from app.services.backtest_manager import BacktestManager
from config import BotConfig


def _manager():
    config = BotConfig(binance_api_key="", binance_api_secret="")
    config.use_multi_strategy = True
    config.strategy_ema_enabled = False
    config.strategy_rsi_bb_enabled = False
    config.strategy_macd_enabled = False
    config.strategy_trend_enabled = True
    return BacktestManager(ApplicationState(), config)


def _fake_result(**_):
    return {
        "trades": 4, "pnl": 6.5, "pnl_pct": 6.8, "buy_hold_pct": -29.4,
        "final_value": 102.5, "max_drawdown_pct": 13.9, "sharpe_ratio": 0.45,
        "chart_data": {"candles": [], "trades": [], "portfolio_values": []},
    }


def test_result_has_risk_numbers_window_and_strategies(monkeypatch):
    monkeypatch.setattr(backtest, "run_backtest", _fake_result)
    mgr = _manager()
    out = mgr.run_backtest(days_back=365, backtest_id="abc",
                           end_date=datetime(2026, 10, 1, tzinfo=timezone.utc))
    r = out["data"]["result"]
    assert r["max_drawdown_pct"] == 13.9 and r["sharpe_ratio"] == 0.45
    assert (r["window_start"], r["window_end"]) == ("2025-10-01", "2026-10-01")
    assert r["strategies_used"] == ["Trend Hold"]


def test_strategies_used_follow_the_override(monkeypatch):
    monkeypatch.setattr(backtest, "run_backtest", _fake_result)
    mgr = _manager()
    out = mgr.run_backtest(days_back=30, config_overrides={
        "strategy_trend_enabled": False, "strategy_ema_enabled": True})
    assert out["data"]["result"]["strategies_used"] == ["EMA Crossover"]


def test_failed_run_is_recorded(monkeypatch):
    def boom(**_):
        raise RuntimeError("no candles")
    monkeypatch.setattr(backtest, "run_backtest", boom)
    mgr = _manager()
    assert mgr.run_backtest(days_back=30, backtest_id="xyz")["success"] is False
    [stored] = mgr.get_backtest_results()
    assert stored["id"] == "xyz" and stored["status"] == "failed"
    assert "no candles" in stored["error"]
    assert mgr.get_backtest_status()["running"] is False


def test_long_runs_chart_as_daily_candles():
    candles = [
        {"timestamp": f"2026-01-0{d}T{h:02d}:00:00Z", "open": 10 + h, "high": 20 + h,
         "low": 5 - h / 10, "close": 11 + h, "volume": 1}
        for d in (1, 2) for h in range(24)
    ]
    values = [{"timestamp": c["timestamp"], "value": c["close"]} for c in candles]
    daily, pv = backtest._daily_chart_series(candles, values)
    assert [c["timestamp"] for c in daily] == ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"]
    assert daily[0]["open"] == 10 and daily[0]["close"] == 34
    assert daily[0]["high"] == 43 and daily[0]["low"] == 5 - 2.3
    assert daily[0]["volume"] == 24
    assert [v["value"] for v in pv] == [34, 34]
