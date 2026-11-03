#!/bin/bash
# The running bot's process id, from the lock file it holds (empty if not running)
bot_pid() {
    local pid
    pid=$(cat "$(dirname "$0")/data/bot.lock" 2>/dev/null)
    if [ -n "$pid" ] && ps -p "$pid" -o command= 2>/dev/null | grep -q "main.py"; then
        echo "$pid"
    fi
}

# Try to unload LaunchAgent if it's loaded
if launchctl list | grep -q "com.trading.bot"; then
    launchctl unload "$HOME/Library/LaunchAgents/com.trading.bot.plist"
    echo "✓ LaunchAgent service stopped"
fi

# Kill any remaining Python processes running main.py
PIDS=$(bot_pid)
if [ ! -z "$PIDS" ]; then
    echo "Stopping bot processes: $PIDS"
    kill $PIDS 2>/dev/null
    sleep 1
    
    # Force kill if still running
    REMAINING=$(bot_pid)
    if [ ! -z "$REMAINING" ]; then
        echo "Force stopping remaining processes: $REMAINING"
        kill -9 $REMAINING 2>/dev/null
    fi
fi

echo "✓ Trading bot stopped"
