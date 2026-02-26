"""
Core API blueprint.

Handles endpoints that don't belong cleanly to a single domain module
and provides the service-injection function used by the app factory.

Routes
------
GET  /api/health                  Health check (no auth required)
GET  /api/state                   Structured trading state (new API format)

GET  /api/backtest/run      POST  Run a backtest (delegated to BacktestManager)
GET  /api/backtest/status         Current running status & progress
GET  /api/backtest/results        All stored results
GET  /api/backtest/results/<id>   Single result by ID
POST /api/backtest/clear          Delete all results
GET  /api/backtest/timing-history Historical run-time data for ETA estimation
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from flask import Blueprint, jsonify, request

try:
    from auth import require_auth
except ImportError:
    def require_auth(f):  # type: ignore[misc]
        return f

from app.core.state import get_app_state
from app.services.trading_manager import TradingManager
from app.services.config_service import ConfigService
from app.services.backtest_manager import BacktestManager

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

_trading_manager: TradingManager = None  # type: ignore[assignment]
_config_service: ConfigService = None     # type: ignore[assignment]
_backtest_manager: BacktestManager = None  # type: ignore[assignment]


def init_api_services(
    trading_manager: TradingManager,
    config_service: ConfigService,
    backtest_manager: BacktestManager,
) -> None:
    """Inject service dependencies.  Called once from the app factory."""
    global _trading_manager, _config_service, _backtest_manager
    _trading_manager = trading_manager
    _config_service = config_service
    _backtest_manager = backtest_manager
    logger.info("API services initialised")


def create_response(
    success: bool,
    data: Any = None,
    error: str = None,
    message: str = None,
) -> Dict[str, Any]:
    """Standardised API response envelope."""
    resp: Dict[str, Any] = {"success": success}
    if data is not None:
        resp["data"] = data
    if error is not None:
        resp["error"] = error
    if message is not None:
        resp["message"] = message
    return resp


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@api_bp.route("/health")
def health_check():
    """Lightweight health probe — no auth required."""
    try:
        ts = get_app_state().get_trading_state()
        return jsonify(create_response(success=True, data={
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trading_enabled": ts.trading_enabled,
            "emergency_stop": ts.emergency_stop,
            "services": {
                "trading_manager": _trading_manager is not None,
                "config_service": _config_service is not None,
                "backtest_manager": _backtest_manager is not None,
            },
        }))
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        return jsonify(create_response(success=False, error=str(exc))), 500


# ---------------------------------------------------------------------------
# Structured state (new-API format — different from the legacy /state endpoint
# in market_bp which the existing UI templates use directly)
# ---------------------------------------------------------------------------

@api_bp.route("/state")
@require_auth
def get_api_state():
    """Return trading state in the {success, data} envelope format."""
    try:
        ts = get_app_state().get_trading_state()
        return jsonify(create_response(success=True, data={
            "usdt_balance": ts.usdt_balance,
            "base_balance": ts.base_balance,
            "current_price": ts.current_price,
            "position_open": ts.position_open,
            "position_entry_price": ts.position_entry_price,
            "position_amount": ts.position_amount,
            "position_side": ts.position_side,
            "stop_loss": ts.stop_loss,
            "take_profit": ts.take_profit,
            "trailing_stop": ts.trailing_stop,
            "trading_enabled": ts.trading_enabled,
            "emergency_stop": ts.emergency_stop,
            "last_update": ts.last_update.isoformat(),
        }))
    except Exception as exc:
        logger.error("Failed to get API state: %s", exc)
        return jsonify(create_response(success=False, error=str(exc))), 500


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

@api_bp.route("/backtest/run", methods=["POST"])
@require_auth
def run_backtest():
    if _backtest_manager is None:
        return jsonify(create_response(success=False, error="Backtest manager not initialised")), 503
    try:
        data = request.get_json() or {}
        days_back = int(data.get("days_back", 30))
        if days_back <= 0:
            return jsonify(create_response(success=False, error="days_back must be > 0")), 400

        result = _backtest_manager.run_backtest(
            days_back=days_back,
            config_overrides=data.get("config_overrides"),
        )
        return jsonify(result), 200 if result.get("success") else 400
    except ValueError as exc:
        return jsonify(create_response(success=False, error=str(exc))), 400
    except Exception as exc:
        logger.error("Backtest run failed: %s", exc, exc_info=True)
        return jsonify(create_response(success=False, error=str(exc))), 500


@api_bp.route("/backtest/status")
@require_auth
def get_backtest_status():
    if _backtest_manager is None:
        return jsonify(create_response(success=False, error="Backtest manager not initialised")), 503
    try:
        return jsonify(create_response(success=True, data=_backtest_manager.get_backtest_status()))
    except Exception as exc:
        return jsonify(create_response(success=False, error=str(exc))), 500


@api_bp.route("/backtest/results")
@require_auth
def get_backtest_results():
    if _backtest_manager is None:
        return jsonify(create_response(success=False, error="Backtest manager not initialised")), 503
    try:
        return jsonify(create_response(success=True, data=_backtest_manager.get_backtest_results()))
    except Exception as exc:
        return jsonify(create_response(success=False, error=str(exc))), 500


@api_bp.route("/backtest/results/<backtest_id>")
@require_auth
def get_backtest_result(backtest_id):
    if _backtest_manager is None:
        return jsonify(create_response(success=False, error="Backtest manager not initialised")), 503
    try:
        results = _backtest_manager.get_backtest_results()
        items = results.get("results", results) if isinstance(results, dict) else results
        match = next((r for r in items if r.get("id") == backtest_id), None)
        if not match:
            return jsonify(create_response(success=False, error="Backtest not found")), 404
        return jsonify(create_response(success=True, data=match))
    except Exception as exc:
        return jsonify(create_response(success=False, error=str(exc))), 500


@api_bp.route("/backtest/clear", methods=["POST", "DELETE"])
@require_auth
def clear_backtest_results():
    if _backtest_manager is None:
        return jsonify(create_response(success=False, error="Backtest manager not initialised")), 503
    try:
        app_state = get_app_state()
        bs = app_state.get_backtest_state()
        count = len(bs.results) if hasattr(bs, "results") else 0
        # Clear via state
        if hasattr(bs, "results"):
            bs.results.clear()
        return jsonify(create_response(success=True,
                                       message=f"Cleared {count} backtest result(s)",
                                       data={"count": count}))
    except Exception as exc:
        return jsonify(create_response(success=False, error=str(exc))), 500


@api_bp.route("/backtest/timing-history")
@require_auth
def get_timing_history():
    if _backtest_manager is None:
        return jsonify(create_response(success=False, error="Backtest manager not initialised")), 503
    try:
        results = _backtest_manager.get_backtest_results()
        items = results.get("results", results) if isinstance(results, dict) else results

        history: Dict[int, list] = {}
        for r in items[:20]:
            if "duration_seconds" in r and r.get("status") == "completed":
                days = r.get("days_back", 0)
                history.setdefault(days, []).append(r["duration_seconds"])

        averages = {d: sum(t) / len(t) for d, t in history.items() if t}
        return jsonify(create_response(success=True, data={"averages": averages, "raw_data": history}))
    except Exception as exc:
        return jsonify(create_response(success=False, error=str(exc))), 500
