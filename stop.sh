#!/bin/bash

# Try to unload LaunchAgent if it's loaded
if launchctl list | grep -q "com.trading.bot"; then
    launchctl unload "$HOME/Library/LaunchAgents/com.trading.bot.plist"
    echo "✓ LaunchAgent service stopped"
fi

# Kill any remaining Python processes running main.py
PIDS=$(pgrep -f "Python main.py")
if [ ! -z "$PIDS" ]; then
    echo "Stopping bot processes: $PIDS"
    kill $PIDS 2>/dev/null
    sleep 1
    
    # Force kill if still running
    REMAINING=$(pgrep -f "Python main.py")
    if [ ! -z "$REMAINING" ]; then
        echo "Force stopping remaining processes: $REMAINING"
        kill -9 $REMAINING 2>/dev/null
    fi
fi

echo "✓ Trading bot stopped"
