#!/usr/bin/env python3
"""
Recommended Backtest Configuration - NO LLM

Focus on fast, proven strategies:
- EMA Crossover
- RSI + Bollinger Bands  
- MACD + Volume

Completes in 5 minutes vs 3 hours with LLM.
"""

import logging
from backtest import run_backtest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

print("=" * 80)
print("RECOMMENDED CONFIGURATION - Traditional Strategies Only")
print("=" * 80)
print("\nEnabled strategies:")
print("  ✅ EMA Crossover (trend following)")
print("  ✅ RSI + Bollinger Bands (mean reversion)")
print("  ✅ MACD + Volume (momentum)")
print("  ❌ LLM Pattern Analysis (disabled - too slow)")
print("\nExpected completion: 2-5 minutes")
print("=" * 80 + "\n")

config_overrides = {
    # === ENABLE FAST STRATEGIES ===
    "strategy_ema_enabled": True,
    "strategy_ema_weight": 1.5,
    
    "strategy_rsi_bb_enabled": True,
    "strategy_rsi_bb_weight": 1.0,
    
    "strategy_macd_enabled": True,
    "strategy_macd_weight": 1.3,
    
    # === DISABLE SLOW LLM ===
    "strategy_llm_enabled": False,
    
    # === AGGREGATION ===
    "strategy_aggregation_mode": "weighted_voting",
    "min_signal_confidence": 0.3,
    
    # === RISK MANAGEMENT ===
    "stop_loss_pct": 0.025,      # 2.5%
    "take_profit_pct": 0.04,     # 4%
    "use_trailing_stop": True,
    "trailing_stop_pct": 0.015,  # 1.5%
}

print("Running 30-day backtest with traditional strategies...")
print("")

try:
    result = run_backtest(
        days_back=30,
        config_overrides=config_overrides
    )
    
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Total Trades: {result['trades']}")
    print(f"Final Value: ${result['final_value']:.2f}")
    print(f"P&L: ${result['pnl']:.2f} ({result['pnl_pct']:+.2f}%)")
    print(f"Buy & Hold: {result['buy_hold_pct']:+.2f}%")
    print(f"Alpha: {result['pnl_pct'] - result['buy_hold_pct']:+.2f}%")
    print("=" * 80)
    
    if result['trades'] > 0:
        print(f"\n✅ Generated {result['trades']} trades")
        print("\nNext steps:")
        print("  1. Review trades: tail -30 data/backtest_log.csv")
        print("  2. Tune parameters if needed")
        print("  3. Run paper trading: python main.py")
        print("  4. Go live when confident")
    else:
        print("\n⚠️  No trades - strategies too conservative")
        print("\nTry lowering min_signal_confidence to 0.2")
    
    print("\n" + "=" * 80)
    print("COMPARISON WITH LLM")
    print("=" * 80)
    print("Traditional strategies:")
    print(f"  ⚡ Backtest time: ~5 minutes")
    print(f"  📊 Trades: {result['trades']}")
    print(f"  💰 P&L: {result['pnl_pct']:+.2f}%")
    print("\nLLM strategy (your system):")
    print("  🐌 Backtest time: ~3 hours")
    print("  📊 Trades: 0 (not working yet)")
    print("  💰 P&L: N/A")
    print("\n✅ Traditional strategies are the practical choice for your setup")
    print("=" * 80)
    
except KeyboardInterrupt:
    print("\n\nBacktest interrupted")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
