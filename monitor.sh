#!/bin/bash

###################################################################
# Next-Gen Trading Bot - Monitoring Script
###################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$PROJECT_DIR/logs/bot.log"
ERROR_LOG="$PROJECT_DIR/logs/bot_error.log"
SERVICE_NAME="com.trading.bot"

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
    fi
}

# Check if service is running
check_service() {
    print_header "Service Status"
    
    if launchctl list | grep -q "$SERVICE_NAME"; then
        print_status 0 "Bot service is RUNNING"
        
        # Get PID
        PID=$(pgrep -f "python3.*main.py" | head -1)
        if [ ! -z "$PID" ]; then
            echo -e "  PID: $PID"
            
            # Get resource usage
            PS_OUTPUT=$(ps -p $PID -o %cpu,%mem,vsz,rss | tail -1)
            echo -e "  CPU: $(echo $PS_OUTPUT | awk '{print $1}')%"
            echo -e "  MEM: $(echo $PS_OUTPUT | awk '{print $2}')%"
            echo -e "  VSZ: $(echo $PS_OUTPUT | awk '{print $3}') KB"
            echo -e "  RSS: $(echo $PS_OUTPUT | awk '{print $4}') KB"
        fi
    else
        print_status 1 "Bot service is STOPPED"
    fi
}

# Check dashboard accessibility
check_dashboard() {
    print_header "Dashboard Health"
    
    # Try to connect to dashboard
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
        print_status 0 "Dashboard is accessible at http://localhost:8000"
    else
        print_status 1 "Dashboard is not accessible"
    fi
}

# Check logs for errors
check_errors() {
    print_header "Recent Errors"
    
    if [ -f "$ERROR_LOG" ]; then
        ERROR_COUNT=$(wc -l < "$ERROR_LOG" 2>/dev/null || echo "0")
        
        if [ "$ERROR_COUNT" -eq 0 ]; then
            print_status 0 "No errors in error log"
        else
            print_status 1 "Found $ERROR_COUNT lines in error log"
            echo -e "\n${YELLOW}Last 10 errors:${NC}"
            tail -10 "$ERROR_LOG"
        fi
    else
        print_status 0 "No error log file (no errors yet)"
    fi
}

# Check database
check_database() {
    print_header "Database Status"
    
    DB_FILE="$PROJECT_DIR/data/trading.db"
    
    if [ -f "$DB_FILE" ]; then
        DB_SIZE=$(du -h "$DB_FILE" | awk '{print $1}')
        print_status 0 "Database exists (Size: $DB_SIZE)"
        
        # Count trades
        TRADE_COUNT=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM trades;" 2>/dev/null || echo "0")
        echo -e "  Total trades: $TRADE_COUNT"
        
        # Get last trade time
        LAST_TRADE=$(sqlite3 "$DB_FILE" "SELECT timestamp FROM trades ORDER BY timestamp DESC LIMIT 1;" 2>/dev/null || echo "None")
        if [ "$LAST_TRADE" != "None" ] && [ ! -z "$LAST_TRADE" ]; then
            echo -e "  Last trade: $LAST_TRADE"
        else
            echo -e "  Last trade: No trades yet"
        fi
    else
        print_status 1 "Database file not found"
    fi
}

# Check disk space
check_disk() {
    print_header "Disk Space"
    
    DISK_USAGE=$(df -h "$PROJECT_DIR" | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [ "$DISK_USAGE" -lt 80 ]; then
        print_status 0 "Disk usage: ${DISK_USAGE}% (Healthy)"
    elif [ "$DISK_USAGE" -lt 90 ]; then
        print_status 1 "Disk usage: ${DISK_USAGE}% (Warning)"
    else
        print_status 1 "Disk usage: ${DISK_USAGE}% (Critical)"
    fi
}

# Check recent activity
check_activity() {
    print_header "Recent Activity"
    
    if [ -f "$LOG_FILE" ]; then
        LAST_MODIFIED=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOG_FILE" 2>/dev/null || echo "Unknown")
        echo -e "Last log update: $LAST_MODIFIED"
        
        echo -e "\n${YELLOW}Last 15 log lines:${NC}"
        tail -15 "$LOG_FILE"
    else
        print_status 1 "No log file found"
    fi
}

# Check network connectivity
check_network() {
    print_header "Network Connectivity"
    
    # Check internet
    if ping -c 1 -W 2 google.com &> /dev/null; then
        print_status 0 "Internet connectivity OK"
    else
        print_status 1 "No internet connectivity"
    fi
    
    # Check Binance API
    if curl -s --max-time 5 https://api.binance.us/api/v3/ping &> /dev/null; then
        print_status 0 "Binance API accessible"
    else
        print_status 1 "Cannot reach Binance API"
    fi
}

# Display trading stats
show_stats() {
    print_header "Trading Statistics"
    
    source "$PROJECT_DIR/venv/bin/activate"
    
    python3 << 'EOF'
import sys
sys.path.insert(0, '.')
try:
    from database import get_database
    
    db = get_database()
    stats = db.get_trade_stats()
    
    print(f"Total Trades: {stats.get('total_trades', 0)}")
    print(f"Win Rate: {stats.get('win_rate', 0):.2f}%")
    print(f"Total P&L: ${stats.get('total_pnl', 0):.2f}")
    print(f"Avg Trade P&L: ${stats.get('avg_pnl', 0):.2f}")
    
except Exception as e:
    print(f"Error fetching stats: {e}")
EOF
}

# Main monitoring function
run_full_check() {
    clear
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════╗"
    echo "║   Next-Gen Trading Bot - Health Monitor    ║"
    echo "║        $(date '+%Y-%m-%d %H:%M:%S')           ║"
    echo "╚════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    check_service
    check_dashboard
    check_database
    check_network
    check_disk
    show_stats
    check_errors
    check_activity
    
    echo -e "\n${GREEN}=== Health Check Complete ===${NC}\n"
}

# Watch mode - continuous monitoring
watch_mode() {
    while true; do
        run_full_check
        echo -e "\n${YELLOW}Refreshing in 30 seconds... (Press Ctrl+C to stop)${NC}"
        sleep 30
    done
}

# Parse arguments
case "${1:-full}" in
    full)
        run_full_check
        ;;
    watch)
        watch_mode
        ;;
    service)
        check_service
        ;;
    dashboard)
        check_dashboard
        ;;
    errors)
        check_errors
        ;;
    db)
        check_database
        ;;
    stats)
        show_stats
        ;;
    logs)
        check_activity
        ;;
    network)
        check_network
        ;;
    *)
        echo "Usage: $0 [full|watch|service|dashboard|errors|db|stats|logs|network]"
        echo ""
        echo "  full       - Run all health checks (default)"
        echo "  watch      - Continuous monitoring (refresh every 30s)"
        echo "  service    - Check service status only"
        echo "  dashboard  - Check dashboard accessibility"
        echo "  errors     - Show recent errors"
        echo "  db         - Check database status"
        echo "  stats      - Show trading statistics"
        echo "  logs       - Show recent logs"
        echo "  network    - Check network connectivity"
        exit 1
        ;;
esac





