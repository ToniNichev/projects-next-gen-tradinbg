#!/bin/bash

###################################################################
# Next-Gen Trading Bot - Uninstall Script
###################################################################

set -e

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="com.trading.bot"
PLIST_FILE="$HOME/Library/LaunchAgents/$SERVICE_NAME.plist"

echo -e "${YELLOW}"
echo "╔════════════════════════════════════════════╗"
echo "║   Next-Gen Trading Bot - Uninstaller       ║"
echo "╚════════════════════════════════════════════╝"
echo -e "${NC}\n"

echo -e "${RED}WARNING: This will remove the trading bot and potentially your data!${NC}\n"

# Show what will be removed
echo "The following will be removed:"
echo "  - LaunchAgent service"
echo "  - Virtual environment"
echo "  - Log files"
echo ""
echo "The following will be PRESERVED (you can delete manually):"
echo "  - Database (data/trading.db)"
echo "  - Trade logs (data/trade_log.csv)"
echo "  - Configuration (.env)"
echo ""

read -p "Are you sure you want to continue? (type 'yes' to confirm): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "\n${GREEN}Uninstall cancelled.${NC}"
    exit 0
fi

echo -e "\n${YELLOW}Starting uninstall...${NC}\n"

# Stop and remove service
if [ -f "$PLIST_FILE" ]; then
    echo "Stopping service..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    
    echo "Removing LaunchAgent..."
    rm "$PLIST_FILE"
    echo -e "${GREEN}✓ Service removed${NC}"
else
    echo -e "${YELLOW}⚠ Service not found (already removed?)${NC}"
fi

# Remove virtual environment
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "Removing virtual environment..."
    rm -rf "$PROJECT_DIR/venv"
    echo -e "${GREEN}✓ Virtual environment removed${NC}"
fi

# Remove log files
if [ -d "$PROJECT_DIR/logs" ]; then
    echo "Removing log files..."
    rm -rf "$PROJECT_DIR/logs"
    echo -e "${GREEN}✓ Log files removed${NC}"
fi

# Remove management scripts
echo "Removing management scripts..."
rm -f "$PROJECT_DIR/start.sh"
rm -f "$PROJECT_DIR/stop.sh"
rm -f "$PROJECT_DIR/restart.sh"
rm -f "$PROJECT_DIR/status.sh"
rm -f "$PROJECT_DIR/run.sh"
echo -e "${GREEN}✓ Management scripts removed${NC}"

# Optional: Remove data
echo ""
read -p "Do you want to remove data directory (database and trade logs)? (y/N): " -n 1 -r REMOVE_DATA
echo

if [[ $REMOVE_DATA =~ ^[Yy]$ ]]; then
    if [ -d "$PROJECT_DIR/data" ]; then
        echo "Creating backup..."
        BACKUP_DIR="$PROJECT_DIR/data-backup-$(date +%Y%m%d-%H%M%S)"
        cp -r "$PROJECT_DIR/data" "$BACKUP_DIR"
        echo -e "${GREEN}✓ Backup created: $BACKUP_DIR${NC}"
        
        echo "Removing data directory..."
        rm -rf "$PROJECT_DIR/data"
        echo -e "${GREEN}✓ Data directory removed${NC}"
    fi
else
    echo -e "${GREEN}✓ Data directory preserved${NC}"
fi

# Optional: Remove configuration
echo ""
read -p "Do you want to remove configuration file (.env)? (y/N): " -n 1 -r REMOVE_CONFIG
echo

if [[ $REMOVE_CONFIG =~ ^[Yy]$ ]]; then
    if [ -f "$PROJECT_DIR/.env" ]; then
        echo "Creating backup..."
        cp "$PROJECT_DIR/.env" "$PROJECT_DIR/.env.backup-$(date +%Y%m%d-%H%M%S)"
        echo -e "${GREEN}✓ Backup created${NC}"
        
        echo "Removing .env file..."
        rm "$PROJECT_DIR/.env"
        echo -e "${GREEN}✓ Configuration removed${NC}"
    fi
else
    echo -e "${GREEN}✓ Configuration preserved${NC}"
fi

# Summary
echo -e "\n${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║      Uninstall Complete!                   ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}\n"

echo "What was removed:"
echo "  ✓ LaunchAgent service"
echo "  ✓ Virtual environment"
echo "  ✓ Log files"
echo "  ✓ Management scripts"

if [[ $REMOVE_DATA =~ ^[Yy]$ ]]; then
    echo "  ✓ Data directory (backup created)"
fi

if [[ $REMOVE_CONFIG =~ ^[Yy]$ ]]; then
    echo "  ✓ Configuration file (backup created)"
fi

echo ""
echo "To completely remove the bot, delete this directory:"
echo -e "  ${YELLOW}rm -rf $PROJECT_DIR${NC}"
echo ""
echo "Thank you for using Next-Gen Trading Bot! 👋"


