# Deployment Guide - macOS Server

This guide will help you deploy the Next-Gen Trading Bot on your macOS server.

## Quick Start

### 1. Run the Deployment Script

```bash
./deploy.sh
```

This will launch an interactive menu with all deployment options.

### 2. Full Automated Installation

For a complete one-command installation:

```bash
./deploy.sh install
```

This will:
- ✓ Check system dependencies
- ✓ Create necessary directories
- ✓ Setup Python virtual environment
- ✓ Install all Python dependencies
- ✓ Create environment configuration file
- ✓ Initialize the database
- ✓ Create macOS LaunchAgent service
- ✓ Generate management scripts

## Prerequisites

### Required Software

- **Python 3.8+** - Install with Homebrew:
  ```bash
  brew install python3
  ```

- **pip3** - Usually comes with Python

### Optional but Recommended

- **Homebrew** - macOS package manager:
  ```bash
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  ```

## Configuration

### 1. Edit Environment Variables

After installation, configure your settings:

```bash
nano .env
```

**Critical Settings:**
```bash
# Binance API Credentials (REQUIRED)
BINANCE_US_KEY=your_api_key_here
BINANCE_US_SECRET=your_api_secret_here

# Dashboard Security (IMPORTANT)
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=your_secure_password_here
DASHBOARD_API_KEY=your_api_key_here
```

**Trading Settings:**
```bash
BOT_SYMBOL=BTC/USDT
BOT_TIMEFRAME=1h
BOT_INITIAL_USDT=1000.0
BOT_ORDER_PCT=0.25
```

**Risk Management:**
```bash
BOT_STOP_LOSS_PCT=0.025      # 2.5% stop loss
BOT_TAKE_PROFIT_PCT=0.04     # 4% take profit
BOT_TRAILING_STOP_PCT=0.015  # 1.5% trailing stop
```

### 2. Generate Secure Password

For the dashboard password:

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())"
```

Use the output hash in your `.env` file.

## Running the Bot

### Testing Mode (Foreground)

Run the bot in the foreground to test configuration:

```bash
./run.sh
```

Press `Ctrl+C` to stop.

### Production Mode (Background Service)

#### Start the Service

```bash
./start.sh
```

The bot will now run in the background and auto-restart on crashes or system reboots.

#### Stop the Service

```bash
./stop.sh
```

#### Restart the Service

```bash
./restart.sh
```

#### Check Status

```bash
./status.sh
```

## Accessing the Dashboard

Once the bot is running, access the web dashboard:

```
http://localhost:8000
```

Or from another machine on your network:

```
http://YOUR_SERVER_IP:8000
```

**Default Credentials:**
- Username: `admin`
- Password: (whatever you set in `.env`)

### Dashboard Features

- 📊 Real-time trading data
- 📈 Price charts with signals
- 💰 Balance tracking
- 📝 Trade history
- ⚙️ Settings configuration
- 🧪 Backtest runner

## Log Management

### View Live Logs

```bash
tail -f logs/bot.log
```

### View Error Logs

```bash
tail -f logs/bot_error.log
```

### View Trade Logs

```bash
tail -f data/trade_log.csv
```

### Log Rotation

To prevent logs from growing too large:

```bash
# Archive old logs
cd logs
gzip bot.log
mv bot.log.gz bot-$(date +%Y%m%d).log.gz

# Or clear logs
> bot.log
> bot_error.log
```

## macOS Service Management

### Manual Service Control

```bash
# Load service (start)
launchctl load ~/Library/LaunchAgents/com.trading.bot.plist

# Unload service (stop)
launchctl unload ~/Library/LaunchAgents/com.trading.bot.plist

# Check if running
launchctl list | grep com.trading.bot
```

### Auto-Start on System Boot

The service is configured to automatically start when you log in. To disable:

```bash
launchctl unload ~/Library/LaunchAgents/com.trading.bot.plist
```

## Database Management

### View Database

```bash
sqlite3 data/trading.db

# Inside sqlite3:
.tables                 # List all tables
.schema trades          # View schema
SELECT * FROM trades;   # View trades
.exit                   # Exit
```

### Backup Database

```bash
# Manual backup
cp data/trading.db data/trading-$(date +%Y%m%d).db.backup

# Automated daily backup (add to crontab)
0 0 * * * cp ~/path/to/data/trading.db ~/path/to/data/backups/trading-$(date +\%Y\%m\%d).db
```

### Reset Database

```bash
./stop.sh
rm data/trading.db
./deploy.sh db  # Reinitialize
./start.sh
```

## Updating the Bot

### Pull Latest Changes

```bash
./stop.sh
git pull origin main
source venv/bin/activate
pip install -r requirements.txt --upgrade
./start.sh
```

### Update Dependencies Only

```bash
./stop.sh
source venv/bin/activate
pip install -r requirements.txt --upgrade
./start.sh
```

## Troubleshooting

### Bot Won't Start

1. Check logs:
   ```bash
   cat logs/bot_error.log
   ```

2. Verify configuration:
   ```bash
   cat .env
   ```

3. Test in foreground:
   ```bash
   ./run.sh
   ```

### Dashboard Not Accessible

1. Check if bot is running:
   ```bash
   ./status.sh
   ```

2. Verify port is open:
   ```bash
   lsof -i :8000
   ```

3. Check firewall settings:
   ```bash
   # Allow incoming connections on port 8000
   # System Preferences > Security & Privacy > Firewall > Firewall Options
   ```

### API Connection Issues

1. Verify API credentials in `.env`
2. Check Binance API status
3. Ensure IP whitelisting (if configured on Binance)

### Permission Denied Errors

```bash
chmod +x deploy.sh
chmod +x *.sh
```

### Virtual Environment Issues

```bash
rm -rf venv
./deploy.sh venv
./deploy.sh deps
```

## Security Best Practices

### 1. Secure API Keys

- Never commit `.env` to version control
- Use read-only API keys if possible
- Enable IP whitelisting on Binance

### 2. Dashboard Security

- Use strong passwords
- Enable HTTPS in production
- Restrict `DASHBOARD_ALLOWED_ORIGINS`
- Use firewall to restrict access

### 3. Server Security

```bash
# Keep macOS updated
softwareupdate -l
softwareupdate -i -a

# Enable firewall
sudo defaults write /Library/Preferences/com.apple.alf globalstate -int 1

# Disable remote login if not needed
sudo systemsetup -setremotelogin off
```

## Performance Optimization

### 1. Increase Process Priority

Edit the LaunchAgent plist and change:
```xml
<key>Nice</key>
<integer>-10</integer>  <!-- Higher priority -->
```

### 2. Monitor Resource Usage

```bash
# CPU and Memory usage
top -pid $(pgrep -f "python3 main.py")

# Detailed stats
ps aux | grep python3
```

### 3. Database Optimization

```bash
sqlite3 data/trading.db "VACUUM;"
sqlite3 data/trading.db "ANALYZE;"
```

## Uninstalling

To completely remove the bot:

```bash
# Stop service
./stop.sh

# Remove LaunchAgent
rm ~/Library/LaunchAgents/com.trading.bot.plist

# Remove bot files (BE CAREFUL - this deletes everything)
cd ..
rm -rf next-gen-trading
```

## Support

For issues, questions, or feature requests:

1. Check existing documentation
2. Review logs for error messages
3. Consult the main README.md
4. Check GitHub issues

## Advanced Configuration

### Custom Port

Edit `.env`:
```bash
BOT_DASHBOARD_PORT=8080
```

### Multiple Instances

To run multiple bots for different pairs:

1. Clone the repository to different directories
2. Use different port numbers
3. Use different database files
4. Create separate LaunchAgent plists

### Network Access

To access from external networks:

1. Configure port forwarding on your router
2. Use dynamic DNS if you don't have a static IP
3. Consider using a reverse proxy (nginx)
4. **Always use HTTPS** for external access

## Monitoring and Alerts

### Email Alerts (via macOS)

Add to your Python code or create a monitoring script:

```python
import subprocess

def send_alert(subject, message):
    subprocess.run([
        'osascript', '-e',
        f'tell application "Mail" to send mail with properties {{subject:"{subject}", content:"{message}"}}'
    ])
```

### SMS Alerts (via Twilio)

Install Twilio SDK and configure in your bot:

```bash
pip install twilio
```

## Production Checklist

- [ ] API credentials configured
- [ ] Dashboard password set
- [ ] Database initialized
- [ ] Service auto-start enabled
- [ ] Logs rotation configured
- [ ] Firewall rules configured
- [ ] Backup strategy in place
- [ ] Monitoring setup
- [ ] Tested in foreground mode
- [ ] Tested as background service

## Additional Resources

- [Main README](README.md)
- [Configuration Guide](config.py)
- [Database Schema](database.py)
- [Strategy Documentation](strategy.py)

---

**Happy Trading! 🚀📈**





