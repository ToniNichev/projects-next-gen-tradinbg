#!/usr/bin/env python3
"""
LLM Backtest with Optimized Settings

This configuration is specifically tuned to make LLM generate more actionable signals.
Based on your test showing phi3 returning NEUTRAL, these settings should help.
"""

import logging
from backtest import run_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

print("=" * 80)
print("LLM Backtest - Optimized for Signal Generation")
print("=" * 80)
print("\nSettings:")
print("  • LLM ONLY (other strategies disabled)")
print("  • Lower confidence threshold (0.2 instead of 0.3)")
print("  • Higher temperature (0.5 - more decisive)")
print("  • No pattern requirement")
print("  • Analyze every 12 candles")
print("  • Using phi3 model")
print("\n" + "=" * 80 + "\n")

config_overrides = {
    # === DISABLE OTHER STRATEGIES ===
    "strategy_ema_enabled": False,
    "strategy_rsi_bb_enabled": False,
    "strategy_macd_enabled": False,
    "strategy_llm_enabled": True,
    
    # === LOWER FILTERS ===
    "min_signal_confidence": 0.2,  # Accept signals with 20%+ confidence
    
    # === LLM TUNING ===
    "llm_ollama_model": "phi3",  # Use phi3 (faster, more decisive)
    "llm_temperature": 0.5,  # Higher = more willing to take positions (was 0.3)
    "llm_require_patterns": False,  # Don't require specific patterns
    "llm_num_predict": 800,  # Shorter responses (more focused)
    
    # === BACKTEST OPTIMIZATION ===
    "llm_backtest_sample_interval": 12,  # Analyze every 12 candles
    "llm_timeout_seconds": 30,  # 30s per analysis with phi3
    
    # === AGGREGATION ===
    "strategy_aggregation_mode": "any",  # Any strategy can trigger
}

print("Running 7-day backtest with optimized LLM settings...")
print("Expected: ~14 analyses, 5-10 minutes\n")

try:
    result = run_backtest(
        days_back=7,
        config_overrides=config_overrides
    )
    
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total Trades: {result['trades']}")
    print(f"Final Value: ${result['final_value']:.2f}")
    print(f"P&L: ${result['pnl']:.2f} ({result['pnl_pct']:+.2f}%)")
    print(f"Buy & Hold: {result['buy_hold_pct']:+.2f}%")
    print(f"vs Buy & Hold: {result['pnl_pct'] - result['buy_hold_pct']:+.2f}%")
    print("=" * 80)
    
    if result['trades'] == 0:
        print("\n⚠️  STILL NO TRADES!")
        print("\nThis means phi3 is consistently returning neutral even with:")
        print("  • Lower confidence threshold (0.2)")
        print("  • Higher temperature (0.5)")
        print("  • No pattern requirement")
        print("\nPossible causes:")
        print("  1. Current market genuinely shows mixed signals")
        print("  2. phi3 model personality is very conservative")
        print("  3. LLM response not being parsed correctly")
        print("\nNext steps:")
        print("  1. Check logs/bot_error.log for actual LLM responses")
        print("  2. Try mistral model instead: llm_ollama_model='mistral'")
        print("  3. Run: python diagnose_llm_signals.py")
        print("  4. Test different date range (trending market)")
    else:
        print(f"\n✅ SUCCESS! Generated {result['trades']} trades")
        print("\nTo see trade details:")
        print("  tail -20 data/backtest_log.csv")
        print("\nTo use these settings permanently:")
        print("  1. Update .env with above config values")
        print("  2. Or save as preset in database")
    
except KeyboardInterrupt:
    print("\n\nBacktest interrupted by user")
except Exception as e:
    print(f"\n❌ Backtest failed: {e}")
    import traceback
    traceback.print_exc()
    
    print("\nTroubleshooting:")
    print("  • Check if Ollama is running: ps aux | grep ollama")
    print("  • Check if phi3 is installed: ollama list")
    print("  • Try: ollama pull phi3")
