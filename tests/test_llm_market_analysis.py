#!/usr/bin/env python3
"""
Test script for the redesigned LLM Market Analysis Strategy.

This verifies that the strategy now works with market data
instead of requiring trading history.
"""

import logging
import ccxt
import pytest
from config import BotConfig
from strategies import LLMPatternStrategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

pytestmark = pytest.mark.llm_integration


def test_llm_market_analysis():
    """Test the LLM strategy with market data (no trading history required)"""
    
    print("=" * 70)
    print("Testing LLM Market Analysis Strategy (Redesigned)")
    print("=" * 70)
    
    # Load configuration
    config_obj = BotConfig(
        binance_api_key="",  # Not needed for public data
        binance_api_secret="",
    )
    config = vars(config_obj)
    
    print(f"\n✓ Configuration loaded")
    print(f"  - LLM Model: {config['llm_ollama_model']}")
    print(f"  - Ollama URL: {config['llm_ollama_url']}")
    print(f"  - Symbol: {config['symbol']}")
    print(f"  - Timeframe: {config['timeframe']}")
    
    # Initialize exchange (read-only, no API keys needed)
    exchange = ccxt.binanceus({"enableRateLimit": True})
    print(f"\n✓ Exchange initialized: {exchange.name}")
    
    # Initialize LLM strategy WITHOUT database manager
    # This tests that it works without trading history
    try:
        llm_strategy = LLMPatternStrategy(config, db_manager=None)
        print(f"\n✓ LLM Strategy initialized")
        print(f"  - {llm_strategy.get_description()}")
    except ImportError as e:
        print(f"\n✗ Failed to initialize LLM strategy: {e}")
        print("  Make sure Ollama package is installed: pip install ollama")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False
    
    # Check if Ollama is running
    try:
        import requests
        response = requests.get(f"{config['llm_ollama_url']}/api/version", timeout=2)
        if response.status_code == 200:
            print(f"\n✓ Ollama is running at {config['llm_ollama_url']}")
        else:
            print(f"\n✗ Ollama responded with status {response.status_code}")
            print("  Make sure Ollama is running: ollama serve")
            return False
    except requests.exceptions.ConnectionError:
        print(f"\n✗ Cannot connect to Ollama at {config['llm_ollama_url']}")
        print("  Make sure Ollama is running: ollama serve")
        return False
    except Exception as e:
        print(f"\n✗ Error checking Ollama: {e}")
        return False
    
    # Test signal generation (this should work without trading history!)
    print(f"\n{'=' * 70}")
    print("Testing Signal Generation (Market Data Analysis)")
    print("=" * 70)
    print("\nThis will:")
    print("  1. Fetch recent candles from Binance")
    print("  2. Calculate technical indicators (RSI, MACD, etc.)")
    print("  3. Send market data to LLM for analysis")
    print("  4. Generate trading signal")
    print("\nThis may take 10-30 seconds...")
    print("-" * 70)
    
    try:
        signal = llm_strategy.compute_signal(
            exchange=exchange,
            symbol=config['symbol'],
            timeframe=config['timeframe'],
            candle_data=None  # Will fetch from exchange
        )
        
        print(f"\n{'=' * 70}")
        print("✓ Signal Generated Successfully!")
        print("=" * 70)
        print(f"\nSignal Details:")
        print(f"  - Direction: {signal.direction.upper()}")
        print(f"  - Confidence: {signal.confidence:.2%}")
        print(f"  - Price: ${signal.price:.2f}")
        print(f"  - Stop Loss: ${signal.stop_loss:.2f} ({((signal.stop_loss - signal.price) / signal.price * 100):.2f}%)")
        print(f"  - Take Profit: ${signal.take_profit:.2f} ({((signal.take_profit - signal.price) / signal.price * 100):.2f}%)")
        print(f"  - Position Size: {signal.position_size:.1%}")
        print(f"  - Strategy: {signal.strategy_name}")
        
        if signal.info and 'reasoning' in signal.info:
            print(f"\nLLM Reasoning:")
            reasoning = signal.info['reasoning']
            # Wrap long text
            max_width = 68
            words = reasoning.split()
            line = "  "
            for word in words:
                if len(line) + len(word) + 1 > max_width:
                    print(line)
                    line = "  " + word
                else:
                    line += " " + word if line != "  " else word
            if line.strip():
                print(line)
        
        if signal.info and 'patterns' in signal.info:
            patterns = signal.info['patterns']
            if patterns:
                print(f"\nPatterns Identified:")
                for pattern in patterns:
                    print(f"  • {pattern}")
        
        print("\n" + "=" * 70)
        print("✓ TEST PASSED - LLM strategy works with market data!")
        print("=" * 70)
        print("\nKey Achievement:")
        print("  The strategy generated a signal WITHOUT requiring trading history.")
        print("  It analyzed market data (candles, indicators, patterns) instead.")
        print("\nYou can now:")
        print("  ✓ Run backtests immediately")
        print("  ✓ Use the strategy in live/paper trading")
        print("  ✓ Click 'Run Analysis Now' to see real-time analysis")
        
        return True
        
    except Exception as e:
        print(f"\n{'=' * 70}")
        print(f"✗ TEST FAILED")
        print("=" * 70)
        print(f"\nError: {e}")
        logger.exception("Full traceback:")
        return False


if __name__ == "__main__":
    try:
        success = test_llm_market_analysis()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        exit(1)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        exit(1)
