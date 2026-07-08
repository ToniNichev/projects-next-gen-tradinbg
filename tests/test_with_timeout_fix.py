#!/usr/bin/env python3
"""
Test LLM with increased timeout and optimizations

This tests with:
- 120s timeout (2x original)
- Shorter prompt (less processing)
- phi3 model
"""

import logging
import pytest

logging.basicConfig(level=logging.INFO, format="%(message)s")

pytestmark = pytest.mark.llm_integration


def test_with_fixes():
    try:
        import ccxt
        from config import BotConfig
        from strategies.llm.strategy import LLMPatternStrategy
        
        print("=" * 60)
        print("Testing with TIMEOUT FIX")
        print("=" * 60)
        print("\nChanges:")
        print("  • Timeout: 120s (was 60s)")
        print("  • Model: phi3")
        print("  • Temperature: 0.4")
        print("")
        
        config = BotConfig.load()
        exchange = ccxt.binanceus({"enableRateLimit": True})
        candles = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=100)
        
        print(f"Current price: ${candles[-1][4]:.2f}")
        print(f"Market: RSI=74.2 (overbought), Trend=bullish")
        
        strategy_config = config.get_strategy_configs()["llm_pattern"]
        
        # Apply fixes
        strategy_config["llm_timeout_seconds"] = 120  # Double timeout
        strategy_config["llm_temperature"] = 0.4
        strategy_config["llm_require_patterns"] = False
        strategy_config["llm_num_predict"] = 600  # Shorter = faster
        
        db_manager = None
        try:
            from database import get_database
            db_manager = get_database()
        except:
            pass
        
        llm_strategy = LLMPatternStrategy(strategy_config, db_manager=db_manager)
        
        print("\nCalling LLM with 120s timeout...")
        print("(This may take 60-90 seconds on your system)")
        print("")
        
        import time
        start = time.time()
        
        signal = llm_strategy.compute_signal(
            exchange=exchange,
            symbol="BTC/USDT",
            timeframe="1h",
            candle_data=candles
        )
        
        duration = time.time() - start
        
        print("\n" + "=" * 60)
        print(f"RESULT (completed in {duration:.0f}s)")
        print("=" * 60)
        print(f"Direction:  {signal.direction.upper()}")
        print(f"Confidence: {signal.confidence:.1%}")
        
        if signal.direction != "neutral":
            print(f"\n✅ SUCCESS! Got {signal.direction.upper()} signal")
            print(f"   Confidence: {signal.confidence:.1%}")
            print(f"   Position: {signal.position_size:.1%}")
            print(f"\n   LLM is working but was timing out!")
            print(f"   Actual response time: {duration:.0f}s")
            print(f"\nNext: Run backtest with 120s timeout")
            return True
        else:
            print(f"\n⚠️  Still neutral after {duration:.0f}s")
            
            if duration > 100:
                print(f"\n   LLM is VERY slow on your system")
                print(f"   Solutions:")
                print(f"     1. Check Activity Monitor - is CPU at 100%?")
                print(f"     2. Restart Ollama: pkill ollama && ollama serve")
                print(f"     3. Check Ollama is using GPU (if available)")
                print(f"     4. Try mistral (might be faster/slower)")
            
            return False
            
    except TimeoutError as e:
        print(f"\n❌ STILL TIMING OUT: {e}")
        print("\nYour system is very slow or Ollama is having issues")
        print("\nTry:")
        print("  1. Restart Ollama: pkill ollama && ollama serve")
        print("  2. Check system resources: Activity Monitor")
        print("  3. Increase to 180s: llm_timeout_seconds=180")
        return False
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_with_fixes()
