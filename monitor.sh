#!/bin/bash
# System Monitoring Script

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
# The running bot's process id, from the lock file it holds (empty if not running)
bot_pid() {
    local pid
    pid=$(cat "$(dirname "$0")/data/bot.lock" 2>/dev/null)
    if [ -n "$pid" ] && ps -p "$pid" -o command= 2>/dev/null | grep -q "main.py"; then
        echo "$pid"
    fi
}

echo "========================================="
echo "Trading Bot Health Check"
echo "========================================="
echo ""

# Check if service is running
if launchctl list | grep -q "com.trading.bot"; then
    echo "✓ Service Status: RUNNING"
else
    echo "✗ Service Status: STOPPED"
fi

# Check process
PID=$(bot_pid)
if [ -n "$PID" ]; then
    echo "✓ Process ID: $PID"
    
    # CPU and Memory usage
    CPU=$(ps -p $PID -o %cpu | tail -1 | xargs)
    MEM=$(ps -p $PID -o %mem | tail -1 | xargs)
    echo "  CPU Usage: ${CPU}%"
    echo "  Memory Usage: ${MEM}%"
else
    echo "✗ Process not found"
fi

# Check logs for recent errors
echo ""
echo "Recent Errors (last 10):"
if [ -f "$PROJECT_DIR/logs/bot_error.log" ]; then
    tail -10 "$PROJECT_DIR/logs/bot_error.log" | grep -i error || echo "  No recent errors"
else
    echo "  No error log found"
fi

# Database size
if [ -f "$PROJECT_DIR/data/trading.db" ]; then
    DB_SIZE=$(du -h "$PROJECT_DIR/data/trading.db" | cut -f1)
    echo ""
    echo "Database Size: $DB_SIZE"
fi

# Disk space
echo ""
echo "Disk Space:"
df -h "$PROJECT_DIR" | tail -1

echo ""
echo "========================================="
