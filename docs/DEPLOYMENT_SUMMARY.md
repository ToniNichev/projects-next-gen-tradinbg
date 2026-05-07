# Deployment Scripts - Summary

This document provides an overview of all deployment-related files created for running the trading bot on macOS.

## 📦 Created Files

### Main Deployment Script
- **`deploy.sh`** - Main deployment and setup script with interactive menu

### Management Scripts
- **`start.sh`** - Start the bot as a background service
- **`stop.sh`** - Stop the bot service
- **`restart.sh`** - Restart the bot service
- **`status.sh`** - Check service status and view recent logs
- **`run.sh`** - Run the bot in foreground (for testing)

### Monitoring & Maintenance
- **`monitor.sh`** - Comprehensive health monitoring script
- **`backup.sh`** - Backup all data and configuration
- **`uninstall.sh`** - Clean uninstall script

### Documentation
- **`QUICKSTART.md`** - Quick start guide (5-minute setup)
- **`DEPLOYMENT.md`** - Comprehensive deployment documentation
- **`DEPLOYMENT_SUMMARY.md`** - This file

## 🚀 Quick Reference

### Initial Setup
```bash
./deploy.sh install
```

### Daily Operations
```bash
./start.sh              # Start bot
./stop.sh               # Stop bot
./restart.sh            # Restart bot
./status.sh             # Check status
./monitor.sh            # Health check
./backup.sh             # Backup data
./run.sh                # Test in foreground
```

### Monitoring
```bash
./monitor.sh            # Full health check
./monitor.sh watch      # Continuous monitoring
./monitor.sh service    # Service status only
./monitor.sh dashboard  # Dashboard health
./monitor.sh stats      # Trading statistics
./monitor.sh errors     # Recent errors
./monitor.sh logs       # Recent logs
./monitor.sh network    # Network connectivity
```

## 📁 Directory Structure

After deployment, your project structure will look like:

```
next-gen-trading/
├── deploy.sh              # Main deployment script
├── start.sh               # Start service
├── stop.sh                # Stop service
├── restart.sh             # Restart service
├── status.sh              # Check status
├── run.sh                 # Run in foreground
├── monitor.sh             # Health monitoring
├── backup.sh              # Backup script
├── uninstall.sh           # Uninstall script
│
├── venv/                  # Virtual environment (created by deploy.sh)
├── logs/                  # Log files (created by deploy.sh)
│   ├── bot.log           # Main log
│   └── bot_error.log     # Error log
│
├── data/                  # Data directory
│   ├── trading.db        # SQLite database
│   ├── trade_log.csv     # CSV trade log
│   └── backtest_log.csv  # Backtest results
│
├── backups/               # Backup directory (created by backup.sh)
│   └── backup-*.tar.gz   # Compressed backups
│
├── .env                   # Configuration (DO NOT COMMIT)
├── env.example            # Example configuration
│
├── main.py                # Main bot entry point
├── dashboard.py           # Web dashboard
├── config.py              # Configuration handler
├── strategy.py            # Trading strategy
├── paper_trader.py        # Paper trading engine
├── database.py            # Database interface
├── auth.py                # Authentication
├── backtest.py            # Backtesting engine
│
├── templates/             # HTML templates
│   ├── ui.html           # Main dashboard
│   ├── settings.html     # Settings page
│   ├── backtest.html     # Backtest page
│   └── ...
│
├── requirements.txt       # Python dependencies
├── README.md              # Main documentation
├── QUICKSTART.md          # Quick start guide
├── DEPLOYMENT.md          # Full deployment guide
└── DEPLOYMENT_SUMMARY.md  # This file
```

## 🔧 Script Details

### deploy.sh

**Purpose:** Main deployment script with interactive menu

**Features:**
- Dependency checking
- Virtual environment setup
- Dependency installation
- Environment configuration
- Database initialization
- macOS LaunchAgent creation
- Management script generation

**Usage:**
```bash
# Interactive menu
./deploy.sh

# Direct commands
./deploy.sh install    # Full installation
./deploy.sh check      # Check dependencies
./deploy.sh venv       # Setup virtualenv
./deploy.sh deps       # Install dependencies
./deploy.sh env        # Setup .env file
./deploy.sh db         # Initialize database
./deploy.sh service    # Create LaunchAgent
./deploy.sh scripts    # Create management scripts
./deploy.sh run        # Run in foreground
```

### Management Scripts

#### start.sh
Loads the LaunchAgent to start the bot as a background service.

```bash
./start.sh
```

#### stop.sh
Unloads the LaunchAgent to stop the bot service.

```bash
./stop.sh
```

#### restart.sh
Stops and then starts the bot service.

```bash
./restart.sh
```

#### status.sh
Checks if the service is running and shows recent log entries.

```bash
./status.sh
```

#### run.sh
Runs the bot in the foreground (useful for testing and debugging).

```bash
./run.sh
# Press Ctrl+C to stop
```

### monitor.sh

**Purpose:** Comprehensive health monitoring and diagnostics

**Features:**
- Service status check
- Dashboard accessibility test
- Error log analysis
- Database status
- Disk space monitoring
- Network connectivity check
- Trading statistics
- Recent activity log

**Usage:**
```bash
# Full health check
./monitor.sh
./monitor.sh full

# Continuous monitoring (refreshes every 30s)
./monitor.sh watch

# Specific checks
./monitor.sh service     # Check if service is running
./monitor.sh dashboard   # Test dashboard accessibility
./monitor.sh errors      # Show recent errors
./monitor.sh db          # Database status
./monitor.sh stats       # Trading statistics
./monitor.sh logs        # Recent activity
./monitor.sh network     # Network connectivity
```

### backup.sh

**Purpose:** Backup all important data and configuration

**What it backs up:**
- SQLite database
- SQL dump (for portability)
- Trade logs (CSV)
- Backtest logs
- Configuration (sensitive data excluded)
- Recent logs (last 1000 lines)

**Features:**
- Creates compressed tar.gz archives
- Automatically cleans old backups (keeps last 10)
- Includes backup metadata
- Provides restore instructions

**Usage:**
```bash
./backup.sh
```

**Backups are saved to:** `backups/backup-TIMESTAMP.tar.gz`

**To restore:**
```bash
tar -xzf backups/backup-TIMESTAMP.tar.gz
cd backup-TIMESTAMP
cp trading.db ../data/
```

### uninstall.sh

**Purpose:** Clean removal of the bot while preserving data

**What it removes:**
- LaunchAgent service
- Virtual environment
- Log files
- Management scripts

**What it preserves (by default):**
- Database
- Trade logs
- Configuration file

**Optional removal:**
- Data directory (with backup)
- Configuration file (with backup)

**Usage:**
```bash
./uninstall.sh
# Follow prompts
```

## 🔐 Security Notes

### Protected Files (Never Commit)
- `.env` - Contains API keys and passwords
- `data/trading.db` - Contains trading history
- `logs/*.log` - May contain sensitive information
- `backups/*` - Backup archives

### .gitignore
The `.gitignore` file is configured to protect:
- Environment files (`.env`)
- Virtual environment (`venv/`)
- Data directory (`data/`)
- Log files (`*.log`, `logs/`)
- Database files (`*.db`)
- Backup files (`backups/`, `*.tar.gz`)
- macOS files (`.DS_Store`)

## 📊 macOS LaunchAgent

The deployment script creates a LaunchAgent plist file:

**Location:** `~/Library/LaunchAgents/com.trading.bot.plist`

**Features:**
- Auto-start on login
- Auto-restart on crash
- Runs in background
- Logs to files
- Proper working directory
- Environment variables

**Manual Control:**
```bash
# Load (start)
launchctl load ~/Library/LaunchAgents/com.trading.bot.plist

# Unload (stop)
launchctl unload ~/Library/LaunchAgents/com.trading.bot.plist

# Check if running
launchctl list | grep com.trading.bot
```

## 📝 Log Files

### bot.log
Main application log showing:
- Trading signals
- Position updates
- Balance changes
- WebSocket activity
- General information

**View:**
```bash
tail -f logs/bot.log
```

### bot_error.log
Error log showing:
- Python exceptions
- API errors
- Database errors
- Critical issues

**View:**
```bash
tail -f logs/bot_error.log
```

## 🔄 Update Process

When updates are available:

```bash
./stop.sh
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade
./start.sh
```

Or use the deployment script:

```bash
./stop.sh
./deploy.sh deps  # Reinstall dependencies
./start.sh
```

## 🆘 Troubleshooting

### Bot won't start
1. Check error log: `cat logs/bot_error.log`
2. Run in foreground: `./run.sh`
3. Check config: `cat .env`
4. Run health check: `./monitor.sh`

### Dashboard not accessible
1. Check if running: `./status.sh`
2. Check port: `lsof -i :8000`
3. Try different port in `.env`
4. Check firewall settings

### Permission errors
```bash
chmod +x *.sh
```

### Database issues
```bash
./stop.sh
./deploy.sh db
./start.sh
```

### Virtual environment corrupted
```bash
rm -rf venv
./deploy.sh venv
./deploy.sh deps
```

## 📞 Support Resources

- **Quick Start:** `QUICKSTART.md`
- **Full Guide:** `DEPLOYMENT.md`
- **Main README:** `README.md`
- **Configuration:** See `config.py` and `.env`
- **Database Schema:** `DATABASE_INTEGRATION.md`

## ✅ Post-Installation Checklist

After running `./deploy.sh install`:

- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] `.env` file configured
- [ ] API keys added to `.env`
- [ ] Dashboard password set
- [ ] Database initialized
- [ ] LaunchAgent created
- [ ] Management scripts created
- [ ] Bot tested in foreground (`./run.sh`)
- [ ] Bot started as service (`./start.sh`)
- [ ] Dashboard accessible (http://localhost:8000)
- [ ] Logs show activity (`./status.sh`)
- [ ] Health check passes (`./monitor.sh`)
- [ ] Backup tested (`./backup.sh`)

## 🎯 Next Steps

1. **Configure trading parameters** in `.env`
2. **Run backtest** to verify strategy
3. **Monitor performance** with `./monitor.sh watch`
4. **Set up automated backups** (crontab)
5. **Review logs daily** for issues
6. **Optimize strategy** based on results

## 📈 Performance Optimization

### System Resources
```bash
# Check resource usage
./monitor.sh service

# Increase priority
sudo renice -10 -p $(pgrep -f "python3 main.py")
```

### Database
```bash
# Optimize database
sqlite3 data/trading.db "VACUUM; ANALYZE;"
```

### Logs
```bash
# Rotate logs to save space
./backup.sh
> logs/bot.log
> logs/bot_error.log
```

## 🔄 Maintenance Schedule

### Daily
- Check status: `./status.sh`
- Review recent activity
- Monitor win rate

### Weekly
- Run health check: `./monitor.sh`
- Review trading statistics
- Analyze trade performance
- Check for updates

### Monthly
- Create backup: `./backup.sh`
- Review and optimize strategy
- Clean old logs
- Update dependencies

---

**For detailed information, see:**
- [QUICKSTART.md](QUICKSTART.md) - Get started in 5 minutes
- [DEPLOYMENT.md](DEPLOYMENT.md) - Comprehensive guide

**Happy trading! 🚀📈**





