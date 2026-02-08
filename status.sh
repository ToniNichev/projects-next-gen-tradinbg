#!/bin/bash

SERVICE_NAME="com.trading.bot"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "========================================="
echo "Trading Bot Service Status"
echo "========================================="
echo ""

# Check if service is loaded
if launchctl print "gui/$(id -u)/${SERVICE_NAME}" &>/dev/null; then
    echo "✓ Service Status: RUNNING"
    
    # Get PID
    PID=$(launchctl print "gui/$(id -u)/${SERVICE_NAME}" | grep -A 1 "pid" | tail -1 | awk '{print $3}')
    if [ -n "$PID" ] && [ "$PID" != "0" ]; then
        echo "  Process ID: $PID"
        
        # Get resource usage
        CPU=$(ps -p "$PID" -o %cpu 2>/dev/null | tail -1 | xargs)
        MEM=$(ps -p "$PID" -o %mem 2>/dev/null | tail -1 | xargs)
        if [ -n "$CPU" ]; then
            echo "  CPU Usage: ${CPU}%"
            echo "  Memory Usage: ${MEM}%"
        fi
    fi
else
    echo "✗ Service Status: STOPPED"
fi

echo ""
echo "Recent logs (last 20 lines):"
echo "-----------------------------------------"
if [ -f "$PROJECT_DIR/logs/bot.log" ]; then
    tail -20 "$PROJECT_DIR/logs/bot.log"
else
    echo "No logs found"
fi

echo ""
echo "========================================="
echo "Commands:"
echo "  ./start.sh   - Start service"
echo "  ./stop.sh    - Stop service"
echo "  ./restart.sh - Restart service"
echo "========================================="
