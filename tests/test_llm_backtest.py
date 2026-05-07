#!/usr/bin/env python3
"""
Test script for LLM pattern backtest functionality.

This script verifies:
1. Ollama is running and accessible
2. Required model is loaded
3. Backtest has sufficient data for LLM analysis
4. Timeout protection is working
5. Progress tracking works correctly
"""

import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def test_ollama_connection():
    """Test connection to Ollama server"""
    logger.info("=" * 80)
    logger.info("TEST 1: Ollama Connection")
    logger.info("=" * 80)
    
    try:
        import ollama
        client = ollama.Client(host="http://localhost:11434")
        
        # Test with a simple prompt
        response = client.generate(
            model="mistral",
            prompt="Respond with just 'OK' if you can read this.",
            stream=False,
            options={"num_predict": 10}
        )
        
        logger.info("✅ Ollama is running and responding")
        logger.info(f"   Model: mistral")
        logger.info(f"   Response: {response.get('response', '') if isinstance(response, dict) else getattr(response, 'response', '')}")
        return True
        
    except ImportError:
        logger.error("❌ ollama package not installed")
        logger.info("   Fix: pip install ollama")
        return False
        
    except Exception as e:
        logger.error(f"❌ Cannot connect to Ollama: {e}")
        logger.info("   Troubleshooting:")
        logger.info("   1. Check if Ollama is running: ps aux | grep ollama")
        logger.info("   2. Start Ollama: ollama serve")
        logger.info("   3. Pull model: ollama pull mistral")
        return False


def test_model_availability():
    """Test if required models are available"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Model Availability")
    logger.info("=" * 80)
    
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            
            logger.info(f"✅ Found {len(models)} models:")
            for model in models:
                name = model.get("name", "unknown")
                size_gb = model.get("size", 0) / (1024**3)
                logger.info(f"   - {name} ({size_gb:.1f} GB)")
            
            # Check for recommended models
            model_names = [m.get("name", "") for m in models]
            has_mistral = any("mistral" in m for m in model_names)
            has_phi3 = any("phi3" in m for m in model_names)
            
            if has_mistral:
                logger.info("✅ Recommended model 'mistral' is available")
            elif has_phi3:
                logger.info("✅ Alternative model 'phi3' is available")
            else:
                logger.warning("⚠️  No recommended models found")
                logger.info("   Install with: ollama pull mistral")
            
            return len(models) > 0
        else:
            logger.error(f"❌ Ollama API returned status {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to Ollama API")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking models: {e}")
        return False


def test_backtest_data_requirements():
    """Test backtest data requirements"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Backtest Data Requirements")
    logger.info("=" * 80)
    
    try:
        import ccxt
        from config import BotConfig
        
        config = BotConfig.load()
        exchange = ccxt.binanceus({"enableRateLimit": True})
        
        # Calculate required candles
        min_candles = 50  # Minimum for technical indicators
        sample_interval = config.llm_backtest_sample_interval
        recommended_candles = max(100, sample_interval * 10)  # At least 10 analyses
        
        logger.info(f"Configuration:")
        logger.info(f"   Symbol: {config.symbol}")
        logger.info(f"   Timeframe: {config.timeframe}")
        logger.info(f"   Sample interval: every {sample_interval} candles")
        logger.info(f"   Minimum candles needed: {min_candles}")
        logger.info(f"   Recommended candles: {recommended_candles}")
        
        # Calculate days needed based on timeframe
        timeframe_hours = {
            "5m": 1/12, "15m": 1/4, "30m": 0.5,
            "1h": 1, "2h": 2, "4h": 4, 
            "12h": 12, "1d": 24
        }
        hours_per_candle = timeframe_hours.get(config.timeframe, 1)
        min_days = (min_candles * hours_per_candle) / 24
        recommended_days = (recommended_candles * hours_per_candle) / 24
        
        logger.info(f"\nRecommendations for {config.timeframe} timeframe:")
        logger.info(f"   Minimum days: {min_days:.1f} days")
        logger.info(f"   Recommended days: {recommended_days:.1f} days")
        
        # Test actual data availability
        logger.info(f"\nTesting data fetch...")
        candles = exchange.fetch_ohlcv(config.symbol, config.timeframe, limit=recommended_candles)
        logger.info(f"✅ Successfully fetched {len(candles)} candles")
        
        if len(candles) >= recommended_candles:
            logger.info(f"✅ Sufficient data available for robust backtest")
        elif len(candles) >= min_candles:
            logger.warning(f"⚠️  Data available but limited ({len(candles)}/{recommended_candles} candles)")
        else:
            logger.error(f"❌ Insufficient data ({len(candles)}/{min_candles} candles)")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error testing data requirements: {e}")
        return False


def test_timeout_handling():
    """Test that timeout handling works"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Timeout Handling")
    logger.info("=" * 80)
    
    try:
        from strategies.llm.llm_client import OllamaClient
        
        # Create client with very short timeout
        client = OllamaClient(
            ollama_url="http://localhost:11434",
            model="mistral",
            timeout_seconds=5
        )
        
        logger.info("Testing with 5-second timeout...")
        
        # Try a quick analysis
        try:
            result = client.analyze("Say 'test successful' and nothing else.")
            logger.info(f"✅ Quick test completed in {result['duration_ms']}ms")
            logger.info(f"   Response: {result['response'][:100]}")
            return True
            
        except TimeoutError as e:
            logger.warning(f"⚠️  Request timed out (may indicate slow model)")
            logger.info(f"   Consider: Using a faster model like phi3")
            return True  # Timeout handling is working
            
    except Exception as e:
        logger.error(f"❌ Error testing timeout: {e}")
        return False


def test_sample_backtest():
    """Run a minimal backtest to verify functionality"""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 5: Sample Backtest (30 seconds)")
    logger.info("=" * 80)
    
    try:
        from backtest import run_backtest
        from config import BotConfig
        
        config = BotConfig.load()
        
        # Override config for quick test
        config_overrides = {
            "strategy_ema_enabled": False,
            "strategy_rsi_bb_enabled": False,
            "strategy_macd_enabled": False,
            "strategy_llm_enabled": True,
            "llm_backtest_sample_interval": 50,  # Analyze only twice
            "llm_timeout_seconds": 20,  # Allow 20s per analysis
        }
        
        logger.info("Running quick backtest (7 days, minimal analyses)...")
        start_time = datetime.now()
        
        def progress_callback(**kwargs):
            completed = kwargs.get('completed_analyses', 0)
            total = kwargs.get('total_analyses', 1)
            pct = completed / total * 100 if total > 0 else 0
            logger.info(f"   Progress: {completed}/{total} analyses ({pct:.0f}%)")
        
        result = run_backtest(
            days_back=7,
            config_overrides=config_overrides,
            progress_callback=progress_callback
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"✅ Backtest completed in {duration:.1f}s")
        logger.info(f"   Trades: {result.get('trades', 0)}")
        logger.info(f"   P&L: {result.get('pnl_pct', 0):.2f}%")
        logger.info(f"   Final value: ${result.get('final_value', 0):.2f}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        logger.exception("Detailed error:")
        return False


def main():
    """Run all tests"""
    logger.info("LLM Backtest Diagnostic Tool")
    logger.info("Testing llm_pattern strategy functionality\n")
    
    tests = [
        ("Ollama Connection", test_ollama_connection),
        ("Model Availability", test_model_availability),
        ("Data Requirements", test_backtest_data_requirements),
        ("Timeout Handling", test_timeout_handling),
        ("Sample Backtest", test_sample_backtest),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except KeyboardInterrupt:
            logger.info("\n\nTest interrupted by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Test '{name}' crashed: {e}")
            results.append((name, False))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{status}: {name}")
    
    logger.info(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        logger.info("\n🎉 All tests passed! LLM backtest should work correctly.")
        logger.info("\nRecommendations:")
        logger.info("  - Use at least 7 days of data for meaningful results")
        logger.info("  - Consider llm_backtest_sample_interval=24 for 5m timeframe")
        logger.info("  - Monitor first analysis to ensure it completes in <60s")
    else:
        logger.info("\n⚠️  Some tests failed. Review errors above and fix issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()
