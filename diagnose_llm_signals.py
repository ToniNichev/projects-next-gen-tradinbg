#!/usr/bin/env python3
"""
LLM Signal Diagnostic Tool

This script traces through the entire LLM signal generation pipeline to identify
why trades aren't being executed in backtests.

It shows:
1. Market data being sent to LLM
2. Raw LLM response
3. Parsed signal (direction, confidence, position size)
4. Whether signal meets confidence threshold
5. How signal is filtered by strategy manager
6. Final trading decision

Usage:
    python diagnose_llm_signals.py [--symbol BTC/USDT] [--days 7]
"""

import argparse
import logging
import sys
import json
from datetime import datetime, timedelta

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)
logger = logging.getLogger(__name__)


def print_section(title):
    """Print a section header"""
    logger.info("\n" + "=" * 80)
    logger.info(title)
    logger.info("=" * 80)


def analyze_llm_signal_generation(symbol="BTC/USDT", days_back=7):
    """
    Trace through complete LLM signal generation process
    """
    try:
        import ccxt
        from config import BotConfig
        from strategies.llm.strategy import LLMPatternStrategy
        from strategies import StrategyManager, SignalAggregationMode
        
        print_section("STEP 1: Configuration")
        
        config = BotConfig.load()
        logger.info(f"Symbol: {symbol}")
        logger.info(f"Timeframe: {config.timeframe}")
        logger.info(f"Min Signal Confidence: {config.min_signal_confidence * 100:.1f}%")
        logger.info(f"Aggregation Mode: {config.strategy_aggregation_mode}")
        logger.info(f"LLM Model: {config.llm_ollama_model}")
        logger.info(f"LLM Timeout: {config.llm_timeout_seconds}s")
        logger.info(f"Stop Loss: {config.stop_loss_pct * 100:.1f}%")
        logger.info(f"Take Profit: {config.take_profit_pct * 100:.1f}%")
        logger.info(f"Position Size: {config.order_pct * 100:.0f}%")
        
        print_section("STEP 2: Fetch Historical Data")
        
        exchange = ccxt.binanceus({"enableRateLimit": True})
        
        # Fetch enough candles for analysis
        since = exchange.parse8601(
            (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT00:00:00Z")
        )
        candles = exchange.fetch_ohlcv(symbol, config.timeframe, since=since, limit=100)
        
        logger.info(f"Fetched {len(candles)} candles")
        logger.info(f"Date range: {datetime.fromtimestamp(candles[0][0]/1000).strftime('%Y-%m-%d %H:%M')} to {datetime.fromtimestamp(candles[-1][0]/1000).strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"Current price: ${candles[-1][4]:.2f}")
        
        if len(candles) < 50:
            logger.error(f"❌ Not enough candles! Need 50+, got {len(candles)}")
            logger.info(f"   Solution: Increase --days parameter (try --days 7)")
            return False
        
        print_section("STEP 3: Initialize LLM Strategy")
        
        # Get database manager for trade history
        db_manager = None
        try:
            from database import get_database
            db_manager = get_database()
            trade_count = len(db_manager.get_trades(limit=100))
            logger.info(f"Database available: {trade_count} trades in history")
        except Exception as e:
            logger.warning(f"Database not available: {e}")
        
        # Create LLM strategy with config
        strategy_config = config.get_strategy_configs()["llm_pattern"]
        llm_strategy = LLMPatternStrategy(strategy_config, db_manager=db_manager)
        
        logger.info(f"✅ LLM Strategy initialized")
        logger.info(f"   Model: {llm_strategy.llm_client.model}")
        logger.info(f"   Temperature: {llm_strategy.llm_client.temperature}")
        logger.info(f"   Timeout: {llm_strategy.llm_client.timeout_seconds}s")
        logger.info(f"   RAG Enabled: {llm_strategy.use_rag}")
        logger.info(f"   Require Patterns: {llm_strategy.response_parser.require_patterns}")
        
        print_section("STEP 4: Call LLM for Analysis")
        
        logger.info("Calling LLM (this may take 10-30 seconds)...")
        logger.info("")
        
        # Compute signal (this calls the LLM)
        signal = llm_strategy.compute_signal(
            exchange=exchange,
            symbol=symbol,
            timeframe=config.timeframe,
            candle_data=candles
        )
        
        print_section("STEP 5: LLM Signal Results")
        
        logger.info(f"Direction: {signal.direction.upper()}")
        logger.info(f"Confidence: {signal.confidence:.1%}")
        logger.info(f"Price: ${signal.price:.2f}")
        logger.info(f"Position Size: {signal.position_size:.1%}")
        
        if signal.stop_loss > 0:
            logger.info(f"Stop Loss: ${signal.stop_loss:.2f}")
        if signal.take_profit > 0:
            logger.info(f"Take Profit: ${signal.take_profit:.2f}")
        
        logger.info(f"\nIndicators:")
        for key, value in signal.indicators.items():
            logger.info(f"  {key}: {value}")
        
        logger.info(f"\nReasoning:")
        reasoning = signal.info.get("reasoning", "No reasoning provided")
        # Truncate long reasoning
        if len(reasoning) > 500:
            logger.info(f"  {reasoning[:500]}...")
        else:
            logger.info(f"  {reasoning}")
        
        patterns = signal.info.get("patterns", [])
        if patterns:
            logger.info(f"\nPatterns Found:")
            for pattern in patterns:
                logger.info(f"  - {pattern}")
        
        print_section("STEP 6: Signal Evaluation")
        
        # Check if signal meets confidence threshold
        meets_confidence = signal.confidence >= config.min_signal_confidence
        is_actionable = signal.direction in ["bullish", "bearish"]
        
        logger.info(f"Meets minimum confidence ({config.min_signal_confidence:.1%})? {meets_confidence}")
        logger.info(f"Is actionable (not neutral)? {is_actionable}")
        
        if meets_confidence and is_actionable:
            logger.info("✅ Signal PASSES filters - WOULD TRIGGER TRADE")
            logger.info(f"\nExpected Trade:")
            side = "BUY" if signal.direction == "bullish" else "SELL"
            logger.info(f"  Side: {side}")
            logger.info(f"  Entry: ${signal.price:.2f}")
            logger.info(f"  Position Size: {signal.position_size:.1%} of portfolio")
            logger.info(f"  Stop Loss: ${signal.stop_loss:.2f} ({abs(signal.stop_loss - signal.price) / signal.price * 100:.1f}%)")
            logger.info(f"  Take Profit: ${signal.take_profit:.2f} ({abs(signal.take_profit - signal.price) / signal.price * 100:.1f}%)")
        else:
            logger.info("❌ Signal FAILS filters - NO TRADE")
            if not is_actionable:
                logger.info("   Reason: Direction is 'neutral' (no trade signal)")
            if not meets_confidence:
                logger.info(f"   Reason: Confidence too low ({signal.confidence:.1%} < {config.min_signal_confidence:.1%})")
        
        print_section("STEP 7: Multi-Strategy Aggregation (if enabled)")
        
        if config.use_multi_strategy:
            logger.info(f"Multi-strategy mode: {config.strategy_aggregation_mode}")
            
            # Check which other strategies are enabled
            other_strategies = []
            if config.strategy_ema_enabled:
                other_strategies.append(f"EMA (weight: {config.strategy_ema_weight})")
            if config.strategy_rsi_bb_enabled:
                other_strategies.append(f"RSI+BB (weight: {config.strategy_rsi_bb_weight})")
            if config.strategy_macd_enabled:
                other_strategies.append(f"MACD (weight: {config.strategy_macd_weight})")
            
            if other_strategies:
                logger.info(f"Other enabled strategies: {', '.join(other_strategies)}")
                logger.info(f"LLM weight: {config.strategy_llm_weight}")
                
                if config.strategy_aggregation_mode == "unanimous":
                    logger.warning("⚠️  Mode 'unanimous' requires ALL strategies to agree!")
                    logger.info("   LLM alone cannot trigger trade - needs other strategies too")
                elif config.strategy_aggregation_mode == "voting":
                    logger.info("Mode 'voting' requires majority agreement")
                elif config.strategy_aggregation_mode == "weighted_voting":
                    logger.info("Mode 'weighted_voting' uses confidence * weight for each strategy")
                elif config.strategy_aggregation_mode == "any":
                    logger.info("Mode 'any' allows any single strategy to trigger trade")
                elif config.strategy_aggregation_mode == "best":
                    logger.info("Mode 'best' uses highest confidence signal")
            else:
                logger.info("✅ Only LLM strategy is enabled - its signal will be used directly")
        else:
            logger.info("Multi-strategy mode is disabled")
        
        print_section("STEP 8: Diagnostic Summary")
        
        # Provide actionable recommendations
        if signal.direction == "neutral":
            logger.info("🔍 LLM returned NEUTRAL signal")
            logger.info("\nPossible causes:")
            logger.info("  1. Market conditions are genuinely unclear/mixed")
            logger.info("  2. LLM prompt emphasizes conservative analysis")
            logger.info("  3. No clear technical patterns detected")
            logger.info("\nSolutions to try:")
            logger.info("  - Lower min_signal_confidence (e.g., 0.2 instead of 0.3)")
            logger.info("  - Adjust LLM temperature (higher = more decisive)")
            logger.info("  - Use different market conditions (trending vs ranging)")
            logger.info("  - Try different model (phi3 vs mistral)")
        
        elif signal.confidence < config.min_signal_confidence:
            logger.info(f"🔍 LLM signal confidence too low ({signal.confidence:.1%} < {config.min_signal_confidence:.1%})")
            logger.info("\nSolutions:")
            logger.info(f"  - Lower min_signal_confidence to {signal.confidence:.1%} or below")
            logger.info(f"  - Or wait for stronger market signals")
        
        elif config.use_multi_strategy and len(other_strategies) > 0:
            logger.info("🔍 LLM signal is good but may be filtered by multi-strategy aggregation")
            logger.info("\nSolutions:")
            logger.info("  - Test with ONLY LLM enabled (disable other strategies)")
            logger.info("  - Use aggregation_mode='any' instead of 'unanimous'")
            logger.info("  - Increase LLM weight relative to other strategies")
        
        else:
            logger.info("✅ Signal looks good! Should trigger trades in backtest.")
            logger.info("\nIf still not seeing trades, check:")
            logger.info("  - Backtest is using correct config (check logs)")
            logger.info("  - No position already open (can't open 2nd position)")
            logger.info("  - Sampling interval not too high (try lower value)")
        
        # Test with actual backtest
        print_section("STEP 9: Test with Sample Backtest (Optional)")
        
        response = input("\nRun 3-day sample backtest with LLM-only? (y/n): ")
        if response.lower() == 'y':
            logger.info("\nRunning sample backtest...")
            
            from backtest import run_backtest
            
            config_overrides = {
                "strategy_ema_enabled": False,
                "strategy_rsi_bb_enabled": False,
                "strategy_macd_enabled": False,
                "strategy_llm_enabled": True,
                "llm_backtest_sample_interval": 24,  # Analyze ~3 times
                "min_signal_confidence": 0.2,  # Lower threshold
            }
            
            try:
                result = run_backtest(
                    days_back=3,
                    config_overrides=config_overrides
                )
                
                logger.info(f"\n✅ Backtest completed!")
                logger.info(f"   Trades: {result.get('trades', 0)}")
                logger.info(f"   P&L: ${result.get('pnl', 0):.2f} ({result.get('pnl_pct', 0):.2f}%)")
                
                if result.get('trades', 0) == 0:
                    logger.warning("⚠️  Still no trades! LLM may be consistently returning neutral signals.")
                    logger.info("\nNext steps:")
                    logger.info("  1. Check logs/bot_error.log for LLM responses")
                    logger.info("  2. Try different market conditions (different date range)")
                    logger.info("  3. Adjust LLM temperature or model")
                    logger.info("  4. Manually inspect LLM responses for JSON parsing issues")
                
            except Exception as e:
                logger.error(f"❌ Backtest failed: {e}")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.info("\nMissing dependencies. Install with:")
        logger.info("  pip install ccxt ollama")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        logger.exception("Detailed traceback:")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose LLM signal generation and trade execution"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTC/USDT",
        help="Trading symbol (default: BTC/USDT)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Days of historical data (default: 7)"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 80)
    logger.info("LLM Signal Diagnostic Tool")
    logger.info("=" * 80)
    logger.info("This tool traces through the complete LLM signal generation pipeline")
    logger.info("to identify why trades aren't being executed.\n")
    
    success = analyze_llm_signal_generation(
        symbol=args.symbol,
        days_back=args.days
    )
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
