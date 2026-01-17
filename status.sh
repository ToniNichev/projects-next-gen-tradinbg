#!/bin/bash
if launchctl list | grep -q "com.trading.bot"; then
    echo "✓ Trading bot service is RUNNING"
    echo ""
    echo "Recent logs:"
    tail -20 logs/bot.log
else
    echo "✗ Trading bot service is STOPPED"
fi
