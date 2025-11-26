#!/usr/bin/env python3
"""Verify test trades were added to database"""

from database import get_database, initialize_database

db = initialize_database()
trades = db.get_trades(limit=10)

print(f'Found {len(trades)} trades in database:')
for i, trade in enumerate(trades):
    print(f'{i+1}. {trade.side.upper()} {trade.amount:.6f} BTC @ ${trade.price:.2f} on {trade.timestamp.strftime("%Y-%m-%d %H:%M")}')
