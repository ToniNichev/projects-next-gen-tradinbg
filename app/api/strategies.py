"""
Strategy-management API endpoints.

Routes
------
GET  /api/strategies                          List strategies and status
GET  /api/strategies/stats                    Per-strategy performance stats
POST /api/strategies/<name>/enable            Enable a strategy at runtime
POST /api/strategies/<name>/disable           Disable (guards last active)
POST /api/strategies/<name>/toggle            Toggle + persist to DB

GET  /api/config                              Full bot configuration
GET  /api/config/debug                        Config debug / DB key dump
GET  /api/strategy-config                     All strategy parameters
POST /api/strategy-config/update              Batch-update parameters in DB
POST /api/strategy-config/apply              Hot-reload running strategies

GET  /api/presets                             List saved config presets
GET  /api/presets/<name>                      Get a specific preset
POST /api/presets                             Save / update a preset
DEL  /api/presets/<name>                      Delete a custom preset
POST /api/presets/<name>/apply                Apply preset to DB + runtime
"""

import logging
from flask import Blueprint, jsonify, request

from app.extensions import limiter, require_auth
from app.core.state import get_app_state

try:
    from database import get_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False

logger = logging.getLogger(__name__)

strategies_bp = Blueprint("strategies", __name__)

# ---------------------------------------------------------------------------
# Shared config field → type/category mapping (used in update + apply preset)
# ---------------------------------------------------------------------------
CONFIG_MAPPING = {
    "symbol":                           {"type": "str",   "category": "trading"},
    "timeframe":                        {"type": "str",   "category": "trading"},
    "initial_usdt":                     {"type": "float", "category": "trading"},
    "order_pct":                        {"type": "float", "category": "trading"},
    "rsi_period":                       {"type": "int",   "category": "indicators"},
    "rsi_oversold":                     {"type": "float", "category": "indicators"},
    "rsi_overbought":                   {"type": "float", "category": "indicators"},
    "atr_period":                       {"type": "int",   "category": "indicators"},
    "atr_stop_multiplier":              {"type": "float", "category": "indicators"},
    "use_atr_stops":                    {"type": "bool",  "category": "indicators"},
    "stop_loss_pct":                    {"type": "float", "category": "risk"},
    "take_profit_pct":                  {"type": "float", "category": "risk"},
    "trailing_stop_pct":                {"type": "float", "category": "risk"},
    "use_trailing_stop":                {"type": "bool",  "category": "risk"},
    "min_position_size":                {"type": "float", "category": "position"},
    "max_position_size":                {"type": "float", "category": "position"},
    "use_dynamic_sizing":               {"type": "bool",  "category": "position"},
    "volume_threshold":                 {"type": "float", "category": "filters"},
    "require_volume_confirmation":      {"type": "bool",  "category": "filters"},
    "require_macd_confirmation":        {"type": "bool",  "category": "filters"},
    "max_trades_per_day":               {"type": "int",   "category": "filters"},
    "strategy_aggregation_mode":        {"type": "str",   "category": "multi_strategy"},
    "min_signal_confidence":            {"type": "float", "category": "multi_strategy"},
    "strategy_ema_enabled":             {"type": "bool",  "category": "ema"},
    "strategy_ema_weight":              {"type": "float", "category": "ema"},
    "short_window":                     {"type": "int",   "category": "ema"},
    "long_window":                      {"type": "int",   "category": "ema"},
    "min_trend_strength":               {"type": "float", "category": "ema"},
    "strategy_rsi_bb_enabled":          {"type": "bool",  "category": "rsi_bb"},
    "strategy_rsi_bb_weight":           {"type": "float", "category": "rsi_bb"},
    "strategy_rsi_bb_rsi_oversold":     {"type": "float", "category": "rsi_bb"},
    "strategy_rsi_bb_rsi_overbought":   {"type": "float", "category": "rsi_bb"},
    "strategy_rsi_bb_bb_period":        {"type": "int",   "category": "rsi_bb"},
    "strategy_rsi_bb_bb_std_dev":       {"type": "float", "category": "rsi_bb"},
    "strategy_rsi_bb_stop_loss_pct":    {"type": "float", "category": "rsi_bb"},
    "strategy_rsi_bb_take_profit_pct":  {"type": "float", "category": "rsi_bb"},
    "strategy_macd_enabled":            {"type": "bool",  "category": "macd"},
    "strategy_macd_weight":             {"type": "float", "category": "macd"},
    "strategy_macd_fast_period":        {"type": "int",   "category": "macd"},
    "strategy_macd_slow_period":        {"type": "int",   "category": "macd"},
    "strategy_macd_signal_period":      {"type": "int",   "category": "macd"},
    "strategy_macd_volume_multiplier":  {"type": "float", "category": "macd"},
    "strategy_macd_require_zero_cross": {"type": "bool",  "category": "macd"},
    "strategy_macd_stop_loss_pct":      {"type": "float", "category": "macd"},
    "strategy_macd_take_profit_pct":    {"type": "float", "category": "macd"},
    "strategy_llm_enabled":             {"type": "bool",  "category": "llm"},
    "strategy_llm_weight":              {"type": "float", "category": "llm"},
    "llm_ollama_model":                 {"type": "str",   "category": "llm"},
    "llm_ollama_url":                   {"type": "str",   "category": "llm"},
    "llm_lookback_days":                {"type": "int",   "category": "llm"},
    "llm_cache_minutes":                {"type": "int",   "category": "llm"},
    "llm_timeout_seconds":              {"type": "int",   "category": "llm"},
    "llm_temperature":                  {"type": "float", "category": "llm"},
    "llm_num_predict":                  {"type": "int",   "category": "llm"},
    "llm_require_patterns":             {"type": "bool",  "category": "llm"},
    "llm_backtest_sample_interval":     {"type": "int",   "category": "llm"},
}


def _get_strategy_manager():
    return get_app_state().get_strategy_manager()


def _batch_save_config(data: dict, db) -> tuple:
    """Save recognised keys to DB. Returns (configs_to_save, saved_count)."""
    configs_to_save = {
        k: {"value": v, "type": CONFIG_MAPPING[k]["type"],
            "category": CONFIG_MAPPING[k]["category"],
            "description": f"Strategy parameter: {k}"}
        for k, v in data.items() if k in CONFIG_MAPPING
    }
    count = db.set_multiple_strategy_configs(configs_to_save)
    return configs_to_save, count


# ---------------------------------------------------------------------------
# Strategy list + stats
# ---------------------------------------------------------------------------

@strategies_bp.route("/api/strategies")
@require_auth
@limiter.limit("30 per minute")
def get_strategies():
    sm = _get_strategy_manager()
    if not sm:
        return jsonify({"multi_strategy_enabled": False, "strategies": [],
                        "message": "Multi-strategy system not enabled"})
    try:
        return jsonify({
            "multi_strategy_enabled": True,
            "aggregation_mode": sm.aggregation_mode.value,
            "min_confidence": sm.min_confidence,
            "strategies": [
                {
                    "name": s.name,
                    "description": s.get_description(),
                    "enabled": s.is_enabled(),
                    "weight": s.get_weight(),
                    "parameters": s.get_parameters(),
                }
                for s in sm.strategies
            ],
            "count": len(sm.strategies),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/strategies/stats")
@require_auth
@limiter.limit("30 per minute")
def get_strategy_stats():
    sm = _get_strategy_manager()
    if not sm:
        return jsonify({"multi_strategy_enabled": False, "stats": {},
                        "message": "Multi-strategy system not enabled"})
    try:
        stats = sm.get_strategy_stats()
        total_gen = sum(s["signals_generated"] for s in stats.values())
        total_used = sum(s["signals_used"] for s in stats.values())
        for s in stats.values():
            s["generation_rate"] = (s["signals_generated"] / total_gen * 100) if total_gen else 0.0
            s["usage_rate"] = (s["signals_used"] / total_used * 100) if total_used else 0.0
            s["acceptance_rate"] = (s["signals_used"] / s["signals_generated"] * 100) if s["signals_generated"] else 0.0
        return jsonify({"multi_strategy_enabled": True,
                        "total_signals_generated": total_gen,
                        "total_signals_used": total_used,
                        "stats": stats})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/strategies/<strategy_name>/enable", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def enable_strategy(strategy_name):
    sm = _get_strategy_manager()
    if not sm:
        return jsonify({"error": "Multi-strategy system not enabled"}), 503
    try:
        sm.enable_strategy(strategy_name)
        
        # Persist to database if available
        if DATABASE_AVAILABLE:
            config_key = _get_strategy_config_key(strategy_name)
            if config_key:
                db = get_database()
                _batch_save_config({config_key: True}, db)
                logger.info(f"Persisted {strategy_name} enabled state to database")
        
        return jsonify({"success": True, "message": f"Strategy '{strategy_name}' enabled",
                        "strategy": strategy_name, "enabled": True})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/strategies/<strategy_name>/disable", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def disable_strategy(strategy_name):
    sm = _get_strategy_manager()
    if not sm:
        return jsonify({"error": "Multi-strategy system not enabled"}), 503
    try:
        if len(sm.get_enabled_strategies()) <= 1:
            return jsonify({"error": "Cannot disable the last active strategy"}), 400
        sm.disable_strategy(strategy_name)
        
        # Persist to database if available
        if DATABASE_AVAILABLE:
            config_key = _get_strategy_config_key(strategy_name)
            if config_key:
                db = get_database()
                _batch_save_config({config_key: False}, db)
                logger.info(f"Persisted {strategy_name} disabled state to database")
        
        return jsonify({"success": True, "message": f"Strategy '{strategy_name}' disabled",
                        "strategy": strategy_name, "enabled": False})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/strategies/<strategy_name>/toggle", methods=["POST"])
@require_auth
@limiter.limit("10 per minute")
def toggle_strategy(strategy_name):
    from strategies.constants import StrategyNames
    sm = _get_strategy_manager()
    if not sm:
        return jsonify({"error": "Multi-strategy system not enabled"}), 503
    if not StrategyNames.is_valid_strategy(strategy_name):
        return jsonify({"error": f"Invalid strategy name: {strategy_name}"}), 400

    try:
        strategy = next((s for s in sm.strategies if s.name == strategy_name), None)
        if not strategy:
            return jsonify({"error": f"Strategy '{strategy_name}' not found"}), 404

        currently_enabled = strategy.is_enabled()
        if currently_enabled:
            if len(sm.get_enabled_strategies()) <= 1:
                return jsonify({"error": "Cannot disable the last active strategy"}), 400
            sm.disable_strategy(strategy_name)
            new_state = False
        else:
            sm.enable_strategy(strategy_name)
            new_state = True

        # Persist to DB
        config_key = StrategyNames.get_config_key(strategy_name)
        persisted = False
        if config_key and DATABASE_AVAILABLE:
            try:
                db = get_database()
                db.set_strategy_config(
                    key=config_key, value=new_state, value_type="bool",
                    category="strategy",
                    description=f"Enable/disable {StrategyNames.get_display_name(strategy_name)} strategy"
                )
                persisted = True
            except Exception as db_err:
                logger.warning("Could not persist strategy toggle: %s", db_err)

        return jsonify({
            "success": True,
            "message": f"Strategy '{strategy_name}' {'enabled' if new_state else 'disabled'}",
            "strategy": strategy_name,
            "enabled": new_state,
            "persisted": persisted,
            "affects_backtest": persisted,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@strategies_bp.route("/api/config")
@require_auth
@limiter.limit("30 per minute")
def get_config():
    try:
        from config import BotConfig
        c = BotConfig.load()
        return jsonify({
            "symbol": c.symbol, "timeframe": c.timeframe,
            "short_window": c.short_window, "long_window": c.long_window,
            "order_pct": c.order_pct, "initial_usdt": c.initial_usdt,
            "fee_rate": c.fee_rate, "slippage": c.slippage,
            "min_trend_strength": c.min_trend_strength,
            "rsi_period": c.rsi_period, "rsi_oversold": c.rsi_oversold, "rsi_overbought": c.rsi_overbought,
            "stop_loss_pct": c.stop_loss_pct, "take_profit_pct": c.take_profit_pct,
            "trailing_stop_pct": c.trailing_stop_pct, "use_trailing_stop": c.use_trailing_stop,
            "max_position_size": c.max_position_size, "min_position_size": c.min_position_size,
            "use_dynamic_sizing": c.use_dynamic_sizing,
            "atr_period": c.atr_period, "atr_stop_multiplier": c.atr_stop_multiplier,
            "use_atr_stops": c.use_atr_stops,
            "macd_fast": c.macd_fast, "macd_slow": c.macd_slow, "macd_signal": c.macd_signal,
            "require_macd_confirmation": c.require_macd_confirmation,
            "require_volume_confirmation": c.require_volume_confirmation,
            "volume_threshold": c.volume_threshold,
            "max_trades_per_day": c.max_trades_per_day,
            "use_multi_strategy": c.use_multi_strategy,
            "strategy_aggregation_mode": c.strategy_aggregation_mode,
            "min_signal_confidence": c.min_signal_confidence,
            "strategy_ema_enabled": c.strategy_ema_enabled,
            "strategy_ema_weight": c.strategy_ema_weight,
            "strategy_rsi_bb_enabled": c.strategy_rsi_bb_enabled,
            "strategy_rsi_bb_weight": c.strategy_rsi_bb_weight,
            "strategy_rsi_bb_rsi_oversold": c.strategy_rsi_bb_rsi_oversold,
            "strategy_rsi_bb_rsi_overbought": c.strategy_rsi_bb_rsi_overbought,
            "strategy_rsi_bb_bb_period": c.strategy_rsi_bb_bb_period,
            "strategy_rsi_bb_bb_std_dev": c.strategy_rsi_bb_bb_std_dev,
            "strategy_rsi_bb_stop_loss_pct": c.strategy_rsi_bb_stop_loss_pct,
            "strategy_rsi_bb_take_profit_pct": c.strategy_rsi_bb_take_profit_pct,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/config/debug")
@require_auth
@limiter.limit("60 per minute")
def debug_config():
    try:
        from config import BotConfig
        c = BotConfig.load()
        db_configs, db_count = {}, 0
        if DATABASE_AVAILABLE:
            try:
                db = get_database()
                db_configs = db.get_all_strategy_configs()
                db_count = len(db_configs)
            except Exception:
                pass
        return jsonify({
            "success": True,
            "database_configs_count": db_count,
            "has_database": DATABASE_AVAILABLE,
            "config_summary": {
                "stop_loss_pct": c.stop_loss_pct, "take_profit_pct": c.take_profit_pct,
                "order_pct": c.order_pct, "strategy_aggregation_mode": c.strategy_aggregation_mode,
                "min_signal_confidence": c.min_signal_confidence,
                "strategy_ema_enabled": c.strategy_ema_enabled, "strategy_ema_weight": c.strategy_ema_weight,
                "strategy_rsi_bb_enabled": c.strategy_rsi_bb_enabled, "strategy_rsi_bb_weight": c.strategy_rsi_bb_weight,
                "strategy_macd_enabled": c.strategy_macd_enabled, "strategy_macd_weight": c.strategy_macd_weight,
            },
            "sample_db_keys": list(db_configs.keys())[:10],
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/strategy-config")
@require_auth
@limiter.limit("30 per minute")
def get_strategy_config():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        db = get_database()
        configs = db.get_all_strategy_configs()
        if not configs:
            from config import BotConfig
            c = BotConfig.load()
            configs = {k: getattr(c, k, None) for k in CONFIG_MAPPING}
        return jsonify({"success": True, "config": configs,
                        "source": "database" if configs else "env"})
    except Exception as exc:
        logger.error("get_strategy_config failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/strategy-config/update", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")
def update_strategy_config():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        db = get_database()
        configs_to_save, count = _batch_save_config(data, db)
        return jsonify({"success": True, "message": f"Updated {count} parameters",
                        "updated_keys": list(configs_to_save.keys())})
    except Exception as exc:
        logger.error("update_strategy_config failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/strategy-config/apply", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")
def apply_strategy_config():
    sm = _get_strategy_manager()
    if not sm:
        return jsonify({"success": False, "message": "Multi-strategy system not enabled"}), 400
    try:
        from config import BotConfig
        sm.reload_config(BotConfig.load())
        return jsonify({"success": True, "message": "Configuration applied",
                        "strategies_reloaded": len(sm.strategies)})
    except Exception as exc:
        logger.error("apply_strategy_config failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@strategies_bp.route("/api/presets", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_presets():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        presets = get_database().get_all_presets()
        return jsonify({"success": True, "presets": presets, "count": len(presets)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/presets/<preset_name>", methods=["GET"])
@require_auth
@limiter.limit("60 per minute")
def get_preset(preset_name):
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        preset = get_database().get_preset(preset_name)
        if not preset:
            return jsonify({"error": "Preset not found"}), 404
        return jsonify({"success": True, "preset": preset})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/presets", methods=["POST"])
@require_auth
@limiter.limit("20 per minute")
def save_preset():
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        name = data.get("name")
        display_name = data.get("display_name")
        config = data.get("config")
        if not name or not display_name or not config:
            return jsonify({"error": "Missing required fields: name, display_name, config"}), 400
        preset = get_database().save_preset(
            name=name, display_name=display_name,
            description=data.get("description", ""),
            config=config, category=data.get("category", "custom"),
            is_builtin=False, is_default=False,
        )
        return jsonify({"success": True, "message": f"Preset '{display_name}' saved", "preset": preset})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/presets/<preset_name>", methods=["DELETE"])
@require_auth
@limiter.limit("20 per minute")
def delete_preset(preset_name):
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        deleted = get_database().delete_preset(preset_name)
        if not deleted:
            return jsonify({"error": "Preset not found or cannot be deleted (built-in)"}), 404
        return jsonify({"success": True, "message": f"Preset '{preset_name}' deleted"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@strategies_bp.route("/api/presets/<preset_name>/apply", methods=["POST"])
@require_auth
@limiter.limit("30 per minute")
def apply_preset(preset_name):
    if not DATABASE_AVAILABLE:
        return jsonify({"error": "Database not available"}), 503
    try:
        db = get_database()
        preset = db.get_preset(preset_name)
        if not preset:
            return jsonify({"error": "Preset not found"}), 404

        configs_to_save, count = _batch_save_config(preset["config"], db)

        # Hot-reload running strategies
        sm = _get_strategy_manager()
        applied_to_runtime = False
        if sm:
            try:
                from config import BotConfig
                sm.reload_config(BotConfig.load())
                applied_to_runtime = True
            except Exception as exc:
                logger.warning("Could not apply preset to runtime: %s", exc)

        return jsonify({
            "success": True,
            "message": f"Preset '{preset['display_name']}' applied",
            "preset": preset,
            "configs_updated": count,
            "applied_to_runtime": applied_to_runtime,
            "requires_restart": "timeframe" in preset["config"] or "symbol" in preset["config"],
        })
    except Exception as exc:
        logger.error("apply_preset failed: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500
