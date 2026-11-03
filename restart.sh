#!/bin/bash
# Restarting kills the bot at once. Near the top of the hour it may be placing
# or recording an order (checks run at :00), and a restart that spans :00 skips
# that hour's check. So refuse from :58 to :03 unless FORCE=1.
MIN=$((10#$(date +%M)))
if [ "${FORCE:-0}" != "1" ] && { [ "$MIN" -ge 58 ] || [ "$MIN" -le 3 ]; }; then
    echo "⚠ It's $(date +%H:%M): too close to the hourly check. Try again after :03 (or FORCE=1 ./restart.sh)."
    exit 1
fi
cd "$(dirname "$0")"
./stop.sh
sleep 2
./start.sh
