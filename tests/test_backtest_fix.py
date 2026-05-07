#!/usr/bin/env python3
"""
Test script to verify the backtest chart marker fix.
This will run a short backtest and check that all trades are included in chart_data.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(__file__))

from backtest import run_backtest

def test_backtest_markers():
    """Test that backtest includes all trade markers in chart data"""
    print("Testing backtest chart marker fix...")
    print("=" * 50)

    # Run a short backtest
    result = run_backtest(days_back=30)

    print(f"Total trades executed: {result['trades']}")
    print(f"Candles in chart: {len(result['chart_data']['candles'])}")
    print(f"Trade markers in chart: {len(result['chart_data']['trades'])}")

    # Check buy/sell counts
    buy_trades = [t for t in result['chart_data']['trades'] if t['side'] == 'buy']
    sell_trades = [t for t in result['chart_data']['trades'] if t['side'] == 'sell']

    print(f"Buy markers: {len(buy_trades)}")
    print(f"Sell markers: {len(sell_trades)}")
    print(f"Total markers: {len(buy_trades) + len(sell_trades)}")

    # Verify all trades are included
    expected_markers = result['trades']  # Each trade should have 1 marker
    actual_markers = len(result['chart_data']['trades'])

    print("\n" + "=" * 50)
    if actual_markers >= expected_markers:
        print("✅ SUCCESS: All trades are included in chart markers!")
        print(f"   Expected at least {expected_markers} markers, got {actual_markers}")
        return True
    else:
        print("❌ FAILURE: Some trades are missing from chart markers!")
        print(f"   Expected at least {expected_markers} markers, got {actual_markers}")
        return False

if __name__ == "__main__":
    success = test_backtest_markers()
    sys.exit(0 if success else 1)

