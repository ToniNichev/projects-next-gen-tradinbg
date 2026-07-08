#!/usr/bin/env python3
"""
Test if prompt changes make LLM more decisive

This quickly tests if the less conservative prompt generates signals.
"""

import logging
import pytest

logging.basicConfig(level=logging.WARNING)  # Quiet output

pytestmark = pytest.mark.llm_integration


def test_new_prompt():
    try:
        import ccxt
        from config import BotConfig
        from strategies.llm.strategy import LLMPatternStrategy
        
        print("Testing with LESS CONSERVATIVE prompt...")
        print("(This should make LLM more willing to take positions)\n")
        
        config = BotConfig.load()
        exchange = ccxt.binanceus({"enableRateLimit": True})
        candles = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=100)
        
        strategy_config = config.get_strategy_configs()["llm_pattern"]
        
        # Override to be even more permissive
        strategy_config["llm_temperature"] = 0.5
        strategy_config["llm_require_patterns"] = False
        
        # Get database if available
        db_manager = None
        try:
            from database import get_database
            db_manager = get_database()
        except:
            pass
        
        llm_strategy = LLMPatternStrategy(strategy_config, db_manager=db_manager)
        
        print("Calling LLM with new prompt (20-30s)...")
        signal = llm_strategy.compute_signal(
            exchange=exchange,
            symbol="BTC/USDT",
            timeframe="1h",
            candle_data=candles
        )
        
        print("\n" + "=" * 60)
        print(f"Direction:  {signal.direction.upper()}")
        print(f"Confidence: {signal.confidence:.1%}")
        print("=" * 60)
        
        if signal.direction != "neutral":
            print(f"\n✅ SUCCESS! Prompt fix worked!")
            print(f"\nLLM now generates {signal.direction.upper()} signals")
            print(f"Confidence: {signal.confidence:.1%}")
            print(f"\nNow run full backtest:")
            print("  python3 backtest_llm_tuned.py")
            return True
        else:
            print(f"\n⚠️  Still neutral")
            print("\nThis means:")
            print("  1. Current market genuinely unclear, OR")
            print("  2. phi3 model very conservative, OR")
            print("  3. Need to try mistral instead")
            print("\nNext steps:")
            print("  1. Try mistral: Edit .env → BOT_LLM_OLLAMA_MODEL=mistral")
            print("  2. Or test different date/symbol")
            print("  3. Or inspect raw LLM response manually")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_new_prompt()
