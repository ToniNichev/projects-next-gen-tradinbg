#!/usr/bin/env python3
"""
Test with Mistral model instead of phi3

Mistral is generally:
- More instruction-following
- More willing to take positions
- Better at JSON formatting
- Slower but higher quality
"""

import logging
import pytest

logging.basicConfig(level=logging.WARNING)

pytestmark = pytest.mark.llm_integration


def test_mistral():
    try:
        import ccxt
        from config import BotConfig
        from strategies.llm.strategy import LLMPatternStrategy
        
        print("Testing with MISTRAL model...")
        print("(Generally more decisive than phi3)\n")
        
        config = BotConfig.load()
        exchange = ccxt.binanceus({"enableRateLimit": True})
        candles = exchange.fetch_ohlcv("BTC/USDT", "1h", limit=100)
        
        strategy_config = config.get_strategy_configs()["llm_pattern"]
        
        # Override to use mistral
        strategy_config["llm_ollama_model"] = "mistral"
        strategy_config["llm_temperature"] = 0.4  # Balanced
        strategy_config["llm_require_patterns"] = False
        strategy_config["llm_timeout_seconds"] = 60  # Mistral is slower
        
        db_manager = None
        try:
            from database import get_database
            db_manager = get_database()
        except:
            pass
        
        llm_strategy = LLMPatternStrategy(strategy_config, db_manager=db_manager)
        
        print("Calling LLM with mistral (30-45s)...")
        signal = llm_strategy.compute_signal(
            exchange=exchange,
            symbol="BTC/USDT",
            timeframe="1h",
            candle_data=candles
        )
        
        print("\n" + "=" * 60)
        print(f"Direction:  {signal.direction.upper()}")
        print(f"Confidence: {signal.confidence:.1%}")
        print(f"Position:   {signal.position_size:.1%}")
        print("=" * 60)
        
        if signal.direction != "neutral":
            print(f"\n✅ MISTRAL WORKS! Generated {signal.direction.upper()} signal")
            print(f"\nTo use mistral permanently:")
            print("  1. Edit .env: BOT_LLM_OLLAMA_MODEL=mistral")
            print("  2. Or in backtest scripts: 'llm_ollama_model': 'mistral'")
            print(f"\nNow run backtest:")
            print("  python3 backtest_llm_tuned.py")
            return True
        else:
            print(f"\n⚠️  Even mistral returns neutral")
            print(f"\nThis strongly suggests:")
            print("  1. Current market truly has mixed signals")
            print("  2. Need to check raw LLM response")
            print("\nNext step:")
            print("  python3 debug_llm_response.py")
            return False
            
    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e):
            print(f"\n❌ Mistral model not installed")
            print("\nInstall it:")
            print("  ollama pull mistral")
            print("\nThen run this script again")
        else:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        return False

if __name__ == "__main__":
    test_mistral()
