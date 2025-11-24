#!/bin/bash

###################################################################
# Next-Gen Trading Bot - Backup Script
###################################################################

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_BASE_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="$BACKUP_BASE_DIR/backup-$TIMESTAMP"

print_header() {
    echo -e "\n${BLUE}=== $1 ===${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

print_header "Starting Backup"

# Backup database
if [ -f "$PROJECT_DIR/data/trading.db" ]; then
    echo "Backing up database..."
    cp "$PROJECT_DIR/data/trading.db" "$BACKUP_DIR/trading.db"
    
    # Also create SQL dump for portability
    sqlite3 "$PROJECT_DIR/data/trading.db" .dump > "$BACKUP_DIR/trading.sql"
    
    print_success "Database backed up"
fi

# Backup CSV logs
if [ -f "$PROJECT_DIR/data/trade_log.csv" ]; then
    echo "Backing up trade log..."
    cp "$PROJECT_DIR/data/trade_log.csv" "$BACKUP_DIR/trade_log.csv"
    print_success "Trade log backed up"
fi

if [ -f "$PROJECT_DIR/data/backtest_log.csv" ]; then
    echo "Backing up backtest log..."
    cp "$PROJECT_DIR/data/backtest_log.csv" "$BACKUP_DIR/backtest_log.csv"
    print_success "Backtest log backed up"
fi

# Backup configuration (without sensitive data)
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "Backing up configuration..."
    # Remove sensitive keys from backup
    grep -v "BINANCE_US_KEY\|BINANCE_US_SECRET\|DASHBOARD_PASSWORD\|DASHBOARD_API_KEY" "$PROJECT_DIR/.env" > "$BACKUP_DIR/config.txt"
    print_success "Configuration backed up (sensitive data excluded)"
fi

# Backup logs (last 1000 lines)
if [ -f "$PROJECT_DIR/logs/bot.log" ]; then
    echo "Backing up recent logs..."
    tail -1000 "$PROJECT_DIR/logs/bot.log" > "$BACKUP_DIR/bot.log"
    print_success "Logs backed up"
fi

# Create backup info file
cat > "$BACKUP_DIR/backup-info.txt" << EOF
Backup Information
==================
Date: $(date)
Hostname: $(hostname)
User: $(whoami)
Project Directory: $PROJECT_DIR

Backed up files:
$(ls -lh "$BACKUP_DIR")

Database Stats:
$([ -f "$PROJECT_DIR/data/trading.db" ] && sqlite3 "$PROJECT_DIR/data/trading.db" "SELECT COUNT(*) as total_trades FROM trades;" || echo "No database")
EOF

# Compress backup
echo -e "\nCompressing backup..."
cd "$BACKUP_BASE_DIR"
tar -czf "backup-$TIMESTAMP.tar.gz" "backup-$TIMESTAMP"
rm -rf "backup-$TIMESTAMP"

BACKUP_SIZE=$(du -h "backup-$TIMESTAMP.tar.gz" | awk '{print $1}')

print_header "Backup Complete"

print_success "Backup created: $BACKUP_BASE_DIR/backup-$TIMESTAMP.tar.gz"
echo -e "  Size: $BACKUP_SIZE"

# Clean old backups (keep last 10)
BACKUP_COUNT=$(ls -1 "$BACKUP_BASE_DIR"/backup-*.tar.gz 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 10 ]; then
    echo -e "\n${YELLOW}Cleaning old backups (keeping last 10)...${NC}"
    ls -t "$BACKUP_BASE_DIR"/backup-*.tar.gz | tail -n +11 | xargs rm -f
    print_success "Old backups cleaned"
fi

echo -e "\n${GREEN}All data backed up successfully!${NC}\n"

# Show restore instructions
echo "To restore from this backup:"
echo "  tar -xzf $BACKUP_BASE_DIR/backup-$TIMESTAMP.tar.gz"
echo "  cd backup-$TIMESTAMP"
echo "  cp trading.db ../data/"
echo ""


