#!/bin/bash

#############################################################
# Production Setup & Security Hardening
#############################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }

#############################################################
# Production Deployment
#############################################################

production_deploy() {
    print_header "🚀 Production Deployment"
    
    # 1. Check if .env exists
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        print_error ".env file not found!"
        echo "Creating from example..."
        if [ -f "$PROJECT_DIR/.env.example" ]; then
            cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        elif [ -f "$PROJECT_DIR/env.example" ]; then
            cp "$PROJECT_DIR/env.example" "$PROJECT_DIR/.env"
        fi
        print_warning "Please configure .env before continuing:"
        echo "  nano .env"
        exit 1
    fi
    
    # 2. Check for default/insecure values
    print_header "Security Check"
    
    if grep -q "your_api_key_here" "$PROJECT_DIR/.env"; then
        print_error "Default API key detected in .env"
        echo "  Please set BINANCE_US_KEY"
        exit 1
    fi
    
    if grep -q "your_secure_password_here" "$PROJECT_DIR/.env"; then
        print_warning "Default dashboard password detected"
        echo "  Consider setting a strong DASHBOARD_PASSWORD"
    fi
    
    # 3. Run deployment
    print_header "Running Deployment"
    "$PROJECT_DIR/deploy.sh" install
    
    # 4. Test configuration
    print_header "Testing Configuration"
    source "$PROJECT_DIR/venv/bin/activate"
    python3 -c "from config import BotConfig; config = BotConfig.load(); print('✓ Configuration loaded successfully')" || {
        print_error "Configuration test failed!"
        exit 1
    }
    
    print_success "Production deployment complete!"
}

#############################################################
# Security Hardening
#############################################################

harden_security() {
    print_header "🔒 Security Hardening"
    
    # 1. Set proper file permissions
    print_header "Setting File Permissions"
    
    # Protect .env file
    if [ -f "$PROJECT_DIR/.env" ]; then
        chmod 600 "$PROJECT_DIR/.env"
        print_success "Protected .env file (600)"
    fi
    
    # Protect data directory
    if [ -d "$PROJECT_DIR/data" ]; then
        chmod 700 "$PROJECT_DIR/data"
        print_success "Protected data directory (700)"
    fi
    
    # Protect database
    if [ -f "$PROJECT_DIR/data/trading.db" ]; then
        chmod 600 "$PROJECT_DIR/data/trading.db"
        print_success "Protected database file (600)"
    fi
    
    # Make scripts executable
    chmod +x "$PROJECT_DIR"/*.sh
    print_success "Made management scripts executable"
    
    # 2. Generate secure dashboard password
    print_header "Dashboard Security"
    
    read -p "Generate new secure dashboard password? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Generate random password
        NEW_PASSWORD=$(openssl rand -base64 16)
        echo -e "\n${GREEN}Generated secure password:${NC} ${YELLOW}$NEW_PASSWORD${NC}"
        echo "Please save this password securely!"
        echo ""
        read -p "Update .env with this password? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Update password in .env
            if grep -q "^DASHBOARD_PASSWORD=" "$PROJECT_DIR/.env"; then
                sed -i.bak "s|^DASHBOARD_PASSWORD=.*|DASHBOARD_PASSWORD=$NEW_PASSWORD|" "$PROJECT_DIR/.env"
            else
                echo "DASHBOARD_PASSWORD=$NEW_PASSWORD" >> "$PROJECT_DIR/.env"
            fi
            print_success "Password updated in .env"
        fi
    fi
    
    # 3. API Key recommendations
    print_header "API Security Recommendations"
    echo "1. Use Binance API keys with SPOT trading permissions only"
    echo "2. Enable IP whitelisting on Binance for your server IP"
    echo "3. Use read-only keys for initial testing"
    echo "4. Never commit .env to version control"
    
    # 4. Firewall configuration
    print_header "Firewall Configuration"
    echo "To secure your dashboard, consider:"
    echo ""
    echo "Option 1: Restrict to specific IPs (recommended)"
    echo "  - Configure firewall to allow port 8000 only from trusted IPs"
    echo ""
    echo "Option 2: Use SSH tunnel (very secure)"
    echo "  ssh -L 8000:localhost:8000 user@your-server"
    echo "  Then access: http://localhost:8000"
    echo ""
    
    read -p "Enable macOS firewall? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo defaults write /Library/Preferences/com.apple.alf globalstate -int 1
        print_success "macOS firewall enabled"
    fi
}

#############################################################
# Backup Setup
#############################################################

setup_backups() {
    print_header "📦 Backup Configuration"
    
    BACKUP_DIR="$PROJECT_DIR/backups"
    mkdir -p "$BACKUP_DIR"
    
    # Create backup script
    cat > "$PROJECT_DIR/backup.sh" << 'EOF'
#!/bin/bash
# Database and Configuration Backup Script

BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "Creating backup..."
tar -czf "$BACKUP_FILE" \
    --exclude='venv' \
    --exclude='backups' \
    --exclude='logs/*.log' \
    .env \
    data/ \
    *.py \
    requirements.txt

echo "✓ Backup created: $BACKUP_FILE"

# Keep only last 7 backups
ls -t "$BACKUP_DIR"/backup_*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null || true
echo "✓ Old backups cleaned up"
EOF
    chmod +x "$PROJECT_DIR/backup.sh"
    print_success "Created backup.sh script"
    
    # Setup automated daily backups
    read -p "Setup automated daily backups? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Create LaunchAgent for daily backups
        BACKUP_PLIST="$HOME/Library/LaunchAgents/com.trading.bot.backup.plist"
        cat > "$BACKUP_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.trading.bot.backup</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$PROJECT_DIR/backup.sh</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/backup.log</string>
    
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/backup_error.log</string>
</dict>
</plist>
EOF
        launchctl load "$BACKUP_PLIST"
        print_success "Automated daily backups enabled (runs at 2 AM)"
    fi
}

#############################################################
# Monitoring Setup
#############################################################

setup_monitoring() {
    print_header "📊 Monitoring Setup"
    
    # Create monitoring script
    cat > "$PROJECT_DIR/monitor.sh" << 'EOF'
#!/bin/bash
# System Monitoring Script

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

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
PID=$(pgrep -f "python3 main.py")
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
EOF
    chmod +x "$PROJECT_DIR/monitor.sh"
    print_success "Created monitor.sh script"
    
    echo ""
    echo "Run monitoring with: ./monitor.sh"
}

#############################################################
# Production Checklist
#############################################################

production_checklist() {
    print_header "✅ Production Deployment Checklist"
    
    echo "Pre-Deployment:"
    echo "  [ ] API credentials configured in .env"
    echo "  [ ] Strong dashboard password set"
    echo "  [ ] Risk management parameters configured"
    echo "  [ ] Tested in foreground mode (./run.sh)"
    echo ""
    
    echo "Security:"
    echo "  [ ] .env file permissions set to 600"
    echo "  [ ] Firewall configured"
    echo "  [ ] IP whitelisting enabled on Binance"
    echo "  [ ] Using HTTPS for dashboard (if external access)"
    echo ""
    
    echo "Monitoring:"
    echo "  [ ] Backup strategy configured"
    echo "  [ ] Log rotation setup"
    echo "  [ ] Monitoring script tested"
    echo "  [ ] Alert system configured (optional)"
    echo ""
    
    echo "Deployment:"
    echo "  [ ] Service auto-start enabled"
    echo "  [ ] Database initialized"
    echo "  [ ] Dashboard accessible"
    echo "  [ ] Verified service restarts on failure"
    echo ""
    
    read -p "Have you completed all items? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_success "Great! Ready for production deployment!"
    else
        print_warning "Please complete all checklist items before production deployment"
    fi
}

#############################################################
# Menu
#############################################################

show_menu() {
    clear
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════╗"
    echo "║     Production Setup & Deployment         ║"
    echo "╚════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "1) Full Production Deployment"
    echo "2) Security Hardening"
    echo "3) Setup Backups"
    echo "4) Setup Monitoring"
    echo "5) Production Checklist"
    echo "6) Quick Start (Deploy + Harden)"
    echo "0) Exit"
    echo ""
    read -p "Select an option: " choice
    
    case $choice in
        1) production_deploy ;;
        2) harden_security ;;
        3) setup_backups ;;
        4) setup_monitoring ;;
        5) production_checklist ;;
        6) 
            production_deploy
            harden_security
            setup_backups
            setup_monitoring
            production_checklist
            ;;
        0) 
            print_success "Goodbye!"
            exit 0
            ;;
        *)
            print_error "Invalid option"
            sleep 2
            show_menu
            ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
    show_menu
}

#############################################################
# Entry Point
#############################################################

if [ $# -eq 0 ]; then
    show_menu
else
    case $1 in
        deploy) production_deploy ;;
        security) harden_security ;;
        backup) setup_backups ;;
        monitor) setup_monitoring ;;
        checklist) production_checklist ;;
        all)
            production_deploy
            harden_security
            setup_backups
            setup_monitoring
            ;;
        *)
            echo "Usage: $0 [deploy|security|backup|monitor|checklist|all]"
            exit 1
            ;;
    esac
fi
