"""
Application factory module.

This is the single entry point for creating and starting the Flask
application.  It builds a fresh Flask app, wires all Blueprints at their
canonical URL paths, and initialises shared extensions (rate-limiter, CORS,
auth).

Typical usage in ``main.py``::

    from app import create_app, init_services, start_app
    from app.core.state import get_app_state

    flask_app = create_app()
    app_state  = init_services(trader, lock, exchange, strategy_manager, config)
    start_app(flask_app, config.dashboard_host, config.dashboard_port)
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

__version__ = "2.0.0"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_app(config=None):
    """
    Create and return the configured Flask application.

    All route Blueprints are registered here at their canonical URL paths.
    The old ``dashboard.py`` is no longer used as the server; it is kept
    only for its helper functions (``_record_history``, ``set_trader``, etc.)
    that ``main.py`` still calls during the transition.
    """
    from flask import Flask

    # Templates live at the project root's ``templates/`` directory.
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    # Static files live at the project root's ``static/`` directory.
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["JSON_SORT_KEYS"] = False

    # Reduce werkzeug noise (errors only)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    # Initialise extensions (limiter, CORS) once the app exists.
    from app.extensions import init_extensions
    init_extensions(app)

    # Register all Blueprints
    _register_blueprints(app)

    return app


def _register_blueprints(app) -> None:
    """Register all route Blueprints on the Flask app."""

    # Core API (health, state, manual buy/sell, trading enable/disable, config, backtest)
    from app.api.routes import api_bp
    app.register_blueprint(api_bp)          # url_prefix=/api  (defined inside the blueprint)

    # Market data (/state, /history, /api/candles, /api/trades, /api/stats, ...)
    from app.api.market import market_bp
    app.register_blueprint(market_bp)       # no prefix — /state and /history at root

    # Trading controls (/api/manual/*, /api/trading/*)
    from app.api.trading import trading_bp
    app.register_blueprint(trading_bp)

    # Strategy management (/api/strategies/*, /api/strategy-config, /api/presets/*, /api/config)
    from app.api.strategies import strategies_bp
    app.register_blueprint(strategies_bp)

    # LLM analysis (/api/llm/*)
    from app.api.llm import llm_bp
    app.register_blueprint(llm_bp)

    # RAG (/api/rag/*)
    from app.api.rag import rag_bp
    app.register_blueprint(rag_bp)

    # UI pages (/, /ui, /backtest, /strategies, /settings, /strategy-config, /logout)
    from app.ui.routes import ui_bp
    app.register_blueprint(ui_bp)

    logger.info(
        "Registered blueprints: api, market, trading, strategies, llm, rag, ui"
    )


# ---------------------------------------------------------------------------
# Service-layer wiring
# ---------------------------------------------------------------------------

def init_services(trader, lock, exchange, strategy_manager, config) -> "ApplicationState":
    """
    Wire up the service layer and populate :class:`ApplicationState`.

    Must be called *after* :func:`create_app` and *before*
    :func:`start_app` so all services are ready when the first HTTP
    request arrives.

    Returns the populated :class:`ApplicationState` singleton.
    """
    from app.core.state import get_app_state
    from app.services.trading_manager import TradingManager
    from app.services.config_service import ConfigService
    from app.services.backtest_manager import BacktestManager
    from app.api.routes import init_api_services

    app_state = get_app_state()
    app_state.set_trader(trader, lock, exchange, strategy_manager)

    # Seed balances immediately so the first /state call is meaningful.
    try:
        balances = trader.get_balances()
        app_state.update_trading_state(
            usdt_balance=balances.get("USDT", 0.0),
            base_balance=balances.get("BASE", 0.0),
        )
    except Exception as exc:
        logger.warning("Could not seed ApplicationState balances: %s", exc)

    trading_manager = TradingManager(app_state, config)
    config_service = ConfigService()
    backtest_manager = BacktestManager(app_state, config)

    init_api_services(trading_manager, config_service, backtest_manager)

    logger.info("Service layer ready: TradingManager, ConfigService, BacktestManager")
    return app_state


# ---------------------------------------------------------------------------
# Server startup
# ---------------------------------------------------------------------------

def start_app(app, host: str = "0.0.0.0", port: int = 8000) -> None:
    """
    Start the Flask app in a background daemon thread.

    Configures CORS and rate-limiting from :class:`BotConfig` before
    launching, mirroring what the old ``dashboard.start_dashboard()`` did.
    """
    _configure_security(app)

    def _runner():
        try:
            logger.info("Starting Flask app on %s:%s", host, port)
            app.run(
                host=host,
                port=port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )
        except Exception as exc:
            logger.error("Flask app failed to start: %s", exc, exc_info=True)

    thread = threading.Thread(target=_runner, daemon=True, name="FlaskApp")
    thread.start()
    logger.info("Flask app thread started (daemon=True, port=%s)", port)


def _configure_security(app) -> None:
    """Configure CORS and rate-limiting from BotConfig."""
    try:
        from config import BotConfig
        from flask_cors import CORS
        from app.extensions import limiter

        config = BotConfig.load()

        origins = config.allowed_origins
        if origins == "*":
            CORS(app, resources={r"/*": {"origins": "*"}})
        else:
            CORS(app, resources={r"/*": {"origins": [o.strip() for o in origins.split(",")]}})

        if not config.enable_rate_limiting:
            limiter.enabled = False
        else:
            limiter.limit(f"{config.rate_limit_per_minute} per minute")

        if config.dashboard_auth_enabled:
            logger.info("Auth: ENABLED (user: %s)", config.dashboard_username)
        else:
            logger.warning("Auth: DISABLED — all endpoints are public")

        logger.info("CORS: %s | Rate-limiting: %s",
                    origins,
                    f"{config.rate_limit_per_minute} req/min" if config.enable_rate_limiting else "OFF")

    except Exception as exc:
        logger.error("Security config failed, using permissive defaults: %s", exc)
        from flask_cors import CORS
        CORS(app, resources={r"/*": {"origins": "*"}})
