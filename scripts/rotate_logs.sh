#!/bin/bash
# rotate_logs.sh — truncate launchd-captured stdout/stderr log files in
# place if they exceed a size threshold.
#
# The bot's own logs are managed by Python's RotatingFileHandler
# (see _configure_logging in main.py) and rotate automatically.
# However, launchd's StandardOutPath/StandardErrorPath files
# (logs/bot.log and logs/bot_error.log) are NOT rotated by launchd
# itself. Renaming or removing them is unsafe because launchd holds
# the file descriptors open with O_APPEND and would keep writing to
# the renamed inode.
#
# Truncating in place (`: > file`) preserves the inode and is safe
# while the bot is running.
#
# Usage:
#   ./scripts/rotate_logs.sh [MAX_BYTES]
#
# Schedule via cron, e.g. hourly:
#   0 * * * * /path/to/repo/scripts/rotate_logs.sh

set -euo pipefail

MAX_BYTES="${1:-10485760}"  # default 10 MB

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$REPO_DIR/logs"

if [ ! -d "$LOG_DIR" ]; then
    echo "No logs directory at $LOG_DIR" >&2
    exit 0
fi

for f in "$LOG_DIR/bot.log" "$LOG_DIR/bot_error.log"; do
    [ -f "$f" ] || continue
    size=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f")
    if [ "$size" -gt "$MAX_BYTES" ]; then
        echo "Truncating $f ($size bytes > $MAX_BYTES)"
        : > "$f"
    fi
done
