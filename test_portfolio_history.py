#!/usr/bin/env python3
"""
Test script to verify the portfolio history API endpoint.
Run after restarting the bot to test the new endpoint.
"""

import requests
import json
from datetime import datetime

# Dashboard URL (update if needed)
DASHBOARD_URL = "http://localhost:8000"
USERNAME = "admin"
PASSWORD = "changeme"

def test_portfolio_history():
    """Test the portfolio history endpoint"""
    print("Testing portfolio history API endpoint...")
    print(f"URL: {DASHBOARD_URL}/api/portfolio/history")
    print()
    
    try:
        # Make request with authentication
        response = requests.get(
            f"{DASHBOARD_URL}/api/portfolio/history?limit=100",
            auth=(USERNAME, PASSWORD),
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Success! Retrieved {data.get('count', 0)} portfolio history points")
            
            if data.get('history'):
                print("\nFirst 3 portfolio snapshots:")
                for i, point in enumerate(data['history'][:3]):
                    timestamp = datetime.fromisoformat(point['timestamp'].replace('Z', '+00:00'))
                    print(f"  {i+1}. {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - "
                          f"Portfolio: ${point['value']:.2f} "
                          f"(${point['usdt_balance']:.2f} USDT + {point['base_balance']:.6f} BTC @ ${point['price']:.2f})")
                
                if len(data['history']) > 3:
                    print(f"\n  ... and {len(data['history']) - 3} more points")
            else:
                print("\n⚠ No trade history available yet. This is normal if no trades have been executed.")
            
            return True
        elif response.status_code == 401:
            print("✗ Authentication failed. Check USERNAME and PASSWORD in this script.")
            return False
        else:
            print(f"✗ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("✗ Connection failed. Is the bot running?")
        print("  Start the bot with: python3 main.py")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_dashboard_ui():
    """Test that the dashboard UI is accessible"""
    print("\n" + "="*60)
    print("Testing dashboard UI...")
    print(f"URL: {DASHBOARD_URL}/ui")
    print()
    
    try:
        response = requests.get(
            f"{DASHBOARD_URL}/ui",
            auth=(USERNAME, PASSWORD),
            timeout=10
        )
        
        if response.status_code == 200:
            print("✓ Dashboard UI is accessible")
            print(f"\nOpen in browser: {DASHBOARD_URL}/ui")
            print("The portfolio chart should now show accurate historical data!")
            return True
        else:
            print(f"✗ Dashboard returned status {response.status_code}")
            return False
            
    except Exception as e:
        print(f"✗ Error accessing dashboard: {e}")
        return False


if __name__ == "__main__":
    print("="*60)
    print("Portfolio History API Test")
    print("="*60)
    print()
    
    # Test the API endpoint
    api_ok = test_portfolio_history()
    
    # Test the dashboard UI
    ui_ok = test_dashboard_ui()
    
    print("\n" + "="*60)
    if api_ok and ui_ok:
        print("✓ All tests passed!")
        print("\nNext steps:")
        print("1. Open the dashboard in your browser")
        print("2. Check the portfolio value line on the chart")
        print("3. It should now show actual trade-by-trade progression")
        print("4. The line will change as trades are executed")
    else:
        print("⚠ Some tests failed. Check the output above.")
        print("\nTo restart the bot:")
        print("  1. Press Ctrl+C in the terminal running main.py")
        print("  2. Run: python3 main.py")
    print("="*60)


