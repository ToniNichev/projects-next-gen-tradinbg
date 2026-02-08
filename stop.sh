#!/bin/bash

SERVICE_NAME="com.trading.bot"

# Check if service is loaded
if ! launchctl print "gui/$(id -u)/${SERVICE_NAME}" &>/dev/null; then
    echo "⚠️  Service is not running"
    exit 0
fi

# Bootout (unload) the service
launchctl bootout "gui/$(id -u)/${SERVICE_NAME}" 2>&1

if [ $? -eq 0 ]; then
    echo "✓ Trading bot service stopped"
else
    echo "✗ Failed to stop service"
    echo "  Try: launchctl kill SIGTERM gui/$(id -u)/${SERVICE_NAME}"
    exit 1
fi
