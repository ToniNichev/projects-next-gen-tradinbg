#!/usr/bin/env python3
"""
Add 5 recent test trades (within last 24 hours) for immediate chart testing.
"""

import random
from datetime import datetime, timedelta, timezone
from database import get_database, initialize_database

def generate_recent_trades():
    """Generate 5 trades within the last 24 hours"""

    # Initialize database
    db = initialize_database()

    # Current time as reference
    now = datetime.now(timezone.utc)

    # Base BTC price around current market levels (~$55k-$65k)
    base_price = 60000.0

    # Generate 5 trades within last 24 hours
    trades = []

    for i in range(5):
        # Spread trades over last 24 hours (randomly distributed)
        hours_back = random.uniform(1, 24)
        timestamp = now - timedelta(hours=hours_back)

        # Random price variation (±$2000)
        price = base_price + random.uniform(-2000, 2000)

        # Alternate between buy and sell
        side = "buy" if i % 2 == 0 else "sell"

        # Random amount (0.001 to 0.01 BTC)
        amount = round(random.uniform(0.001, 0.01), 6)

        # Calculate notional value
        notional = price * amount

        # Fee (0.1% typical exchange fee)
        fee = notional * 0.001

        # Slippage (small random variation)
        slippage = random.uniform(-0.0001, 0.0001) * notional

        # Realistic balances (starting with ~$1000 USDT and 0.1 BTC)
        usdt_balance = round(random.uniform(500, 1500), 2)
        base_balance = round(random.uniform(0.01, 0.2), 6)

        # Exit reason for sell trades
        exit_reason = random.choice(["take_profit", "stop_loss", "signal", "trailing_stop"]) if side == "sell" else None

        # P&L for sell trades (realistic profit/loss)
        pnl = None
        if side == "sell":
            pnl = round(random.uniform(-50, 150), 2)

        # Signal data
        signal_direction = random.choice(["bullish", "bearish"])
        signal_price = price
        short_ema = price + random.uniform(-500, 500)
        long_ema = price + random.uniform(-1000, 1000)
        trend_strength = random.uniform(0.1, 1.0)
        rsi = random.uniform(20, 80)
        atr = random.uniform(500, 2000)
        position_size = random.uniform(0.1, 0.5)
        stop_loss = price * (0.98 if side == "buy" else 1.02)
        take_profit = price * (1.04 if side == "buy" else 0.96)

        trade_data = {
            "timestamp": timestamp,
            "side": side,
            "price": round(price, 2),
            "amount": amount,
            "notional": round(notional, 2),
            "fee": round(fee, 4),
            "slippage": round(slippage, 4),
            "usdt_balance": usdt_balance,
            "base_balance": base_balance,
            "exit_reason": exit_reason,
            "pnl": pnl,
            "signal_direction": signal_direction,
            "signal_price": round(signal_price, 2),
            "short_ema": round(short_ema, 2),
            "long_ema": round(long_ema, 2),
            "trend_strength": round(trend_strength, 3),
            "rsi": round(rsi, 2),
            "atr": round(atr, 2),
            "position_size": round(position_size, 3),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
        }

        trades.append((timestamp, trade_data))

    # Sort trades by timestamp (oldest first)
    trades.sort(key=lambda x: x[0])

    print(f"Adding {len(trades)} recent test trades (within last 24 hours)...")

    # Add trades to database
    for i, (timestamp, trade_data) in enumerate(trades):
        try:
            db.add_trade(trade_data)
            side = trade_data['side']
            amount = trade_data['amount']
            price = trade_data['price']
            hours_ago = (now - timestamp).total_seconds() / 3600
            print(f"✅ Added {side.upper()} trade #{i+1}: {amount:.6f} BTC @ ${price:.2f} ({hours_ago:.1f} hours ago)")
        except Exception as e:
            print(f"❌ Failed to add trade #{i+1}: {e}")

    print("\nRecent test trades added successfully!")
    print("You should now see trade markers on the chart at /ui")

if __name__ == "__main__":
    generate_recent_trades()
