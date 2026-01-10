#!/usr/bin/env python3
"""Check all trades in database"""

from database import get_database, initialize_database

db = initialize_database()
trades = db.get_trades(limit=20)

print(f'Total trades in database: {len(trades)}')
print()

for i, trade in enumerate(trades):
    print(f'{i+1}. {trade.side.upper()} {trade.amount:.6f} BTC @ ${trade.price:.2f}')
    print(f'   Time: {trade.timestamp.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'   P&L: ${trade.pnl:.2f}' if trade.pnl else '   P&L: N/A')
    print()

