import logging
import signal
import threading
from datetime import datetime, timezone

import ccxt
from binance import ThreadedWebsocketManager

from config import BotConfig
from dashboard import start_dashboard, update_state, set_trader
from paper_trader import PaperTrader

# Import LiveTrader for real money trading
try:
    from live_trader import LiveTrader, TradingMode
    LIVE_TRADER_AVAILABLE = True
except ImportError:
    LIVE_TRADER_AVAILABLE = False
    logging.warning("LiveTrader module not available. Only paper trading supported.")

# Import strategies (with fallback to legacy single strategy)
try:
    from strategies import (
        EMACrossoverStrategy,
        RSIBollingerBandsStrategy,
        MACDVolumeStrategy,
        StrategyManager,
        SignalAggregationMode,
    )
    MULTI_STRATEGY_AVAILABLE = True
except ImportError:
    MULTI_STRATEGY_AVAILABLE = False
    from strategy import compute_signal
    logging.warning("Multi-strategy system not available. Using legacy single strategy.")

try:
    from database import initialize_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    logging.warning("Database module not available. Install SQLAlchemy to enable database features.")


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
    config = BotConfig.load()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

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
    if config.use_multi_strategy and MULTI_STRATEGY_AVAILABLE:
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
            from strategies.llm_pattern_strategy import LLMPatternStrategy
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
                    interval_minutes=config.llm_cache_minutes
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
        if not config.use_multi_strategy:
            logging.info("Multi-strategy disabled in config. Using legacy single strategy.")
        else:
            logging.warning("Multi-strategy not available. Using legacy single strategy.")
    
    # Create trader lock before starting dashboard
    trader_lock = threading.Lock()
    
    # Start dashboard and enable manual trading
    start_dashboard(config.dashboard_host, config.dashboard_port)
    set_trader(trader, trader_lock, exchange, strategy_manager)
    logging.info("Manual trading enabled on dashboard")
    if strategy_manager:
        logging.info("Multi-strategy dashboard integration enabled")
    
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
    twm = ThreadedWebsocketManager(
        api_key=config.binance_api_key,
        api_secret=config.binance_api_secret,
        tld="us",
    )
    twm.daemon = True  # Run as daemon thread
    
    # Try to start websocket manager with custom port to avoid conflict with dashboard (port 3010)
    # The websocket manager uses a local server, so we need to ensure it doesn't conflict
    try:
        twm.start()
    except OSError as e:
        if "Address already in use" in str(e):
            logging.warning("Default websocket port in use, this is expected if dashboard is on same port")
            # The websocket will still work, it just won't be able to start its local server
        else:
            raise
    
    # Buffer to store candles from websocket (avoids fetch_ohlcv calls)
    candle_buffer = []
    max_buffer_size = max(config.long_window * 2, 120)
    
    # Pre-load initial candles to start trading immediately
    try:
        logging.info("Fetching initial candle history...")
        initial_candles = exchange.fetch_ohlcv(
            config.symbol, config.timeframe, limit=max_buffer_size
        )
        candle_buffer = initial_candles
        logging.info("Loaded %d initial candles", len(candle_buffer))
        
        # Compute initial signal and populate dashboard with historical data
        if len(candle_buffer) >= config.long_window:
            try:
                # Populate dashboard history with recent candles (last 100 for chart)
                from dashboard import _record_history
                for candle in candle_buffer[-100:]:
                    _record_history(
                        timestamp=datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc).isoformat(),
                        price=float(candle[4]),  # close price
                        signal_direction="neutral",
                        trade_side=None,
                        ohlc={
                            "open": float(candle[1]),
                            "high": float(candle[2]),
                            "low": float(candle[3]),
                            "close": float(candle[4]),
                        },
                    )
                
                # Compute and display initial signal
                if strategy_manager:
                    initial_signal = strategy_manager.compute_aggregate_signal(
                        exchange,
                        config.symbol,
                        config.timeframe,
                        candle_data=candle_buffer,
                    )
                else:
                    initial_signal = compute_signal(
                        exchange,
                        config.symbol,
                        config.timeframe,
                        short_window=config.short_window,
                        long_window=config.long_window,
                        candle_data=candle_buffer,
                        min_trend_strength=config.min_trend_strength,
                        rsi_period=config.rsi_period,
                        rsi_oversold=config.rsi_oversold,
                        rsi_overbought=config.rsi_overbought,
                        atr_period=config.atr_period,
                        atr_stop_multiplier=config.atr_stop_multiplier,
                        use_atr_stops=config.use_atr_stops,
                        stop_loss_pct=config.stop_loss_pct,
                        take_profit_pct=config.take_profit_pct,
                        macd_fast=config.macd_fast,
                        macd_slow=config.macd_slow,
                        macd_signal=config.macd_signal,
                        require_macd_confirmation=config.require_macd_confirmation,
                        require_volume_confirmation=config.require_volume_confirmation,
                        volume_threshold=config.volume_threshold,
                        use_dynamic_sizing=config.use_dynamic_sizing,
                        min_position_size=config.min_position_size,
                        max_position_size=config.max_position_size,
                    )
                update_state(
                    balances=trader.get_balances(),
                    last_signal=initial_signal.to_dict(),
                    last_trade=None,
                    price=initial_signal.price,
                    signal_direction=initial_signal.direction,
                    timestamp=initial_signal.timestamp.isoformat(),
                    trade_side=None,
                    ohlc={
                        "open": candle_buffer[-1][1],
                        "high": candle_buffer[-1][2],
                        "low": candle_buffer[-1][3],
                        "close": candle_buffer[-1][4],
                    },
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

    def handle_kline(msg: dict) -> None:
        nonlocal candle_buffer
        if msg.get("e") != "kline":
            return
        kline = msg.get("k", {})
        started_at = datetime.utcfromtimestamp(int(kline.get("t", 0)) / 1000)
        ended_at = datetime.utcfromtimestamp(int(kline.get("T", 0)) / 1000)
        logging.info(
            "Kline %s %s-%s open=%.2f high=%.2f low=%.2f close=%.2f volume=%.2f closed=%s",
            config.symbol,
            started_at.isoformat(),
            ended_at.isoformat(),
            float(kline.get("o", 0.0)),
            float(kline.get("h", 0.0)),
            float(kline.get("l", 0.0)),
            float(kline.get("c", 0.0)),
            float(kline.get("v", 0.0)),
            kline.get("x"),
        )
        if kline.get("s") != binance_symbol:
            return
        
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
                
                if strategy_manager:
                    signal_obj = strategy_manager.compute_aggregate_signal(
                        exchange,
                        config.symbol,
                        config.timeframe,
                        candle_data=candle_buffer,
                    )
                else:
                    signal_obj = compute_signal(
                        exchange,
                        config.symbol,
                        config.timeframe,
                        short_window=config.short_window,
                        long_window=config.long_window,
                        candle_data=candle_buffer,
                        min_trend_strength=config.min_trend_strength,
                        rsi_period=config.rsi_period,
                        rsi_oversold=config.rsi_oversold,
                        rsi_overbought=config.rsi_overbought,
                        atr_period=config.atr_period,
                        atr_stop_multiplier=config.atr_stop_multiplier,
                        use_atr_stops=config.use_atr_stops,
                        stop_loss_pct=config.stop_loss_pct,
                        take_profit_pct=config.take_profit_pct,
                        macd_fast=config.macd_fast,
                        macd_slow=config.macd_slow,
                        macd_signal=config.macd_signal,
                        require_macd_confirmation=config.require_macd_confirmation,
                        require_volume_confirmation=config.require_volume_confirmation,
                        volume_threshold=config.volume_threshold,
                        use_dynamic_sizing=config.use_dynamic_sizing,
                        min_position_size=config.min_position_size,
                        max_position_size=config.max_position_size,
                    )
                trade = trader.handle_signal(signal_obj)
                update_state(
                    balances=trader.get_balances(),
                    last_signal=signal_obj.to_dict(),
                    last_trade=trade.to_dict() if trade else None,
                    price=signal_obj.price,
                    signal_direction=signal_obj.direction,
                    timestamp=signal_obj.timestamp.isoformat(),
                trade_side=trade.side if trade else None,
                ohlc={
                    "open": float(kline.get("o", 0.0)),
                    "high": float(kline.get("h", 0.0)),
                    "low": float(kline.get("l", 0.0)),
                    "close": float(kline.get("c", 0.0)),
                },
                )

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

    twm.start_kline_socket(
        callback=handle_kline,
        symbol=binance_symbol,
        interval=config.timeframe,
    )

    try:
        stop_event.wait()
    finally:
        logging.info("Shutting down websocket stream.")
        twm.stop()
        
        # Stop LLM scheduler if running
        if 'llm_scheduler' in locals() and llm_scheduler:
            logging.info("Stopping LLM scheduler...")
            llm_scheduler.stop()
        
        logging.info("Trading loop terminated.")


if __name__ == "__main__":
    main()