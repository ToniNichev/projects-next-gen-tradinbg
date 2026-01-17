#!/bin/bash
launchctl load "$HOME/Library/LaunchAgents/com.trading.bot.plist"
echo "✓ Trading bot service started"
echo "  View logs: tail -f logs/bot.log"
echo "  Dashboard: http://localhost:8000"
