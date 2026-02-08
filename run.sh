#!/bin/bash

# Run script for Next-Gen Trading Bot

cd "$(dirname "$0")"

# Check if virtual environment exists and use it, otherwise use system Python
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    echo "✓ Using virtual environment"
    source venv/bin/activate
else
    echo "ℹ️  Using system Python (run ./setup.sh to create virtual environment)"
fi

# Run the trading bot
python3 main.py
