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
        StrategyManager,
        SignalAggregationMode,
    )
    MULTI_STRATEGY_AVAILABLE = True
except ImportError:
    MULTI_STRATEGY_AVAILABLE = False
    from strategy import compute_signal
    logging.warning("Multi-strategy system not available. Using legacy single strategy for backtest.")

try:
    from database import initialize_database
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


def run_backtest(days_back: int = 30, use_database: bool = False, config_overrides: dict = None):
    """
    Run accelerated backtest on historical data with multi-strategy support.
    
    Args:
        days_back: Number of days of historical data to backtest
        use_database: Whether to store results in database
        config_overrides: Optional dict of config parameters to override (for presets/testing)
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    
    # Initialize main trading database for reading configuration
    # (This is separate from the backtest results database)
    if DATABASE_AVAILABLE:
        try:
            from database import initialize_database as init_db
            init_db("sqlite:///data/trading.db")
            logging.info("✓ Trading database initialized for config reading")
        except Exception as e:
            logging.warning(f"Could not initialize trading database: {e}")
            logging.warning("Using .env configuration instead")
    
    config = BotConfig.load()
    
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
    
    # Initialize strategy system
    strategy_manager = None
    if config.use_multi_strategy and MULTI_STRATEGY_AVAILABLE:
        logging.info("=" * 80)
        logging.info("MULTI-STRATEGY BACKTEST MODE")
        logging.info("=" * 80)
        
        # Create strategies
        strategies = []
        strategy_configs = config.get_strategy_configs()
        
        # EMA Crossover Strategy
        if strategy_configs["ema_crossover"]["enabled"]:
            ema_strategy = EMACrossoverStrategy(strategy_configs["ema_crossover"])
            strategies.append(ema_strategy)
            logging.info(f"✓ Enabled: {ema_strategy.name} (weight: {ema_strategy.get_weight()})")
        
        # RSI + Bollinger Bands Strategy
        if strategy_configs["rsi_bb"]["enabled"]:
            rsi_bb_strategy = RSIBollingerBandsStrategy(strategy_configs["rsi_bb"])
            strategies.append(rsi_bb_strategy)
            logging.info(f"✓ Enabled: {rsi_bb_strategy.name} (weight: {rsi_bb_strategy.get_weight()})")
        
        # MACD + Volume Momentum Strategy
        if strategy_configs.get("macd_volume", {}).get("enabled", True):
            macd_strategy = MACDVolumeStrategy(strategy_configs.get("macd_volume", {}))
            strategies.append(macd_strategy)
            logging.info(f"✓ Enabled: {macd_strategy.name} (weight: {macd_strategy.get_weight()})")
        
        if strategies:
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
    
    # Fetch historical data
    logging.info(f"Fetching {days_back} days of {config.timeframe} candles for {config.symbol}...")
    since = exchange.parse8601(
        (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
    )
    all_candles = exchange.fetch_ohlcv(
        config.symbol, 
        config.timeframe, 
        since=since,
        limit=1000
    )
    
    logging.info(f"Loaded {len(all_candles)} candles. Starting backtest...")
    logging.info(f"Strategy: EMA {config.short_window}/{config.long_window} on {config.timeframe} timeframe")
    logging.info(f"Order size: {config.order_pct * 100}% per trade")
    logging.info("-" * 80)
    
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
            # Record exit trade marker
            chart_data["trades"].append({
                "timestamp": candle_timestamp.isoformat() + "Z",
                "side": exit_trade.side,
                "price": exit_trade.price,
                "amount": exit_trade.amount,
                "reason": exit_trade.exit_reason,
                "pnl": exit_trade.pnl,
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
            
            # Record entry trade marker
            chart_data["trades"].append({
                "timestamp": candle_time.isoformat() + "Z",
                "side": trade.side,
                "price": trade.price,
                "amount": trade.amount,
                "reason": "signal",
                "pnl": None,
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
            chart_data["trades"].append({
                "timestamp": final_timestamp.isoformat() + "Z",
                "side": final_exit.side,
                "price": final_exit.price,
                "reason": final_exit.exit_reason,
                "pnl": final_exit.pnl,
            })
    
    # Final results
    total_value = trader.usdt_balance + (trader.base_balance * final_price)
    pnl = total_value - config.initial_usdt
    pnl_pct = (pnl / config.initial_usdt) * 100
    
    # Calculate buy & hold comparison
    buy_hold_btc = config.initial_usdt / all_candles[config.long_window][4]
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

