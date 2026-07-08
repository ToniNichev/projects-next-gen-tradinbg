#!/usr/bin/env python3
"""
Quick LLM Test - Verify LLM can generate non-neutral signals

This minimal test checks if your LLM setup can produce buy/sell signals.
"""

import logging
import pytest

logging.basicConfig(level=logging.INFO, format="%(message)s")

pytestmark = pytest.mark.llm_integration


def test_llm_signal():
    """Test if LLM generates actionable signals"""
    print("=" * 60)
    print("Quick LLM Signal Test")
    print("=" * 60)
    
    try:
        import ccxt
        from config import BotConfig
        from strategies.llm.strategy import LLMPatternStrategy
        
        # Load config
        config = BotConfig.load()
        
        # Create exchange
        exchange = ccxt.binanceus({"enableRateLimit": True})
        
        # Fetch recent data
        print("\n1. Fetching market data...")
        candles = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=100)
        print(f"   ✓ Got {len(candles)} candles")
        print(f"   Current price: ${candles[-1][4]:.2f}")
        
        # Initialize strategy
        print("\n2. Initializing LLM strategy...")
        strategy_config = config.get_strategy_configs()["llm_pattern"]
        
        # Get database if available
        db_manager = None
        try:
            from database import get_database
            db_manager = get_database()
        except:
            pass
        
        llm_strategy = LLMPatternStrategy(strategy_config, db_manager=db_manager)
        print(f"   ✓ Model: {llm_strategy.llm_client.model}")
        print(f"   ✓ Temperature: {llm_strategy.llm_client.temperature}")
        
        # Get signal
        print("\n3. Calling LLM (15-30 seconds)...")
        signal = llm_strategy.compute_signal(
            exchange=exchange,
            symbol="BTC/USDT",
            timeframe="1h",
            candle_data=candles
        )
        
        # Display results
        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"Direction:  {signal.direction.upper()}")
        print(f"Confidence: {signal.confidence:.1%}")
        print(f"Position:   {signal.position_size:.1%}")
        
        if signal.direction != "neutral":
            print(f"\n✅ SUCCESS - LLM generated {signal.direction.upper()} signal!")
            print(f"\nWould trigger trade:")
            print(f"  Entry: ${signal.price:.2f}")
            print(f"  Stop:  ${signal.stop_loss:.2f}")
            print(f"  Target: ${signal.take_profit:.2f}")
            
            # Check if passes confidence filter
            min_conf = config.min_signal_confidence
            if signal.confidence >= min_conf:
                print(f"\n✅ Confidence {signal.confidence:.1%} >= threshold {min_conf:.1%}")
                print("   Signal would PASS filters ✓")
            else:
                print(f"\n⚠️  Confidence {signal.confidence:.1%} < threshold {min_conf:.1%}")
                print("   Signal would be FILTERED OUT")
                print(f"   Solution: Lower min_signal_confidence to {signal.confidence:.1%}")
        else:
            print(f"\n⚠️  LLM returned NEUTRAL (no trade)")
            print("\nPossible reasons:")
            print("  • Market signals genuinely mixed")
            print("  • LLM being conservative")
            print("  • Technical indicators unclear")
            
            print("\nSolutions to try:")
            print("  1. Lower min_signal_confidence (try 0.2)")
            print("  2. Increase llm_temperature (try 0.5)")
            print("  3. Try different model (phi3 vs mistral)")
            print("  4. Test different market conditions")
        
        # Show reasoning
        reasoning = signal.info.get("reasoning", "")
        if reasoning:
            print(f"\nLLM Reasoning (first 200 chars):")
            print(f"  {reasoning[:200]}...")
        
        return signal.direction != "neutral"
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_llm_signal()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ LLM IS WORKING - Generates actionable signals")
        print("\nNext: Run full backtest")
        print("  python backtest.py 7")
    else:
        print("⚠️  LLM returns only neutral - needs tuning")
        print("\nNext: Run detailed diagnostic")
        print("  python diagnose_llm_signals.py")
    print("=" * 60)
