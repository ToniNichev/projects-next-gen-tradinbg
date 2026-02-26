#!/usr/bin/env python3
"""
Fast LLM Backtest - Optimized for slow systems

Reduces analyses from 168 to ~10 by:
- Higher sample interval (analyze less frequently)
- Shorter lookback (fewer days)
- Optimized prompt length
"""

import logging
from backtest import run_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

print("=" * 80)
print("FAST LLM Backtest - Optimized for Your System")
print("=" * 80)
print("\nOptimizations:")
print("  • Sample interval: 50 (was 12) = ~10 analyses instead of 168")
print("  • Days: 7 (reasonable period)")
print("  • Timeout: 120s (for your system)")
print("  • Shorter prompt responses")
print("\nExpected time: 10-15 minutes (vs 3+ hours)")
print("=" * 80 + "\n")

config_overrides = {
    # === DISABLE OTHER STRATEGIES ===
    "strategy_ema_enabled": False,
    "strategy_rsi_bb_enabled": False,
    "strategy_macd_enabled": False,
    "strategy_llm_enabled": True,
    
    # === CRITICAL: REDUCE ANALYSES ===
    "llm_backtest_sample_interval": 50,  # Analyze every 50 candles (was 12)
    # For 7 days, 1h candles = 168 candles / 50 = ~3 analyses
    
    # === TIMING ===
    "llm_timeout_seconds": 120,  # Your system needs this
    
    # === FILTERS ===
    "min_signal_confidence": 0.2,
    "llm_require_patterns": False,
    
    # === LLM OPTIMIZATION ===
    "llm_ollama_model": "phi3",
    "llm_temperature": 0.4,
    "llm_num_predict": 500,  # Shorter = faster (was 1000)
    "llm_lookback_days": 3,  # Less context = faster (was 7)
    
    # === DISABLE RAG (speeds up processing) ===
    "llm_use_rag": False,  # RAG adds overhead
    
    # === AGGREGATION ===
    "strategy_aggregation_mode": "any",
}

print("Running 7-day backtest with ~3-4 LLM analyses...")
print("This should complete in 10-15 minutes\n")

try:
    result = run_backtest(
        days_back=7,
        config_overrides=config_overrides
    )
    
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total Trades: {result['trades']}")
    print(f"P&L: ${result['pnl']:.2f} ({result['pnl_pct']:+.2f}%)")
    print(f"Buy & Hold: {result['buy_hold_pct']:+.2f}%")
    print("=" * 80)
    
    if result['trades'] > 0:
        print(f"\n✅ SUCCESS! Generated {result['trades']} trades")
        print("\nTo see details:")
        print("  tail -20 data/backtest_log.csv")
    else:
        print("\n⚠️  No trades generated")
        print("\nPossible reasons:")
        print("  1. Only 3-4 analyses (small sample)")
        print("  2. Market conditions at those specific points were neutral")
        print("  3. Try increasing days_back to 14 (more opportunities)")
    
except KeyboardInterrupt:
    print("\n\nBacktest interrupted")
except Exception as e:
    print(f"\n❌ Error: {e}")

print("\n" + "=" * 80)
print("CONFIGURATION RECOMMENDATIONS")
print("=" * 80)
print("\nFor production use with your slow system:")
print("  • Sample interval: 50-100 (balance speed vs opportunities)")
print("  • Timeout: 120s minimum")
print("  • Days: 7-14 (more days = more trades)")
print("  • Consider: Upgrade hardware or use cloud LLM")
