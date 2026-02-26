"""
LLM (Ollama) API endpoints.

Routes
------
GET  /api/llm/latest              Most recent LLM pattern analysis
GET  /api/llm/history             Historical LLM analyses
POST /api/llm/trigger             Manually trigger a fresh analysis
POST /api/llm/clear-cache         Delete all cached analyses
GET  /api/llm/models              Available Ollama models
POST /api/llm/test-connection     Test Ollama connection server-side
POST /api/llm/validate            Run multi-period direction validation
POST /api/llm/validate/quick      Run single quick validation (~15 s)
GET  /api/llm/validate/results    All stored validation results
GET  /api/llm/validate/status     Current validation status
"""

import json
import logging
import threading
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.extensions import limiter, require_auth
from app.core.state import get_app_state

try:
    from database import get_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

logger = logging.getLogger(__name__)

llm_bp = Blueprint("llm", __name__)

# In-memory validation state (transient, no persistence needed)
_validation_results: list = []
_validation_running: bool = False


# ---------------------------------------------------------------------------
# Analysis read endpoints
# ---------------------------------------------------------------------------

@llm_bp.route("/api/llm/latest")
@require_auth
@limiter.limit("30 per minute")
def get_latest_llm_analysis():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        analysis = get_database().get_latest_llm_analysis()
        if not analysis:
            return jsonify({"error": "No LLM analysis available yet"}), 404
        return jsonify({
            "timestamp": analysis.timestamp.isoformat(),
            "direction": analysis.direction,
            "confidence": analysis.confidence,
            "reasoning": analysis.reasoning,
            "patterns_found": json.loads(analysis.patterns_found),
            "suggested_stop_loss": analysis.suggested_stop_loss,
            "suggested_take_profit": analysis.suggested_take_profit,
            "suggested_position_size": analysis.suggested_position_size,
            "current_price": analysis.current_price,
            "recent_win_rate": analysis.recent_win_rate,
            "recent_pnl": analysis.recent_pnl,
            "cache_valid_until": analysis.cache_valid_until.isoformat(),
            "model_used": analysis.model_used,
            "analysis_duration_ms": analysis.analysis_duration_ms,
            "num_trades_analyzed": analysis.num_trades_analyzed,
            "analysis_period_days": analysis.analysis_period_days,
        })
    except Exception as exc:
        logger.error("get_latest_llm_analysis failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@llm_bp.route("/api/llm/history")
@require_auth
@limiter.limit("30 per minute")
def get_llm_analysis_history():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        analyses = get_database().get_llm_analysis_history(limit=limit)
        return jsonify({
            "analyses": [
                {
                    "timestamp": a.timestamp.isoformat(),
                    "direction": a.direction,
                    "confidence": a.confidence,
                    "patterns_found": json.loads(a.patterns_found) if a.patterns_found else [],
                    "patterns_count": len(json.loads(a.patterns_found)) if a.patterns_found else 0,
                    "current_price": a.current_price,
                    "reasoning": (a.reasoning[:100] + "...") if len(a.reasoning or "") > 100 else a.reasoning,
                }
                for a in analyses
            ],
            "count": len(analyses),
        })
    except Exception as exc:
        logger.error("get_llm_analysis_history failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Trigger / cache management
# ---------------------------------------------------------------------------

@llm_bp.route("/api/llm/trigger", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def trigger_llm_analysis():
    app_state = get_app_state()
    sm = app_state.get_strategy_manager()
    if not sm:
        return jsonify({"error": "Strategy manager not available"}), 503

    try:
        from strategies.constants import StrategyNames
        llm_strategy = next(
            (s for s in sm.strategies if s.name == StrategyNames.LLM_PATTERN), None
        )
        if not llm_strategy:
            return jsonify({"error": "LLM strategy not configured"}), 503

        exchange = app_state.get_exchange()

        def _run():
            try:
                if llm_strategy.db_manager:
                    try:
                        from database import LLMAnalysis
                        with llm_strategy.db_manager.get_session() as session:
                            session.query(LLMAnalysis).delete()
                            session.commit()
                    except Exception as exc:
                        logger.warning("Could not clear LLM cache before trigger: %s", exc)

                from config import BotConfig
                config = BotConfig.load()
                signal = llm_strategy.compute_signal(
                    exchange=exchange,
                    symbol=config.symbol,
                    timeframe=config.timeframe,
                    candle_data=None,
                )
                logger.info("Manual LLM analysis: %s (conf=%.2f)",
                            signal.direction, signal.confidence)
            except Exception as exc:
                logger.error("Manual LLM analysis failed: %s", exc, exc_info=True)

        threading.Thread(target=_run, daemon=True, name="ManualLLMAnalysis").start()
        return jsonify({"status": "triggered",
                        "message": "LLM analysis started. Results available in 10-30 seconds."})
    except Exception as exc:
        logger.error("trigger_llm_analysis failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@llm_bp.route("/api/llm/clear-cache", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def clear_llm_cache():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        from database import LLMAnalysis
        db = get_database()
        with db.get_session() as session:
            count = session.query(LLMAnalysis).delete()
        logger.info("Cleared %d LLM cache entries", count)
        return jsonify({"status": "success",
                        "message": f"Cleared {count} cached entries",
                        "count": count})
    except Exception as exc:
        logger.error("clear_llm_cache failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Ollama connectivity
# ---------------------------------------------------------------------------

@llm_bp.route("/api/llm/models")
@require_auth
@limiter.limit("30 per minute")
def get_ollama_models():
    try:
        import requests
        from config import BotConfig
        config = BotConfig.load()
        try:
            resp = requests.get(f"{config.llm_ollama_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [
                {"name": m.get("name", ""), "size": m.get("size", 0), "modified": m.get("modified_at", "")}
                for m in resp.json().get("models", [])
            ]
            return jsonify({"success": True, "models": models, "count": len(models)})
        except requests.exceptions.ConnectionError:
            return jsonify({"success": False,
                            "error": f"Cannot connect to Ollama at {config.llm_ollama_url}",
                            "models": []}), 503
        except Exception as exc:
            return jsonify({"success": False, "error": str(exc), "models": []}), 500
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "models": []}), 500


@llm_bp.route("/api/llm/test-connection", methods=["POST"])
@require_auth
@limiter.limit("20 per minute")
def test_llm_connection():
    import requests
    try:
        from config import BotConfig
        config = BotConfig.load()
        data = request.get_json() or {}
        ollama_url = data.get("url", config.llm_ollama_url)
        model_name = data.get("model", config.llm_ollama_model)

        try:
            ver_resp = requests.get(f"{ollama_url}/api/version", timeout=5)
            ver_resp.raise_for_status()
            ollama_version = ver_resp.json().get("version", "unknown")
        except requests.exceptions.ConnectionError:
            return jsonify({"success": False,
                            "error": f"Cannot connect to Ollama at {ollama_url}. Is it running?",
                            "url": ollama_url, "model": model_name,
                            "suggestion": "Run 'ollama serve' on the server"}), 503
        except requests.exceptions.Timeout:
            return jsonify({"success": False,
                            "error": f"Connection to {ollama_url} timed out",
                            "url": ollama_url, "model": model_name}), 504

        try:
            models_resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
            models_resp.raise_for_status()
            available = [m["name"] for m in models_resp.json().get("models", [])]
            model_exists = any(m.startswith(model_name) for m in available)
        except Exception:
            available, model_exists = [], False

        return jsonify({
            "success": True, "version": ollama_version,
            "model_exists": model_exists, "available_models": available,
            "url": ollama_url, "model": model_name,
        })
    except Exception as exc:
        logger.error("test_llm_connection failed: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@llm_bp.route("/api/llm/validate", methods=["POST"])
@require_auth
@limiter.limit("5 per minute")
def run_llm_validation():
    global _validation_running, _validation_results
    if _validation_running:
        return jsonify({"error": "Validation already running"}), 409

    try:
        from config import BotConfig
        try:
            from llm_validator import LLMValidator
        except ImportError:
            return jsonify({"error": "LLM validator not available"}), 500

        config = BotConfig.load()
        data = request.get_json() or {}
        num_tests = data.get("num_tests", 5)
        quick_mode = data.get("quick", False)
        model = data.get("model", config.llm_ollama_model)

        _validation_running = True
        validator = LLMValidator(ollama_url=config.llm_ollama_url, model=model, symbol=config.symbol)

        results = validator.quick_test() if quick_mode else validator.run_validation(num_tests=num_tests)
        results["id"] = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        results["timestamp"] = datetime.now(timezone.utc).isoformat()

        _validation_results.insert(0, results)
        if len(_validation_results) > 20:
            _validation_results[:] = _validation_results[:20]

        _validation_running = False
        return jsonify(results)
    except Exception as exc:
        _validation_running = False
        logger.error("run_llm_validation failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@llm_bp.route("/api/llm/validate/quick", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def run_quick_validation():
    global _validation_running
    if _validation_running:
        return jsonify({"error": "Validation already running"}), 409
    try:
        from config import BotConfig
        from llm_validator import LLMValidator
        config = BotConfig.load()
        _validation_running = True
        validator = LLMValidator(ollama_url=config.llm_ollama_url, model=config.llm_ollama_model, symbol=config.symbol)
        results = validator.quick_test()
        results["timestamp"] = datetime.now(timezone.utc).isoformat()
        _validation_running = False
        return jsonify(results)
    except Exception as exc:
        _validation_running = False
        return jsonify({"error": str(exc)}), 500


@llm_bp.route("/api/llm/validate/results")
@require_auth
@limiter.limit("30 per minute")
def get_validation_results():
    return jsonify({"results": _validation_results, "running": _validation_running})


@llm_bp.route("/api/llm/validate/status")
@require_auth
@limiter.limit("30 per minute")
def get_validation_status():
    return jsonify({
        "running": _validation_running,
        "last_result": _validation_results[0] if _validation_results else None,
    })
