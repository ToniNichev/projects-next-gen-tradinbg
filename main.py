import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import json
import websocket
import ccxt

from config import BotConfig
from app import create_app, init_services, start_app
from app.core.state import get_app_state
from paper_trader import PaperTrader

# Import LiveTrader for real money trading
try:
    from live_trader import LiveTrader, TradingMode
    LIVE_TRADER_AVAILABLE = True
except ImportError:
    LIVE_TRADER_AVAILABLE = False
    logging.warning("LiveTrader module not available. Only paper trading supported.")

from strategies import (
    EMACrossoverStrategy,
    RSIBollingerBandsStrategy,
    MACDVolumeStrategy,
    StrategyManager,
    SignalAggregationMode,
)

try:
    from database import initialize_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    logging.warning("Database module not available. Install SQLAlchemy to enable database features.")

try:
    from seed_history import seed_candle_history
    SEED_HISTORY_AVAILABLE = True
except ImportError:
    SEED_HISTORY_AVAILABLE = False

try:
    from notify import send_notification
except ImportError:
    def send_notification(title: str, body: str, *, severity: str = "warning") -> None:
        logging.getLogger(__name__).warning(
            "notify module unavailable; would alert [%s] %s", severity, title,
        )


def _configure_logging(log_dir: str = "logs") -> None:
    """Configure root logger with a rotating file handler and a stderr
    handler restricted to WARNING+.

    Why: Python's default ``logging.basicConfig`` sends every level to
    stderr. When the bot runs under launchd, that stream is captured into
    ``logs/bot_error.log`` (``StandardErrorPath``) which has no rotation
    and grows without bound. Routing INFO+ to a rotated file and only
    WARNING+ to stderr keeps the launchd error file small and bounds disk
    usage to roughly ``maxBytes * (backupCount + 1)``.
    """
    os.makedirs(log_dir, exist_ok=True)
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    formatter = logging.Formatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def build_exchange(config: BotConfig) -> ccxt.binanceus:
    import socket
    import urllib3.util.connection as urllib3_cn
    
    # Force IPv4 to avoid Binance.US IPv6 error
    def allowed_gai_family():
        return socket.AF_INET
    
    urllib3_cn.allowed_gai_family = allowed_gai_family
    
    exchange = ccxt.binanceus(
        {
            "apiKey": config.binance_api_key,
            "secret": config.binance_api_secret,
            "enableRateLimit": True,
        }
    )
    exchange.options["defaultType"] = (
        "future" if config.exchange_type == "future" else "spot"
    )
    return exchange


def main():
    _configure_logging()
    
    # Initialize database BEFORE loading config so config can read from DB
    if DATABASE_AVAILABLE:
        try:
            initialize_database("sqlite:///data/trading.db")
            logging.info("✓ Database initialized for configuration loading")
        except Exception as e:
            logging.warning(f"Could not initialize database: {e}, using environment variables")
    
    # Now load config (will read from database if available)
    config = BotConfig.load()

    from auth import enforce_production_auth
    enforce_production_auth(config)

    if not config.binance_api_key or not config.binance_api_secret:
        logging.warning(
            "BINANCE_US_KEY/BINANCE_US_SECRET missing; data is restricted to public endpoints."
        )

    exchange = build_exchange(config)
    
    # Initialize database if enabled
    db_manager = None
    if config.enable_database and DATABASE_AVAILABLE:
        try:
            db_manager = initialize_database(config.database_url)
            logging.info(f"Database initialized: {config.database_url}")
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            logging.warning("Continuing without database support")
    
    # Determine trading mode and create appropriate trader
    trading_mode = config.trading_mode.lower()
    use_live_trader = False
    
    if trading_mode in ("live", "dry_run") and LIVE_TRADER_AVAILABLE:
        # Validate live trading configuration
        if trading_mode == "live":
            if not config.live_trading_enabled:
                logging.error("=" * 80)
                logging.error("🚨 LIVE TRADING BLOCKED: BOT_LIVE_TRADING_ENABLED is not set to 'true'")
                logging.error("Set BOT_LIVE_TRADING_ENABLED=true in your .env file to enable live trading")
                logging.error("=" * 80)
                logging.warning("Falling back to PAPER trading mode for safety")
                trading_mode = "paper"
            elif not config.binance_api_key or not config.binance_api_secret:
                logging.error("=" * 80)
                logging.error("🚨 LIVE TRADING BLOCKED: API credentials missing")
                logging.error("Set BINANCE_US_KEY and BINANCE_US_SECRET in your .env file")
                logging.error("=" * 80)
                logging.warning("Falling back to PAPER trading mode for safety")
                trading_mode = "paper"
            else:
                use_live_trader = True
                logging.warning("=" * 80)
                logging.warning("⚠️  LIVE TRADING MODE ENABLED - REAL MONEY AT RISK! ⚠️")
                logging.warning("=" * 80)
        else:  # dry_run
            use_live_trader = True
            logging.info("=" * 80)
            logging.info("📝 DRY RUN MODE - Signals logged but NOT executed")
            logging.info("=" * 80)
    
    if use_live_trader:
        # Create LiveTrader for live/dry_run modes
        mode = TradingMode.LIVE if trading_mode == "live" else TradingMode.DRY_RUN
        
        trader = LiveTrader(
            exchange=exchange,
            config=config,
            mode=mode,
            db_manager=db_manager,
        )
        
        # Sync balances and positions from exchange
        try:
            trader.sync_balances()
            trader.sync_positions()
            logging.info(f"Exchange sync complete: USDT=${trader.usdt_balance:.2f}, BTC={trader.base_balance:.8f}")
        except Exception as e:
            logging.error(f"Failed to sync with exchange: {e}")
            if trading_mode == "live":
                logging.error("Cannot start live trading without exchange sync. Exiting.")
                return
    else:
        # Create PaperTrader for paper trading (default/safe mode)
        logging.info("=" * 80)
        logging.info("📄 PAPER TRADING MODE - Simulated trades only")
        logging.info("=" * 80)
        
        trader = PaperTrader(
            initial_usdt=config.initial_usdt,
            fee_rate=config.fee_rate,
            slippage=config.slippage,
            log_path=config.trades_log_path,
            use_trailing_stop=config.use_trailing_stop,
            trailing_stop_pct=config.trailing_stop_pct,
            db_manager=db_manager,
            enable_database=config.enable_database,
            enable_csv_logging=config.enable_csv_logging,
        )
    
    # Initialize strategy system
    strategy_manager = None
    if config.use_multi_strategy:
        # Create ALL strategies (regardless of enabled state)
        # This allows toggling via dashboard without restart
        strategies = []
        strategy_configs = config.get_strategy_configs()
        
        # EMA Crossover Strategy - always create, set enabled state from config
        ema_strategy = EMACrossoverStrategy(strategy_configs["ema_crossover"])
        ema_strategy.set_enabled(strategy_configs["ema_crossover"]["enabled"])
        strategies.append(ema_strategy)
        status = "✓ Enabled" if ema_strategy.is_enabled() else "✗ Disabled"
        logging.info(f"{status}: {ema_strategy.name} (weight: {ema_strategy.get_weight()})")
        
        # RSI + Bollinger Bands Strategy - always create, set enabled state from config
        rsi_bb_strategy = RSIBollingerBandsStrategy(strategy_configs["rsi_bb"])
        rsi_bb_strategy.set_enabled(strategy_configs["rsi_bb"]["enabled"])
        strategies.append(rsi_bb_strategy)
        status = "✓ Enabled" if rsi_bb_strategy.is_enabled() else "✗ Disabled"
        logging.info(f"{status}: {rsi_bb_strategy.name} (weight: {rsi_bb_strategy.get_weight()})")
        
        # MACD + Volume Momentum Strategy - always create, set enabled state from config
        macd_strategy = MACDVolumeStrategy(strategy_configs["macd_volume"])
        macd_strategy.set_enabled(strategy_configs["macd_volume"]["enabled"])
        strategies.append(macd_strategy)
        status = "✓ Enabled" if macd_strategy.is_enabled() else "✗ Disabled"
        logging.info(f"{status}: {macd_strategy.name} (weight: {macd_strategy.get_weight()})")
        
        # LLM Pattern Strategy - always create, set enabled state from config
        llm_scheduler = None
        try:
            from strategies.llm.strategy import LLMPatternStrategy
            from llm_scheduler import LLMScheduler
            
            llm_strategy = LLMPatternStrategy(strategy_configs["llm_pattern"], db_manager=db_manager)
            llm_strategy.set_enabled(strategy_configs["llm_pattern"]["enabled"])
            strategies.append(llm_strategy)
            status = "✓ Enabled" if llm_strategy.is_enabled() else "✗ Disabled"
            logging.info(f"{status}: {llm_strategy.name} (weight: {llm_strategy.get_weight()})")
            
            # Start background scheduler for LLM analysis
            if llm_strategy.is_enabled():
                llm_scheduler = LLMScheduler(
                    llm_strategy=llm_strategy,
                    exchange=exchange,
                    symbol=config.symbol,
                    timeframe=config.timeframe,
                    interval_minutes=config.llm_cache_minutes,
                )
                llm_scheduler.start()
                logging.info("LLM pattern analysis scheduler started")
        except ImportError as e:
            logging.warning(f"LLM strategy not available: {e}")
        except Exception as e:
            logging.error(f"Failed to initialize LLM strategy: {e}", exc_info=True)
        
        # Create strategy manager with all strategies
        aggregation_mode_map = {
            "voting": SignalAggregationMode.VOTING,
            "weighted_voting": SignalAggregationMode.WEIGHTED_VOTING,
            "unanimous": SignalAggregationMode.UNANIMOUS,
            "any": SignalAggregationMode.ANY,
            "best": SignalAggregationMode.BEST,
        }
        aggregation_mode = aggregation_mode_map.get(
            config.strategy_aggregation_mode,
            SignalAggregationMode.WEIGHTED_VOTING
        )
        
        strategy_manager = StrategyManager(
            strategies=strategies,
            aggregation_mode=aggregation_mode,
            min_confidence=config.min_signal_confidence,
        )
        
        enabled_count = len([s for s in strategies if s.is_enabled()])
        logging.info(
            f"Multi-strategy system initialized: {enabled_count}/{len(strategies)} strategies enabled, "
            f"aggregation mode: {aggregation_mode.value}"
        )
        
        if enabled_count == 0:
            logging.warning("⚠️ No strategies are currently enabled! Enable at least one in the dashboard.")
    else:
        logging.warning("\u26a0\ufe0f No strategies enabled. Enable at least one in the dashboard.")
    
    # Create trader lock before starting app
    trader_lock = threading.Lock()

    # Build the Flask app, wire the service layer, start the server thread.
    # init_services() also seeds ApplicationState so the new /app/api/*
    # blueprint routes return live data immediately.
    flask_app = create_app()
    app_state = init_services(trader, trader_lock, exchange, strategy_manager, config)
    start_app(flask_app, config.dashboard_host, config.dashboard_port)

    logging.info("Application started — dashboard + service layer ready")
    if strategy_manager:
        logging.info("Multi-strategy integration enabled")
    
    stop_event = threading.Event()

    def stop_handler(*_):
        logging.info("Received shutdown signal.")
        stop_event.set()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    logging.info(
        "Starting websocket stream (symbol=%s timeframe=%s)",
        config.symbol,
        config.timeframe,
    )

    binance_symbol = config.symbol.replace("/", "").upper()

    # Mutable holder so the watchdog can swap in a fresh WebSocketApp on reconnect.
    ws_holder: dict = {"ws": None, "thread": None}

    def _start_ws() -> None:
        old_wsa = ws_holder["ws"]
        if old_wsa is not None:
            try:
                old_wsa.close()
            except Exception:
                pass
        old_thread = ws_holder["thread"]
        if old_thread is not None and old_thread.is_alive():
            old_thread.join(timeout=5.0)

        url = (
            f"wss://stream.binance.us:9443/ws/"
            f"{binance_symbol.lower()}@kline_{config.timeframe}"
        )

        def on_message(ws, raw):
            try:
                handle_kline(json.loads(raw))
            except Exception as exc:
                logging.error("WS on_message error: %s", exc)

        def on_error(ws, error):
            logging.error("WebSocket error: %s", error)
            ws_activity["last_mono"] = 0  # force stale detection

        def on_close(ws, code, msg):
            logging.warning("WebSocket closed: %s %s", code, msg)

        def on_open(ws):
            ws_activity["last_mono"] = time.monotonic()
            ws_activity["stale_alerted"] = False
            logging.info("WebSocket stream started for %s / %s", config.symbol, config.timeframe)

        wsa = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )
        ws_holder["ws"] = wsa

        t = threading.Thread(
            target=wsa.run_forever,
            kwargs={"ping_interval": 30, "ping_timeout": 10},
            name="ws-kline",
            daemon=True,
        )
        t.start()
        ws_holder["thread"] = t

    candle_buffer = []
    max_buffer_size = max(config.long_window * 2, 120)
    
    # Pre-load initial candles to start trading immediately
    try:
        logging.info("Fetching initial candle history...")
        initial_candles = exchange.fetch_ohlcv(
            config.symbol, config.timeframe, limit=500
        )
        candle_buffer = initial_candles
        logging.info("Loaded %d initial candles", len(candle_buffer))
        
        # Compute initial signal and populate dashboard with historical data
        if len(candle_buffer) >= config.long_window:
            try:
                # Populate ApplicationState history so chart has data on first load.
                for candle in candle_buffer[-500:]:
                    ts = datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc).isoformat()
                    ohlc = {
                        "open": float(candle[1]),
                        "high": float(candle[2]),
                        "low": float(candle[3]),
                        "close": float(candle[4]),
                    }
                    app_state.add_history_record({
                        "timestamp": ts,
                        "price": float(candle[4]),
                        "signal_direction": "neutral",
                        "trade_side": None,
                        **ohlc,
                    })
                
                # Compute and display initial signal
                if strategy_manager:
                    initial_signal = strategy_manager.compute_aggregate_signal(
                        exchange,
                        config.symbol,
                        config.timeframe,
                        candle_data=candle_buffer,
                    )
                    balances = trader.get_balances()
                    app_state.update_trading_state(
                        usdt_balance=balances.get("USDT", 0.0),
                        base_balance=balances.get("BASE", 0.0),
                        current_price=initial_signal.price,
                    )
                    logging.info(
                        "Initial signal computed: %s at price %.2f (populated %d historical candles)",
                        initial_signal.direction,
                        initial_signal.price,
                        min(100, len(candle_buffer)),
                    )
            except Exception as e:
                logging.warning("Failed to compute initial signal: %s", e)
    except Exception as e:
        logging.warning("Failed to fetch initial candles: %s. Will buffer from stream.", e)

    # Seed historical candle data in background (30 days → SQLite)
    if SEED_HISTORY_AVAILABLE and DATABASE_AVAILABLE:
        try:
            from database import get_database
            _seed_db = get_database()
            if _seed_db is not None:
                def _do_seed():
                    try:
                        seed_candle_history(exchange, _seed_db, config.symbol, config.timeframe, days_back=30)
                    except Exception as _e:
                        logging.warning("Candle history seed failed: %s", _e)
                threading.Thread(target=_do_seed, name="candle-seeder", daemon=True).start()
                logging.info("Candle history seeder started in background")
        except Exception as e:
            logging.warning("Could not start candle seeder: %s", e)

    # Last monotonic time we saw a kline for our symbol (partial counts).
    ws_activity = {"last_mono": time.monotonic(), "stale_alerted": False}

    def handle_kline(msg: dict) -> None:
        nonlocal candle_buffer
        if msg.get("e") == "error":
            logging.error("WebSocket error message: %s", msg.get("m", msg))
            ws_activity["last_mono"] = 0  # force stale detection immediately
            return
        if msg.get("e") != "kline":
            return
        kline = msg.get("k", {})
        started_at = datetime.utcfromtimestamp(int(kline.get("t", 0)) / 1000)
        ended_at = datetime.utcfromtimestamp(int(kline.get("T", 0)) / 1000)
        # In-progress klines arrive every few seconds and dominate the log
        # volume. Only emit INFO when a candle closes; the partial updates
        # remain available at DEBUG level for troubleshooting.
        is_closed = bool(kline.get("x"))
        log_level = logging.INFO if is_closed else logging.DEBUG
        logging.log(
            log_level,
            "Kline %s %s-%s open=%.2f high=%.2f low=%.2f close=%.2f volume=%.2f closed=%s",
            config.symbol,
            started_at.isoformat(),
            ended_at.isoformat(),
            float(kline.get("o", 0.0)),
            float(kline.get("h", 0.0)),
            float(kline.get("l", 0.0)),
            float(kline.get("c", 0.0)),
            float(kline.get("v", 0.0)),
            is_closed,
        )
        if kline.get("s") != binance_symbol:
            return

        ws_activity["last_mono"] = time.monotonic()
        ws_activity["stale_alerted"] = False
        
        # Store closed candles in buffer
        if kline.get("x"):  # Candle is closed
            candle_data = [
                int(kline.get("t", 0)),  # timestamp
                float(kline.get("o", 0.0)),  # open
                float(kline.get("h", 0.0)),  # high
                float(kline.get("l", 0.0)),  # low
                float(kline.get("c", 0.0)),  # close
                float(kline.get("v", 0.0)),  # volume
            ]
            candle_buffer.append(candle_data)
            
            # Keep buffer at max size
            if len(candle_buffer) > max_buffer_size:
                candle_buffer.pop(0)
            
            # Skip signal computation until we have enough candles
            if len(candle_buffer) < config.long_window:
                logging.info(
                    "Buffering candles: %d/%d",
                    len(candle_buffer),
                    config.long_window,
                )
                return

        if not kline.get("x"):
            return

        try:
            with trader_lock:
                # Get current price for position updates
                current_price = float(kline.get("c", 0.0))
                
                # Check if open position should be closed (stop loss, take profit, trailing stop)
                exit_trade = trader.update_position(current_price)
                if exit_trade:
                    logging.info(
                        "Position closed: %s | Reason: %s | P&L: $%.2f",
                        exit_trade.side,
                        exit_trade.exit_reason,
                        exit_trade.pnl or 0.0,
                    )
                
                if strategy_manager is None:
                    logging.debug("No strategy manager configured; skipping signal computation.")
                    return
                signal_obj = strategy_manager.compute_aggregate_signal(
                    exchange,
                    config.symbol,
                    config.timeframe,
                    candle_data=candle_buffer,
                )
                trade = trader.handle_signal(signal_obj)

                balances = trader.get_balances()
                ohlc = {
                    "open": float(kline.get("o", 0.0)),
                    "high": float(kline.get("h", 0.0)),
                    "low": float(kline.get("l", 0.0)),
                    "close": float(kline.get("c", 0.0)),
                }

                pos = trader.open_position
                app_state.update_trading_state(
                    usdt_balance=balances.get("USDT", 0.0),
                    base_balance=balances.get("BASE", 0.0),
                    current_price=signal_obj.price,
                    position_open=pos is not None,
                    position_entry_price=pos.entry_price if pos else 0.0,
                    position_amount=pos.amount if pos else 0.0,
                    position_side="long" if pos else "none",
                    stop_loss=pos.stop_loss if pos else 0.0,
                    take_profit=pos.take_profit if pos else 0.0,
                    trailing_stop=pos.trailing_stop if pos else 0.0,
                )
                app_state.add_history_record({
                    "timestamp": signal_obj.timestamp.isoformat(),
                    "price": signal_obj.price,
                    "signal_direction": signal_obj.direction,
                    "trade_side": trade.side if trade else None,
                    **ohlc,
                })

            # Log signal with strategy info
            if strategy_manager and hasattr(signal_obj, 'info') and 'strategies_used' in signal_obj.info:
                strategies_str = "+".join(signal_obj.info['strategies_used'])
                logging.info(
                    "Signal=%s [%s] conf=%.2f price=%.2f PosSize=%.1f%% SL=%.2f TP=%.2f",
                    signal_obj.direction,
                    strategies_str,
                    signal_obj.confidence if hasattr(signal_obj, 'confidence') else 0.0,
                    signal_obj.price,
                    signal_obj.position_size * 100,
                    signal_obj.stop_loss,
                    signal_obj.take_profit,
                )
            elif hasattr(signal_obj, 'short_ema'):
                # Legacy logging for single strategy
                logging.info(
                    "Signal=%s price=%.2f short=%.2f long=%.2f trend=%.4f ATR=%.2f PosSize=%.1f%% SL=%.2f TP=%.2f",
                    signal_obj.direction,
                    signal_obj.price,
                    signal_obj.short_ema,
                    signal_obj.long_ema,
                    signal_obj.trend_strength,
                    signal_obj.atr if hasattr(signal_obj, 'atr') else 0.0,
                    signal_obj.position_size * 100,
                    signal_obj.stop_loss,
                    signal_obj.take_profit,
                )
            else:
                # Minimal logging
                logging.info(
                    "Signal=%s [%s] conf=%.2f price=%.2f",
                    signal_obj.direction,
                    signal_obj.strategy_name if hasattr(signal_obj, 'strategy_name') else 'unknown',
                    signal_obj.confidence if hasattr(signal_obj, 'confidence') else 0.0,
                    signal_obj.price,
                )
        except Exception as exc:
            logging.exception("websocket cycle failed: %s", exc)

    def _ws_watchdog_loop() -> None:
        threshold = float(getattr(config, "ws_stale_alert_seconds", 180.0))
        poll = max(5.0, min(60.0, threshold / 4.0))
        reconnect_attempts = 0

        while not stop_event.wait(poll):
            if not getattr(config, "ws_watchdog_enabled", True):
                continue
            age = time.monotonic() - ws_activity["last_mono"]
            if age < threshold:
                ws_activity["stale_alerted"] = False
                reconnect_attempts = 0
                continue

            # Alert once when the stream first goes stale.
            if not ws_activity["stale_alerted"]:
                ws_activity["stale_alerted"] = True
                body = (
                    f"No kline for {config.symbol} / {config.timeframe} in {age:.0f}s "
                    f"(threshold {threshold:.0f}s). Attempting reconnect..."
                )
                logging.error("WebSocket watchdog: %s", body)
                send_notification(
                    "Trading bot: kline stream stale",
                    body,
                    severity="critical",
                )

            # Exponential backoff: 10s, 20s, 40s, 80s … capped at 5 min.
            backoff = min(300.0, 10.0 * (2 ** reconnect_attempts))
            reconnect_attempts += 1
            logging.warning(
                "WebSocket reconnect attempt #%d (waiting %.0fs)",
                reconnect_attempts,
                backoff,
            )
            if stop_event.wait(backoff):
                break

            try:
                _start_ws()
                logging.info(
                    "WebSocket reconnected successfully on attempt #%d",
                    reconnect_attempts,
                )
                reconnect_attempts = 0
            except Exception as exc:
                logging.error("WebSocket reconnect failed: %s", exc)

    watchdog_thread = threading.Thread(
        target=_ws_watchdog_loop,
        name="ws-watchdog",
        daemon=True,
    )
    watchdog_thread.start()

    _start_ws()

    try:
        stop_event.wait()
    finally:
        logging.info("Shutting down websocket stream.")
        if ws_holder["ws"]:
            ws_holder["ws"].close()
        
        # Stop LLM scheduler if running
        if 'llm_scheduler' in locals() and llm_scheduler:
            logging.info("Stopping LLM scheduler...")
            llm_scheduler.stop()
        
        logging.info("Trading loop terminated.")


if __name__ == "__main__":
    main()