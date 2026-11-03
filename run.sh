#!/bin/bash
cd "$(dirname "$0")"
# The running bot's process id, from the lock file it holds (empty if not running)
bot_pid() {
    local pid
    pid=$(cat "$(dirname "$0")/data/bot.lock" 2>/dev/null)
    if [ -n "$pid" ] && ps -p "$pid" -o command= 2>/dev/null | grep -q "main.py"; then
        echo "$pid"
    fi
}

# Check if bot is already running
if [ -n "$(bot_pid)" ]; then
    echo "⚠ Trading bot is already running!"
    echo "Use ./stop.sh to stop it first, or ./status.sh to check status"
    exit 1
fi

source venv/bin/activate
python3 main.py
