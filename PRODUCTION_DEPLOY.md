# Production Deployment Guide

## 🚀 Quick Start (5 Steps)

### 1. Transfer to Server

```bash
# Option A: Via rsync
rsync -avz --exclude 'venv' --exclude 'data' --exclude '*.log' \
  /Users/toninichev/workspace/projects-next-gen-trading/ \
  user@server:/opt/trading-bot/

# Option B: Via git (recommended)
ssh user@server
git clone <your-repo> /opt/trading-bot
cd /opt/trading-bot
```

### 2. Run Production Setup

```bash
# Make scripts executable
chmod +x *.sh

# Quick production deployment
./production-setup.sh all
```

Or step by step:

```bash
# Deploy and configure
./deploy.sh install

# Harden security
./production-setup.sh security

# Setup backups
./production-setup.sh backup

# Setup monitoring
./production-setup.sh monitor
```

### 3. Configure Environment

```bash
nano .env
```

**Critical Production Values:**

```bash
# API Credentials (REQUIRED)
BINANCE_US_KEY=your_production_key
BINANCE_US_SECRET=your_production_secret

# Security (IMPORTANT)
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=use_a_very_strong_password_here
DASHBOARD_API_KEY=generate_secure_random_key

# Trading Settings
BOT_SYMBOL=BTC/USDT
BOT_TIMEFRAME=1h
BOT_INITIAL_USDT=1000.0
BOT_ORDER_PCT=0.25

# Risk Management (Conservative for Production)
BOT_STOP_LOSS_PCT=0.025
BOT_TAKE_PROFIT_PCT=0.04
BOT_TRAILING_STOP_PCT=0.015

# Server
BOT_DASHBOARD_HOST=0.0.0.0
BOT_DASHBOARD_PORT=8000
```

### 4. Test Before Production

```bash
# Test in foreground
./run.sh

# Verify:
# ✓ No errors
# ✓ Dashboard loads: http://server-ip:8000
# ✓ API connects to Binance
# ✓ Database initializes

# Stop with Ctrl+C
```

### 5. Start Production Service

```bash
# Start as background service
./start.sh

# Check status
./status.sh

# Monitor logs
tail -f logs/bot.log
```

## 📋 Complete Production Workflow

```bash
# On server
cd /opt/trading-bot

# 1. Full deployment
./production-setup.sh deploy

# 2. Configure .env with production credentials
nano .env

# 3. Harden security
./production-setup.sh security

# 4. Test
./run.sh  # Press Ctrl+C after verifying

# 5. Start production service
./start.sh

# 6. Verify
./status.sh
tail -f logs/bot.log

# 7. Access dashboard
# http://your-server-ip:8000
```

## 🔐 Security Best Practices

### 1. API Security

```bash
# On Binance:
# ✓ Use SPOT trading permissions only
# ✓ Enable IP whitelisting for your server
# ✓ Use read-only keys for testing first
# ✓ Enable withdrawal whitelist
```

### 2. Dashboard Security

```bash
# Generate secure password
openssl rand -base64 32

# Or use the production setup script
./production-setup.sh security

# Access via SSH tunnel (most secure)
ssh -L 8000:localhost:8000 user@server
# Then access: http://localhost:8000
```

### 3. File Permissions

```bash
chmod 600 .env                    # Protect credentials
chmod 700 data/                   # Protect database
chmod 600 data/trading.db         # Protect database file
chmod +x *.sh                     # Make scripts executable
```

### 4. Firewall Configuration

```bash
# macOS Firewall
sudo defaults write /Library/Preferences/com.apple.alf globalstate -int 1

# Allow only specific IPs (if needed)
# System Preferences > Security & Privacy > Firewall > Firewall Options
```

## 📊 Monitoring & Maintenance

### Health Check

```bash
./monitor.sh
```

### View Logs

```bash
# Application logs
tail -f logs/bot.log

# Error logs
tail -f logs/bot_error.log

# Last 100 lines
tail -100 logs/bot.log

# Follow errors only
tail -f logs/bot_error.log | grep ERROR
```

### Service Management

```bash
./start.sh      # Start service
./stop.sh       # Stop service
./restart.sh    # Restart service
./status.sh     # Check status and view logs
```

### Database Management

```bash
# Backup database
./backup.sh

# View database
sqlite3 data/trading.db
> .tables
> SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10;
> .exit

# Database size
du -h data/trading.db
```

### Performance Monitoring

```bash
# Check resource usage
ps aux | grep "python3 main.py"

# Detailed monitoring
top -pid $(pgrep -f "python3 main.py")

# Check open connections
lsof -i :8000
```

## 🔄 Updates & Maintenance

### Update the Bot

```bash
# Stop service
./stop.sh

# Pull latest changes
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart service
./start.sh
```

### Backup Before Updates

```bash
# Create backup
./backup.sh

# Or manual backup
tar -czf backup-$(date +%Y%m%d).tar.gz \
  .env data/ *.py requirements.txt
```

### Rollback if Needed

```bash
# Stop service
./stop.sh

# Restore from backup
tar -xzf backups/backup_YYYYMMDD_HHMMSS.tar.gz

# Restart
./start.sh
```

## 🚨 Troubleshooting

### Service Won't Start

```bash
# Check logs
cat logs/bot_error.log

# Test in foreground
./run.sh

# Check configuration
python3 -c "from config import BotConfig; BotConfig.load()"
```

### Dashboard Not Accessible

```bash
# Check if running
./status.sh

# Check port
lsof -i :8000

# Check firewall
sudo pfctl -sr | grep 8000
```

### High CPU/Memory Usage

```bash
# Check resource usage
./monitor.sh

# Restart service
./restart.sh

# Check for memory leaks in logs
grep -i "memory" logs/bot_error.log
```

### Database Locked

```bash
# Stop service
./stop.sh

# Wait for locks to clear
sleep 5

# Start service
./start.sh
```

## 📦 Backup Strategy

### Automated Daily Backups

```bash
# Setup automated backups (runs at 2 AM daily)
./production-setup.sh backup
```

### Manual Backup

```bash
# Quick backup
./backup.sh

# Full backup with logs
tar -czf full-backup-$(date +%Y%m%d).tar.gz \
  .env data/ logs/ *.py requirements.txt
```

### Restore from Backup

```bash
# Stop service
./stop.sh

# Extract backup
tar -xzf backups/backup_YYYYMMDD_HHMMSS.tar.gz

# Start service
./start.sh
```

## 🎯 Production Checklist

### Pre-Deployment
- [ ] API credentials configured
- [ ] Strong dashboard password
- [ ] Risk parameters set (conservative)
- [ ] Tested in development
- [ ] Tested in foreground on server

### Security
- [ ] .env file protected (chmod 600)
- [ ] Firewall configured
- [ ] IP whitelisting on Binance
- [ ] SSH access only (no direct dashboard access)
- [ ] Strong passwords everywhere

### Monitoring
- [ ] Automated backups enabled
- [ ] Log rotation configured
- [ ] Monitoring script tested
- [ ] Know how to check status

### Deployment
- [ ] Service auto-starts on boot
- [ ] Service restarts on failure
- [ ] Dashboard accessible
- [ ] Logs are being written
- [ ] Database is working

## 🌐 Remote Access (Secure)

### SSH Tunnel (Recommended)

```bash
# From your local machine
ssh -L 8000:localhost:8000 user@server

# Access dashboard at: http://localhost:8000
```

### VPN Access (Alternative)

Set up VPN to server, then access directly:

```
http://server-local-ip:8000
```

### Reverse Proxy (Advanced)

Use nginx with HTTPS for production:

```nginx
server {
    listen 443 ssl;
    server_name trading.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 📈 Scaling Tips

### Multiple Trading Pairs

```bash
# Create separate instances
cp -r /opt/trading-bot /opt/trading-bot-eth
cd /opt/trading-bot-eth

# Edit .env for different pair
nano .env
# Change: BOT_SYMBOL=ETH/USDT
# Change: BOT_DASHBOARD_PORT=8001

# Deploy
./deploy.sh install
./start.sh
```

### Resource Optimization

```bash
# Increase process priority (in LaunchAgent plist)
<key>Nice</key>
<integer>-10</integer>

# Vacuum database regularly
sqlite3 data/trading.db "VACUUM; ANALYZE;"
```

## 📞 Support & Resources

- **Documentation**: See DEPLOYMENT.md for detailed guide
- **Logs**: Check `logs/bot_error.log` for errors
- **Database**: SQLite at `data/trading.db`
- **Configuration**: All settings in `.env`

## 🎉 Quick Commands Reference

```bash
./deploy.sh install          # Initial deployment
./production-setup.sh all    # Full production setup
./start.sh                   # Start service
./stop.sh                    # Stop service
./restart.sh                 # Restart service
./status.sh                  # Check status
./monitor.sh                 # Health check
./backup.sh                  # Create backup
tail -f logs/bot.log         # View logs
```

---

**Ready for Production! 🚀**
