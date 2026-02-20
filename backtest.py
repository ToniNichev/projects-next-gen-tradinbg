import logging
from datetime import datetime, timedelta
import ccxt
from config import BotConfig
from paper_trader import PaperTrader

# Import multi-strategy system with fallback to legacy
try:
    from strategies import (
        EMACrossoverStrategy,
        RSIBollingerBandsStrategy,
        MACDVolumeStrategy,
        LLMPatternStrategy,
        StrategyManager,
        SignalAggregationMode,
        LLM_AVAILABLE,
    )
    MULTI_STRATEGY_AVAILABLE = True
except ImportError:
    MULTI_STRATEGY_AVAILABLE = False
    LLM_AVAILABLE = False
    from strategy import compute_signal
    logging.warning("Multi-strategy system not available. Using legacy single strategy for backtest.")

try:
    from database import initialize_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


def run_backtest(days_back: int = 30, use_database: bool = False, config_overrides: dict = None, progress_callback=None):
    """
    Run accelerated backtest on historical data with multi-strategy support.
    
    Args:
        days_back: Number of days of historical data to backtest
        use_database: Whether to store results in database
        config_overrides: Optional dict of config parameters to override (for presets/testing)
        progress_callback: Optional callback function for progress updates (for UI)
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    
    # Initialize main trading database for reading configuration
    # (This is separate from the backtest results database)
    db_config_loaded = False
    if DATABASE_AVAILABLE:
        try:
            from database import initialize_database as init_db, get_database
            init_db("sqlite:///data/trading.db")
            
            # Verify database has configurations
            db = get_database()
            db_configs = db.get_all_strategy_configs()
            if db_configs:
                logging.info(f"✓ Trading database initialized with {len(db_configs)} config parameters")
                db_config_loaded = True
            else:
                logging.warning("⚠ Database has no configurations, using .env defaults")
        except Exception as e:
            logging.warning(f"Could not initialize trading database: {e}")
            logging.warning("Using .env configuration instead")
    
    config = BotConfig.load()
    
    # Log key configuration values for verification
    logging.info("=" * 80)
    logging.info("CONFIGURATION SOURCE: " + ("DATABASE" if db_config_loaded else "ENVIRONMENT"))
    logging.info("=" * 80)
    logging.info(f"  Stop Loss: {config.stop_loss_pct * 100:.1f}%")
    logging.info(f"  Take Profit: {config.take_profit_pct * 100:.1f}%")
    logging.info(f"  Position Size: {config.order_pct * 100:.0f}%")
    logging.info(f"  Aggregation Mode: {config.strategy_aggregation_mode}")
    logging.info(f"  Min Confidence: {config.min_signal_confidence * 100:.0f}%")
    logging.info(f"  EMA Strategy: {'Enabled' if config.strategy_ema_enabled else 'Disabled'} (weight: {config.strategy_ema_weight})")
    logging.info(f"  RSI+BB Strategy: {'Enabled' if config.strategy_rsi_bb_enabled else 'Disabled'} (weight: {config.strategy_rsi_bb_weight})")
    logging.info(f"  MACD Strategy: {'Enabled' if config.strategy_macd_enabled else 'Disabled'} (weight: {config.strategy_macd_weight})")
    logging.info("=" * 80)
    
    # Apply config overrides (for presets like conservative, balanced, aggressive)
    if config_overrides:
        logging.info("=" * 80)
        logging.info("APPLYING CONFIG OVERRIDES")
        logging.info("=" * 80)
        for key, value in config_overrides.items():
            if hasattr(config, key):
                old_value = getattr(config, key)
                setattr(config, key, value)
                logging.info(f"  {key}: {old_value} → {value}")
            else:
                logging.warning(f"  Unknown config key: {key}")
        logging.info("=" * 80)
    
    # Build exchange (read-only, no API keys needed for historical data)
    exchange = ccxt.binanceus({"enableRateLimit": True})
    
    # Get trading database manager for LLM strategy (reads trade history for pattern analysis)
    # This is separate from the backtest database (which stores backtest results)
    trading_db_manager = None
    if DATABASE_AVAILABLE:
        try:
            from database import get_database
            trading_db_manager = get_database()
        except Exception as e:
            logging.warning(f"Could not get trading database manager: {e}")
    
    # Initialize strategy system
    strategy_manager = None
    if config.use_multi_strategy and MULTI_STRATEGY_AVAILABLE:
        logging.info("=" * 80)
        logging.info("MULTI-STRATEGY BACKTEST MODE")
        logging.info("=" * 80)
        
        # Create ALL strategies (respecting their enabled state from config)
        strategies = []
        strategy_configs = config.get_strategy_configs()
        
        # EMA Crossover Strategy
        ema_strategy = EMACrossoverStrategy(strategy_configs["ema_crossover"])
        ema_strategy.set_enabled(strategy_configs["ema_crossover"]["enabled"])
        strategies.append(ema_strategy)
        status = "✓ Enabled" if ema_strategy.is_enabled() else "✗ Disabled"
        logging.info(f"{status}: {ema_strategy.name} (weight: {ema_strategy.get_weight()})")
        
        # RSI + Bollinger Bands Strategy
        rsi_bb_strategy = RSIBollingerBandsStrategy(strategy_configs["rsi_bb"])
        rsi_bb_strategy.set_enabled(strategy_configs["rsi_bb"]["enabled"])
        strategies.append(rsi_bb_strategy)
        status = "✓ Enabled" if rsi_bb_strategy.is_enabled() else "✗ Disabled"
        logging.info(f"{status}: {rsi_bb_strategy.name} (weight: {rsi_bb_strategy.get_weight()})")
        
        # MACD + Volume Momentum Strategy
        macd_config = strategy_configs.get("macd_volume", {})
        macd_strategy = MACDVolumeStrategy(macd_config)
        macd_strategy.set_enabled(macd_config.get("enabled", False))  # Default to False if missing
        strategies.append(macd_strategy)
        status = "✓ Enabled" if macd_strategy.is_enabled() else "✗ Disabled"
        logging.info(f"{status}: {macd_strategy.name} (weight: {macd_strategy.get_weight()})")
        
        # LLM Pattern Analysis Strategy (optional - requires Ollama and database)
        if LLM_AVAILABLE:
            try:
                llm_config = strategy_configs.get("llm_pattern", {})
                # Pass trading database manager to LLM strategy for trade history analysis
                # Also pass progress_callback for UI updates during backtesting
                llm_strategy = LLMPatternStrategy(llm_config, db_manager=trading_db_manager, progress_callback=progress_callback)
                llm_strategy.set_enabled(llm_config.get("enabled", False))
                strategies.append(llm_strategy)
                status = "✓ Enabled" if llm_strategy.is_enabled() else "✗ Disabled"
                logging.info(f"{status}: {llm_strategy.name} (weight: {llm_strategy.get_weight()})")
            except Exception as e:
                logging.warning(f"✗ LLM strategy unavailable: {e}")
        else:
            logging.info("✗ Disabled: LLM Pattern Analysis (not available)")
        
        # Check if at least one strategy is enabled
        enabled_strategies = [s for s in strategies if s.is_enabled()]
        if enabled_strategies:
            # Create strategy manager
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
            logging.info(f"Aggregation mode: {aggregation_mode.value}")
            logging.info(f"Min confidence: {config.min_signal_confidence * 100}%")
            logging.info("=" * 80)
        else:
            logging.warning("No strategies enabled! Falling back to legacy single strategy.")
            strategy_manager = None
    else:
        logging.info("Using legacy single strategy for backtest")
        strategy_manager = None
    
    # Initialize database if requested (use separate backtest database)
    db_manager = None
    if use_database and DATABASE_AVAILABLE:
        try:
            db_manager = initialize_database("sqlite:///data/backtest.db")
            logging.info("Using database for backtest results: data/backtest.db")
        except Exception as e:
            logging.error(f"Failed to initialize database: {e}")
            logging.warning("Continuing with CSV-only logging")
    
    # Initialize paper trader with separate log file for backtesting
    trader = PaperTrader(
        initial_usdt=config.initial_usdt,
        fee_rate=config.fee_rate,
        slippage=config.slippage,
        log_path="data/backtest_log.csv",
        use_trailing_stop=config.use_trailing_stop,
        trailing_stop_pct=config.trailing_stop_pct,
        db_manager=db_manager,
        enable_database=use_database,
        enable_csv_logging=True,
    )
    
    # Fetch historical data with pagination to respect the full time period
    logging.info(f"Fetching {days_back} days of {config.timeframe} candles for {config.symbol}...")
    since = exchange.parse8601(
        (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    )
    
    # Fetch candles in batches (exchange limit is typically 1000-1500 per request)
    all_candles = []
    batch_size = 1000
    current_since = since
    target_end_time = exchange.milliseconds()
    
    logging.info(f"Fetching candles in batches of {batch_size}...")
    batch_count = 0
    
    while current_since < target_end_time:
        try:
            batch = exchange.fetch_ohlcv(
                config.symbol,
                config.timeframe,
                since=current_since,
                limit=batch_size
            )
            
            if not batch:
                logging.info(f"No more candles available (reached current time)")
                break
            
            # Add candles to collection (avoid duplicates)
            if all_candles and batch[0][0] <= all_candles[-1][0]:
                # Skip candles we already have
                batch = [c for c in batch if c[0] > all_candles[-1][0]]
            
            all_candles.extend(batch)
            batch_count += 1
            
            # Update since to the timestamp of the last candle + 1ms
            current_since = batch[-1][0] + 1
            
            # Stop if we've reached the present or got fewer candles than requested
            if len(batch) < batch_size:
                logging.info(f"Received partial batch ({len(batch)} candles), reached end of data")
                break
            
            # Rate limiting: small delay between requests
            if batch_count % 5 == 0:
                logging.info(f"Fetched {len(all_candles)} candles so far ({batch_count} batches)...")
                import time
                time.sleep(0.5)  # Be nice to the exchange API
                
        except Exception as e:
            logging.warning(f"Error fetching batch: {e}")
            if len(all_candles) < batch_size:
                # If we don't even have one batch, this is a real error
                raise
            else:
                # We have some data, continue with what we got
                logging.info(f"Continuing with {len(all_candles)} candles fetched so far")
                break
    
    logging.info(f"✓ Loaded {len(all_candles)} candles across {batch_count} batch(es). Starting backtest...")
    
    # Show actual time period covered
    if all_candles:
        first_candle_time = datetime.utcfromtimestamp(all_candles[0][0] / 1000)
        last_candle_time = datetime.utcfromtimestamp(all_candles[-1][0] / 1000)
        actual_days = (last_candle_time - first_candle_time).total_seconds() / 86400
        logging.info(f"📅 Time period: {first_candle_time.strftime('%Y-%m-%d %H:%M')} to {last_candle_time.strftime('%Y-%m-%d %H:%M')} ({actual_days:.1f} days)")
    
    # Validate we have enough candles for the strategy
    min_required_candles = max(config.long_window + 1, 50)  # Need at least long_window + buffer, or 50 for indicators
    if len(all_candles) < min_required_candles:
        error_msg = (
            f"Not enough candles for backtest! Got {len(all_candles)}, need at least {min_required_candles}.\n"
            f"  - Long window requires: {config.long_window} candles\n"
            f"  - Technical indicators require: 50 candles\n"
            f"  - Current timeframe: {config.timeframe}\n"
            f"\nSolutions:\n"
            f"  1. Increase days: For {config.timeframe} timeframe, try --days 10 or more\n"
            f"  2. Use shorter timeframe: Try 1h instead of 4h\n"
            f"  3. Reduce long_window: Change from {config.long_window} to a smaller value"
        )
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    logging.info(f"Strategy: EMA {config.short_window}/{config.long_window} on {config.timeframe} timeframe")
    logging.info(f"Order size: {config.order_pct * 100}% per trade")
    logging.info("-" * 80)

    # Inform LLM strategy of the real total candle count so progress tracking is accurate
    if LLM_AVAILABLE and strategy_manager:
        for strategy in strategy_manager.strategies:
            if hasattr(strategy, "set_backtest_total_candles"):
                strategy.set_backtest_total_candles(len(all_candles))
    
    trade_count = 0
    
    # Chart data storage for visualization
    chart_data = {
        "candles": [],  # OHLC data with timestamps
        "portfolio_values": [],  # Portfolio value at each timestamp
        "trades": [],  # Trade markers (entry/exit points)
    }
    
    # Process each candle (simulating closed candles)
    for i in range(config.long_window, len(all_candles)):
        current_candle = all_candles[i]
        current_price = current_candle[4]  # Close price
        candle_timestamp = datetime.utcfromtimestamp(current_candle[0] / 1000)
        
        # Record candle data for chart
        chart_data["candles"].append({
            "timestamp": candle_timestamp.isoformat() + "Z",
            "open": current_candle[1],
            "high": current_candle[2],
            "low": current_candle[3],
            "close": current_candle[4],
            "volume": current_candle[5],
        })
        
        # Check for position exits (stop loss, take profit, trailing stop)
        exit_trade = trader.update_position(current_price)
        if exit_trade:
            trade_count += 1
            # Get strategy name from the exit trade signal (populated from position)
            exit_strategy_name = exit_trade.signal.get("strategy_name") if exit_trade.signal else None
            
            # Record exit trade marker with complete details for HUD
            chart_data["trades"].append({
                "timestamp": candle_timestamp.isoformat() + "Z",
                "side": exit_trade.side,
                "price": exit_trade.price,
                "amount": exit_trade.amount,
                "notional": exit_trade.notional,
                "fee": exit_trade.fee,
                "usdt_balance": exit_trade.usdt_balance,
                "base_balance": exit_trade.base_balance,
                "reason": exit_trade.exit_reason,
                "exit_reason": exit_trade.exit_reason,
                "pnl": exit_trade.pnl,
                "strategy_name": exit_strategy_name,  # Now includes strategy from position
                "confidence": None,
                "rsi": None,
                "atr": None,
                "signal_direction": exit_strategy_name,  # For dashboard compatibility
            })
        
        # Get window of candles for signal computation
        candle_window = all_candles[max(0, i - config.long_window * 2):i + 1]
        
        # Compute signal (multi-strategy or legacy)
        if strategy_manager:
            signal = strategy_manager.compute_aggregate_signal(
                exchange,
                config.symbol,
                config.timeframe,
                candle_data=candle_window,
            )
        else:
            signal = compute_signal(
                exchange,
                config.symbol,
                config.timeframe,
                short_window=config.short_window,
                long_window=config.long_window,
                candle_data=candle_window,
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
        
        # Execute trade if signal triggers (uses dynamic position sizing)
        trade = trader.handle_signal(signal)
        
        if trade:
            trade_count += 1
            candle_time = datetime.utcfromtimestamp(all_candles[i][0] / 1000)
            current_price = all_candles[i][4]
            portfolio_value = trader.usdt_balance + (trader.base_balance * current_price)
            
            # Extract strategy info from signal
            strategy_name = trade.signal.get("strategy_name", "Unknown")
            confidence = trade.signal.get("confidence", 0.0)
            
            # Get technical indicators from signal
            indicators = trade.signal.get("indicators", {})
            rsi = indicators.get("rsi")
            atr = indicators.get("atr")
            
            # Record entry trade marker with complete details for HUD
            chart_data["trades"].append({
                "timestamp": candle_time.isoformat() + "Z",
                "side": trade.side,
                "price": trade.price,
                "amount": trade.amount,
                "notional": trade.notional,
                "fee": trade.fee,
                "usdt_balance": trade.usdt_balance,
                "base_balance": trade.base_balance,
                "reason": "signal",
                "exit_reason": None,
                "pnl": None,
                "strategy_name": strategy_name,
                "confidence": confidence,
                "rsi": rsi,
                "atr": atr,
                "signal_direction": strategy_name,  # For dashboard compatibility
            })
            
            logging.info(
                f"[{candle_time}] Trade #{trade_count}: {trade.side.upper()} "
                f"{trade.amount:.6f} @ ${trade.price:.2f} | "
                f"Portfolio: ${portfolio_value:.2f} "
                f"(${trader.usdt_balance:.2f} + {trader.base_balance:.6f} BTC)"
            )
        
        # Calculate and record portfolio value AFTER all trades on this candle
        portfolio_value = trader.usdt_balance + (trader.base_balance * current_price)
        chart_data["portfolio_values"].append({
            "timestamp": candle_timestamp.isoformat() + "Z",
            "value": portfolio_value,
        })
    
    # Close any remaining open position at final price
    final_price = all_candles[-1][4]  # Last close price
    if trader.open_position:
        final_exit = trader._close_position(final_price, "backtest_end")
        if final_exit:
            trade_count += 1
            final_timestamp = datetime.utcfromtimestamp(all_candles[-1][0] / 1000)
            
            # Get strategy name from the exit trade signal (populated from position)
            final_strategy_name = final_exit.signal.get("strategy_name") if final_exit.signal else None
            
            chart_data["trades"].append({
                "timestamp": final_timestamp.isoformat() + "Z",
                "side": final_exit.side,
                "price": final_exit.price,
                "amount": final_exit.amount,
                "notional": final_exit.notional,
                "fee": final_exit.fee,
                "usdt_balance": final_exit.usdt_balance,
                "base_balance": final_exit.base_balance,
                "reason": final_exit.exit_reason,
                "exit_reason": final_exit.exit_reason,
                "pnl": final_exit.pnl,
                "strategy_name": final_strategy_name,  # Now includes strategy from position
                "confidence": None,
                "rsi": None,
                "atr": None,
                "signal_direction": final_strategy_name,  # For dashboard compatibility
            })
    
    # Final results
    total_value = trader.usdt_balance + (trader.base_balance * final_price)
    pnl = total_value - config.initial_usdt
    pnl_pct = (pnl / config.initial_usdt) * 100
    
    # Calculate buy & hold comparison (use first tradeable candle, not arbitrary index)
    # Start from config.long_window or first available candle, whichever is smaller
    buy_hold_start_idx = min(config.long_window, len(all_candles) - 1)
    buy_hold_btc = config.initial_usdt / all_candles[buy_hold_start_idx][4]
    buy_hold_value = buy_hold_btc * final_price
    buy_hold_pnl = buy_hold_value - config.initial_usdt
    buy_hold_pct = (buy_hold_pnl / config.initial_usdt) * 100
    
    # Advanced metrics
    win_rate = (trader.winning_trades / trader.total_trades * 100) if trader.total_trades > 0 else 0
    avg_pnl_per_trade = trader.total_pnl / trader.total_trades if trader.total_trades > 0 else 0
    
    logging.info("\n" + "=" * 80)
    if strategy_manager:
        logging.info("BACKTEST RESULTS - MULTI-STRATEGY WITH RISK MANAGEMENT")
    else:
        logging.info("BACKTEST RESULTS - SINGLE STRATEGY WITH RISK MANAGEMENT")
    logging.info("=" * 80)
    logging.info(f"Period: {days_back} days | Candles processed: {len(all_candles)}")
    if strategy_manager:
        enabled_strategies = [s.name for s in strategy_manager.strategies if s.is_enabled()]
        logging.info(f"Strategies: {', '.join(enabled_strategies)}")
        logging.info(f"Aggregation: {config.strategy_aggregation_mode}")
    else:
        logging.info(f"Strategy: EMA {config.short_window}/{config.long_window} + MACD + ATR stops")
    logging.info("-" * 80)
    logging.info("PERFORMANCE METRICS")
    logging.info("-" * 80)
    logging.info(f"Total trades: {trade_count}")
    logging.info(f"Winning trades: {trader.winning_trades}")
    logging.info(f"Losing trades: {trader.total_trades - trader.winning_trades}")
    logging.info(f"Win rate: {win_rate:.1f}%")
    logging.info(f"Average P&L per trade: ${avg_pnl_per_trade:.2f}")
    logging.info("-" * 80)
    logging.info("CAPITAL & RETURNS")
    logging.info("-" * 80)
    logging.info(f"Initial Capital: ${config.initial_usdt:.2f}")
    logging.info(f"Final USDT: ${trader.usdt_balance:.2f}")
    logging.info(f"Final BTC: {trader.base_balance:.6f} (${trader.base_balance * final_price:.2f})")
    logging.info(f"Total Value: ${total_value:.2f}")
    logging.info(f"Total P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
    logging.info(f"Cumulative P&L from trades: ${trader.total_pnl:.2f}")
    logging.info("-" * 80)
    logging.info("COMPARISON")
    logging.info("-" * 80)
    logging.info(f"Buy & Hold P&L: ${buy_hold_pnl:.2f} ({buy_hold_pct:+.2f}%)")
    logging.info(f"Strategy vs Buy & Hold: {pnl_pct - buy_hold_pct:+.2f}%")
    logging.info("-" * 80)
    logging.info("RISK MANAGEMENT FEATURES")
    logging.info("-" * 80)
    logging.info(f"ATR-based stops: {'Enabled' if config.use_atr_stops else 'Disabled'}")
    logging.info(f"Trailing stops: {'Enabled' if config.use_trailing_stop else 'Disabled'}")
    logging.info(f"Dynamic position sizing: {'Enabled' if config.use_dynamic_sizing else 'Disabled'}")
    logging.info(f"MACD confirmation: {'Required' if config.require_macd_confirmation else 'Optional'}")
    logging.info(f"Volume confirmation: {'Required' if config.require_volume_confirmation else 'Optional'}")
    logging.info("-" * 80)
    
    # Show strategy statistics if multi-strategy was used
    if strategy_manager:
        logging.info("STRATEGY PERFORMANCE")
        logging.info("-" * 80)
        stats = strategy_manager.get_strategy_stats()
        for strategy_name, strategy_stats in stats.items():
            logging.info(f"Strategy: {strategy_name}")
            logging.info(f"  Signals Generated: {strategy_stats['signals_generated']}")
            logging.info(f"  Signals Used: {strategy_stats['signals_used']}")
            logging.info(f"  Avg Confidence: {strategy_stats['avg_confidence']:.2%}")
            if strategy_stats['signals_generated'] > 0:
                acceptance = strategy_stats['signals_used'] / strategy_stats['signals_generated'] * 100
                logging.info(f"  Acceptance Rate: {acceptance:.1f}%")
            logging.info("")
        logging.info("-" * 80)
    
    logging.info(f"Trade log saved to: {trader.log_path}")
    logging.info("=" * 80)
    
    # Limit chart data to last 2000 candles to show more context with trades
    if len(chart_data["candles"]) > 2000:
        # Get the timestamp of the first candle we're keeping
        cutoff_timestamp = chart_data["candles"][-2000]["timestamp"]
        
        # Limit candles and portfolio values
        chart_data["candles"] = chart_data["candles"][-500:]
        chart_data["portfolio_values"] = chart_data["portfolio_values"][-500:]
        
        # Keep all trades for the chart (don't filter by time range)
        # All trades will be displayed regardless of candle limit
        # chart_data["trades"] remains unchanged
    
    return {
        "trades": trade_count,
        "final_value": total_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "buy_hold_pct": buy_hold_pct,
        "chart_data": chart_data,
    }


if __name__ == "__main__":
    import sys
    
    # Allow days_back to be passed as command line argument
    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print(f"Usage: python backtest.py [days_back]")
            print(f"Using default: {days} days")
    
    run_backtest(days_back=days)

