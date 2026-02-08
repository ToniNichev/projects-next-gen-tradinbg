#!/bin/bash

SERVICE_NAME="com.trading.bot"
PLIST_PATH="$HOME/Library/LaunchAgents/${SERVICE_NAME}.plist"

# Check if already loaded
if launchctl print "gui/$(id -u)/${SERVICE_NAME}" &>/dev/null; then
    echo "⚠️  Service is already running"
    echo "   Use ./restart.sh to restart"
    exit 0
fi

# Bootstrap (load) the service
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH" 2>&1

if [ $? -eq 0 ]; then
    echo "✓ Trading bot service started"
    echo "  View logs: tail -f logs/bot.log"
    echo "  Dashboard: http://localhost:8000"
else
    echo "✗ Failed to start service"
    echo "  Check: launchctl print gui/$(id -u)/${SERVICE_NAME}"
    exit 1
fi
