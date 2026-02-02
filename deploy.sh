#!/bin/bash

#############################################################
# Next-Gen Trading Bot - macOS Deployment Script
#############################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project configuration
PROJECT_NAME="next-gen-trading"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
DATA_DIR="$PROJECT_DIR/data"
LOG_DIR="$PROJECT_DIR/logs"
SERVICE_NAME="com.trading.bot"
PLIST_FILE="$HOME/Library/LaunchAgents/$SERVICE_NAME.plist"

#############################################################
# Helper Functions
#############################################################

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_command() {
    if command -v $1 &> /dev/null; then
        print_success "$1 is installed"
        return 0
    else
        print_error "$1 is not installed"
        return 1
    fi
}

#############################################################
# Pre-flight Checks
#############################################################

check_dependencies() {
    print_header "Checking System Dependencies"
    
    local missing_deps=0
    
    # Check Python 3
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | awk '{print $2}')
        print_success "Python 3 is installed (version $PYTHON_VERSION)"
    else
        print_error "Python 3 is not installed"
        echo "  Install with: brew install python3"
        missing_deps=1
    fi
    
    # Check pip
    if command -v pip3 &> /dev/null; then
        print_success "pip3 is installed"
    else
        print_error "pip3 is not installed"
        missing_deps=1
    fi
    
    # Check git (optional)
    check_command git || true
    
    if [ $missing_deps -eq 1 ]; then
        print_error "Missing required dependencies. Please install them first."
        exit 1
    fi
}

#############################################################
# Setup Functions
#############################################################

setup_directories() {
    print_header "Setting Up Directories"
    
    mkdir -p "$DATA_DIR"
    mkdir -p "$LOG_DIR"
    
    print_success "Created data directory: $DATA_DIR"
    print_success "Created logs directory: $LOG_DIR"
}

setup_virtualenv() {
    print_header "Setting Up Virtual Environment"
    
    if [ -d "$VENV_DIR" ]; then
        print_warning "Virtual environment already exists"
        read -p "Do you want to recreate it? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        else
            print_success "Using existing virtual environment"
            return 0
        fi
    fi
    
    python3 -m venv "$VENV_DIR"
    print_success "Virtual environment created at $VENV_DIR"
    
    # Activate and upgrade pip
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip setuptools wheel
    print_success "Updated pip, setuptools, and wheel"
}

install_dependencies() {
    print_header "Installing Python Dependencies"
    
    source "$VENV_DIR/bin/activate"
    
    if [ -f "$PROJECT_DIR/requirements.txt" ]; then
        pip install -r "$PROJECT_DIR/requirements.txt"
        print_success "Installed all dependencies from requirements.txt"
    else
        print_error "requirements.txt not found!"
        exit 1
    fi
}

setup_environment() {
    print_header "Setting Up Environment Configuration"
    
    if [ -f "$PROJECT_DIR/.env" ]; then
        print_warning ".env file already exists"
        read -p "Do you want to edit it? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            ${EDITOR:-nano} "$PROJECT_DIR/.env"
        fi
    else
        if [ -f "$PROJECT_DIR/env.example" ]; then
            cp "$PROJECT_DIR/env.example" "$PROJECT_DIR/.env"
            print_success "Created .env file from env.example"
            print_warning "Please edit .env and add your Binance API credentials:"
            echo -e "  ${YELLOW}nano $PROJECT_DIR/.env${NC}"
            read -p "Press Enter to continue..."
        else
            # Create a basic .env file
            cat > "$PROJECT_DIR/.env" << 'EOF'
# Binance API Credentials
BINANCE_US_KEY=your_api_key_here
BINANCE_US_SECRET=your_api_secret_here

# Trading Configuration
BOT_SYMBOL=BTC/USDT
BOT_TIMEFRAME=1h
BOT_INITIAL_USDT=1000.0

# Dashboard Configuration
BOT_DASHBOARD_HOST=0.0.0.0
BOT_DASHBOARD_PORT=8000

# Dashboard Security
DASHBOARD_AUTH_ENABLED=true
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=your_secure_password_here
DASHBOARD_API_KEY=your_api_key_here

# Database
BOT_DATABASE_URL=sqlite:///data/trading.db
BOT_ENABLE_DATABASE=true
BOT_ENABLE_CSV_LOGGING=true
EOF
            print_success "Created basic .env file"
            print_warning "Please edit .env and configure your settings:"
            echo -e "  ${YELLOW}nano $PROJECT_DIR/.env${NC}"
            read -p "Press Enter to continue..."
        fi
    fi
}

setup_database() {
    print_header "Setting Up Database"
    
    source "$VENV_DIR/bin/activate"
    
    # Check if database exists
    if [ -f "$DATA_DIR/trading.db" ]; then
        print_warning "Database already exists"
    else
        # Run database initialization
        python3 << 'EOF'
import sys
sys.path.insert(0, '.')
try:
    from database import initialize_database
    from config import BotConfig
    config = BotConfig.load()
    initialize_database(config.database_url)
    print("Database initialized successfully")
except Exception as e:
    print(f"Error initializing database: {e}")
    sys.exit(1)
EOF
        print_success "Database initialized"
    fi
}

create_launch_agent() {
    print_header "Creating macOS Launch Agent"
    
    # Ensure LaunchAgents directory exists
    mkdir -p "$HOME/Library/LaunchAgents"
    
    # Determine which Python executable to use
    PYTHON_EXECUTABLE="$VENV_DIR/bin/python3"
    if [ ! -f "$PYTHON_EXECUTABLE" ]; then
        print_warning "Virtual environment python executable not found at $PYTHON_EXECUTABLE"
        print_warning "Falling back to system python3"
        PYTHON_EXECUTABLE=$(command -v python3)
        if [ -z "$PYTHON_EXECUTABLE" ]; then
            print_error "System python3 not found. Please install Python 3."
            exit 1
        fi
        print_success "Using system Python: $PYTHON_EXECUTABLE"
    else
        print_success "Using venv Python: $PYTHON_EXECUTABLE"
    fi
    
    # Create the plist file
    cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$SERVICE_NAME</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_EXECUTABLE</string>
        <string>$PROJECT_DIR/main.py</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    
    <key>StandardOutPath</key>
    <string>$LOG_DIR/bot.log</string>
    
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/bot_error.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    
    <key>ProcessType</key>
    <string>Background</string>
    
    <key>Nice</key>
    <integer>0</integer>
</dict>
</plist>
EOF
    
    print_success "Created Launch Agent: $PLIST_FILE"
}

create_management_scripts() {
    print_header "Creating Management Scripts"
    
    # Start script
    cat > "$PROJECT_DIR/start.sh" << 'EOF'
#!/bin/bash
launchctl load "$HOME/Library/LaunchAgents/com.trading.bot.plist"
echo "✓ Trading bot service started"
echo "  View logs: tail -f logs/bot.log"
echo "  Dashboard: http://localhost:8000"
EOF
    chmod +x "$PROJECT_DIR/start.sh"
    
    # Stop script
    cat > "$PROJECT_DIR/stop.sh" << 'EOF'
#!/bin/bash
launchctl unload "$HOME/Library/LaunchAgents/com.trading.bot.plist"
echo "✓ Trading bot service stopped"
EOF
    chmod +x "$PROJECT_DIR/stop.sh"
    
    # Status script
    cat > "$PROJECT_DIR/status.sh" << 'EOF'
#!/bin/bash
if launchctl list | grep -q "com.trading.bot"; then
    echo "✓ Trading bot service is RUNNING"
    echo ""
    echo "Recent logs:"
    tail -20 logs/bot.log
else
    echo "✗ Trading bot service is STOPPED"
fi
EOF
    chmod +x "$PROJECT_DIR/status.sh"
    
    # Restart script
    cat > "$PROJECT_DIR/restart.sh" << 'EOF'
#!/bin/bash
./stop.sh
sleep 2
./start.sh
EOF
    chmod +x "$PROJECT_DIR/restart.sh"
    
    # Run script (for foreground testing)
    cat > "$PROJECT_DIR/run.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python3 main.py
EOF
    chmod +x "$PROJECT_DIR/run.sh"
    
    print_success "Created management scripts:"
    echo "  - start.sh    : Start bot as background service"
    echo "  - stop.sh     : Stop background service"
    echo "  - restart.sh  : Restart background service"
    echo "  - status.sh   : Check service status and view logs"
    echo "  - run.sh      : Run bot in foreground (for testing)"
}

#############################################################
# Main Installation
#############################################################

full_install() {
    print_header "Starting Full Installation"
    
    check_dependencies
    setup_directories
    setup_virtualenv
    install_dependencies
    setup_environment
    setup_database
    create_launch_agent
    create_management_scripts
    
    print_header "Installation Complete! 🎉"
    
    echo -e "${GREEN}Next Steps:${NC}"
    echo ""
    echo "1. Configure your settings:"
    echo -e "   ${YELLOW}nano .env${NC}"
    echo ""
    echo "2. Test the bot in foreground:"
    echo -e "   ${YELLOW}./run.sh${NC}"
    echo ""
    echo "3. Start as background service:"
    echo -e "   ${YELLOW}./start.sh${NC}"
    echo ""
    echo "4. View dashboard:"
    echo -e "   ${YELLOW}http://localhost:8000${NC}"
    echo ""
    echo "5. Check logs:"
    echo -e "   ${YELLOW}tail -f logs/bot.log${NC}"
    echo ""
    echo -e "${BLUE}Management Commands:${NC}"
    echo "  ./start.sh    - Start bot service"
    echo "  ./stop.sh     - Stop bot service"
    echo "  ./restart.sh  - Restart bot service"
    echo "  ./status.sh   - Check status and view logs"
    echo "  ./run.sh      - Run in foreground (testing)"
}

#############################################################
# Menu System
#############################################################

show_menu() {
    clear
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════╗"
    echo "║   Next-Gen Trading Bot - Deployment       ║"
    echo "║            macOS Server Setup              ║"
    echo "╚════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    echo "1) Full Installation (Recommended)"
    echo "2) Check Dependencies"
    echo "3) Setup Virtual Environment"
    echo "4) Install Dependencies Only"
    echo "5) Setup Environment File (.env)"
    echo "6) Initialize Database"
    echo "7) Create Launch Agent (Service)"
    echo "8) Create Management Scripts"
    echo "9) Run Bot (Foreground - Testing)"
    echo "0) Exit"
    echo ""
    read -p "Select an option: " choice
    
    case $choice in
        1) full_install ;;
        2) check_dependencies ;;
        3) setup_directories && setup_virtualenv ;;
        4) install_dependencies ;;
        5) setup_environment ;;
        6) setup_database ;;
        7) create_launch_agent ;;
        8) create_management_scripts ;;
        9) 
            source "$VENV_DIR/bin/activate"
            python3 main.py
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
# Script Entry Point
#############################################################

# If no arguments, show menu
if [ $# -eq 0 ]; then
    show_menu
else
    # Allow direct command execution
    case $1 in
        install|full)
            full_install
            ;;
        check)
            check_dependencies
            ;;
        venv)
            setup_directories
            setup_virtualenv
            ;;
        deps)
            install_dependencies
            ;;
        env)
            setup_environment
            ;;
        db)
            setup_database
            ;;
        service)
            create_launch_agent
            ;;
        scripts)
            create_management_scripts
            ;;
        run)
            source "$VENV_DIR/bin/activate"
            python3 main.py
            ;;
        *)
            echo "Usage: $0 [install|check|venv|deps|env|db|service|scripts|run]"
            echo ""
            echo "  install  - Full installation"
            echo "  check    - Check dependencies"
            echo "  venv     - Setup virtual environment"
            echo "  deps     - Install Python dependencies"
            echo "  env      - Setup environment file"
            echo "  db       - Initialize database"
            echo "  service  - Create macOS service"
            echo "  scripts  - Create management scripts"
            echo "  run      - Run bot in foreground"
            echo ""
            echo "Or run without arguments for interactive menu."
            exit 1
            ;;
    esac
fi

