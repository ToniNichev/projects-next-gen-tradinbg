#!/bin/bash
cd "$(dirname "$0")"

# Check if bot is already running
if pgrep -f "Python main.py" > /dev/null; then
    echo "⚠ Trading bot is already running!"
    echo "Use ./stop.sh to stop it first, or ./status.sh to check status"
    exit 1
fi

source venv/bin/activate
python3 main.py
