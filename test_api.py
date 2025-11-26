#!/usr/bin/env python3
"""Test if the trades API is working"""

import requests
import json

try:
    response = requests.get('http://localhost:5000/api/trades?limit=10')
    if response.status_code == 200:
        data = response.json()
        trades = data.get('trades', [])
        print(f"API returned {len(trades)} trades")
        for i, trade in enumerate(trades[:5]):  # Show first 5
            print(f"{i+1}. {trade['side']} {trade['amount']:.6f} BTC @ ${trade['price']:.2f}")
            print(f"   Time: {trade['timestamp']}")
    else:
        print(f"API returned status {response.status_code}")
        print(f"Response: {response.text}")
except Exception as e:
    print(f"Could not connect to API: {e}")
    print("Make sure the server is running with: python3 main.py")
