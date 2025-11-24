# Installation Checklist

Use this checklist to ensure successful deployment on your macOS server.

## 📋 Pre-Installation

- [ ] macOS server is accessible
- [ ] Have Binance.US account and API keys ready
- [ ] Have chosen a secure dashboard password
- [ ] Have Python 3.8+ installed (`python3 --version`)
- [ ] Have git installed (optional)

## 🚀 Installation Steps

### Step 1: Deploy Bot
```bash
cd ~/workspace/projects-next-gen-trading
./deploy.sh install
```

- [ ] Deployment script completed successfully
- [ ] Virtual environment created
- [ ] Dependencies installed
- [ ] `.env` file created

### Step 2: Configure Settings
```bash
nano .env
```

**Required Configuration:**
- [ ] Set `BINANCE_US_KEY` (your API key)
- [ ] Set `BINANCE_US_SECRET` (your API secret)
- [ ] Set `DASHBOARD_PASSWORD` (secure password)
- [ ] Set `DASHBOARD_API_KEY` (optional, for API access)

**Optional Configuration:**
- [ ] Adjust `BOT_SYMBOL` (default: BTC/USDT)
- [ ] Adjust `BOT_TIMEFRAME` (recommended: 1h)
- [ ] Adjust `BOT_INITIAL_USDT` (paper trading balance)
- [ ] Review risk management settings
- [ ] Review position sizing settings

### Step 3: Test Configuration
```bash
./run.sh
```

- [ ] Bot starts without errors
- [ ] Websocket connects to Binance
- [ ] Dashboard is accessible at http://localhost:8000
- [ ] Can login to dashboard
- [ ] Price data is displaying
- [ ] No error messages in console
- [ ] Press `Ctrl+C` to stop

### Step 4: Start as Service
```bash
./start.sh
```

- [ ] Service started successfully
- [ ] Process is running (`./status.sh`)
- [ ] Dashboard is accessible
- [ ] Logs show activity (`tail -f logs/bot.log`)

## ✅ Post-Installation Verification

### Service Status
```bash
./status.sh
```

- [ ] Service shows as "RUNNING"
- [ ] Recent logs show trading activity
- [ ] No error messages

### Dashboard Access
Open browser: http://localhost:8000

- [ ] Dashboard loads successfully
- [ ] Login page appears (if auth enabled)
- [ ] Can login with credentials
- [ ] Price chart is displaying
- [ ] Balance is showing correctly
- [ ] No JavaScript errors in console

### Health Check
```bash
./monitor.sh
```

- [ ] Service status: ✓ RUNNING
- [ ] Dashboard: ✓ Accessible
- [ ] Database: ✓ Exists
- [ ] Network: ✓ Connected
- [ ] No errors reported

### Database Check
```bash
sqlite3 data/trading.db "SELECT COUNT(*) FROM trades;"
```

- [ ] Database is accessible
- [ ] Tables exist
- [ ] Can query successfully

### Log Files
```bash
ls -lh logs/
```

- [ ] `bot.log` exists and is growing
- [ ] `bot_error.log` exists (may be empty if no errors)
- [ ] Logs show recent timestamps

## 🔒 Security Checklist

- [ ] Changed default password in `.env`
- [ ] Using strong password (12+ characters)
- [ ] `.env` file is not committed to git
- [ ] Dashboard authentication is enabled
- [ ] Rate limiting is enabled
- [ ] CORS origins configured (if needed)
- [ ] Firewall rules configured (if needed)
- [ ] API keys have appropriate permissions
- [ ] IP whitelisting enabled on Binance (optional)

## 📊 Functionality Tests

### Trading Signals
- [ ] Bot is receiving price updates
- [ ] Signals are being generated
- [ ] Trades are being logged
- [ ] Dashboard shows recent signals

### Dashboard Features
- [ ] `/ui` - Main dashboard works
- [ ] `/settings` - Settings page works
- [ ] `/backtest` - Backtest page works
- [ ] `/api/stats` - Statistics endpoint works
- [ ] `/api/trades` - Trades endpoint works
- [ ] `/api/config` - Config endpoint works

### Management Scripts
- [ ] `./start.sh` - Starts service
- [ ] `./stop.sh` - Stops service
- [ ] `./restart.sh` - Restarts service
- [ ] `./status.sh` - Shows status
- [ ] `./monitor.sh` - Shows health check
- [ ] `./backup.sh` - Creates backup
- [ ] `./run.sh` - Runs in foreground

## 🔄 Auto-Start on Boot

Test reboot behavior:

```bash
# Reboot server
sudo reboot

# After reboot, check if bot auto-started
./status.sh
```

- [ ] Service auto-started after reboot
- [ ] Dashboard is accessible
- [ ] Trading resumed automatically

## 💾 Backup Test

```bash
./backup.sh
ls -lh backups/
```

- [ ] Backup created successfully
- [ ] Backup file exists in `backups/`
- [ ] Backup includes database
- [ ] Backup size is reasonable

## 📱 Remote Access (Optional)

If accessing from another machine:

- [ ] Can access dashboard from local network
- [ ] Firewall allows port 8000 (if needed)
- [ ] HTTPS configured (for production)
- [ ] CORS settings allow access

Test from another machine:
```bash
curl http://YOUR_SERVER_IP:8000/health
```

## 📈 Performance Check

### Resource Usage
```bash
./monitor.sh service
```

- [ ] CPU usage is reasonable (<20% steady state)
- [ ] Memory usage is reasonable (<500MB)
- [ ] No memory leaks over time

### Database Performance
```bash
sqlite3 data/trading.db "PRAGMA integrity_check;"
```

- [ ] Database integrity check passes
- [ ] Query performance is good

## 🐛 Troubleshooting Tests

### If Service Won't Start
```bash
# Check error log
cat logs/bot_error.log

# Try foreground mode
./run.sh

# Check configuration
cat .env

# Verify dependencies
source venv/bin/activate
pip list
```

### If Dashboard Not Accessible
```bash
# Check if port is in use
lsof -i :8000

# Check if service is running
./status.sh

# Try different port in .env
BOT_DASHBOARD_PORT=8080
./restart.sh
```

### If API Connection Fails
```bash
# Test internet connectivity
ping -c 3 google.com

# Test Binance API
curl https://api.binance.us/api/v3/ping

# Verify API keys in .env
grep BINANCE .env
```

## 📚 Documentation Review

- [ ] Read `QUICKSTART.md`
- [ ] Read `DEPLOYMENT.md`
- [ ] Review `DEPLOYMENT_SUMMARY.md`
- [ ] Understand `README.md`
- [ ] Know where to find help

## 🎯 Production Readiness

Before going live with real trading:

- [ ] Thoroughly tested in paper trading mode
- [ ] Reviewed and understood all risk settings
- [ ] Set appropriate position sizes
- [ ] Configured stop losses
- [ ] Tested strategy with backtesting
- [ ] Win rate is acceptable (>50%)
- [ ] Monitoring is in place
- [ ] Backup strategy is working
- [ ] Know how to stop bot quickly
- [ ] Understand all trading parameters

## 📞 Support Resources

- [ ] Know how to view logs (`./status.sh`)
- [ ] Know how to run health check (`./monitor.sh`)
- [ ] Know how to backup data (`./backup.sh`)
- [ ] Know where documentation is
- [ ] Have tested disaster recovery

## ✨ Optional Enhancements

### Automated Backups
Add to crontab for daily backups:
```bash
crontab -e
# Add: 0 2 * * * cd ~/workspace/projects-next-gen-trading && ./backup.sh
```

- [ ] Automated backups configured
- [ ] Backup schedule tested

### Monitoring Alerts
- [ ] Email alerts configured (optional)
- [ ] SMS alerts configured (optional)
- [ ] Monitoring dashboard setup (optional)

### Advanced Security
- [ ] HTTPS enabled (for production)
- [ ] VPN access configured (optional)
- [ ] Two-factor authentication considered
- [ ] API key rotation schedule

## 🎉 Installation Complete!

If all items are checked, your trading bot is successfully deployed!

**Next Steps:**
1. Monitor bot performance daily
2. Review logs regularly
3. Run weekly health checks
4. Keep backups current
5. Update bot periodically

**Quick Reference:**
```bash
./start.sh      # Start bot
./status.sh     # Check status
./monitor.sh    # Health check
./backup.sh     # Backup data
```

**Dashboard:** http://localhost:8000

**Happy Trading! 🚀📈💰**

---

**Date Completed:** ________________

**Notes:**
_________________________
_________________________
_________________________


