# Quick Start Guide - macOS Server Deployment

Get your trading bot up and running in 5 minutes!

## 🚀 One-Command Install

```bash
./deploy.sh install
```

That's it! The script will guide you through the rest.

## 📋 What You Need

1. **Binance API Keys** (from binance.us)
2. **Python 3.8+** (install with `brew install python3`)
3. **5 minutes of your time**

## 🎯 Installation Steps

### 1. Clone & Deploy

```bash
cd ~/workspace/projects-next-gen-trading
./deploy.sh install
```

### 2. Configure API Keys

Edit the `.env` file that was created:

```bash
nano .env
```

**Required settings:**
```bash
BINANCE_US_KEY=your_api_key_here
BINANCE_US_SECRET=your_api_secret_here
DASHBOARD_PASSWORD=your_secure_password
```

### 3. Test Run

```bash
./run.sh
```

Press `Ctrl+C` to stop. If everything works, proceed to step 4.

### 4. Start as Service

```bash
./start.sh
```

Your bot is now running in the background!

## 📊 Access Dashboard

Open your browser:
```
http://localhost:8000
```

**Login:**
- Username: `admin`
- Password: (what you set in `.env`)

## 🛠 Daily Commands

| Command | Description |
|---------|-------------|
| `./start.sh` | Start bot service |
| `./stop.sh` | Stop bot service |
| `./restart.sh` | Restart bot service |
| `./status.sh` | Check status & view logs |
| `./monitor.sh` | Full health check |
| `./backup.sh` | Backup all data |
| `./run.sh` | Run in foreground (testing) |

## 📝 View Logs

```bash
# Live logs
tail -f logs/bot.log

# Error logs
tail -f logs/bot_error.log

# Status + recent logs
./status.sh
```

## 🔍 Monitoring

### Quick Health Check
```bash
./monitor.sh
```

### Continuous Monitoring
```bash
./monitor.sh watch
```

### Specific Checks
```bash
./monitor.sh service    # Check if running
./monitor.sh dashboard  # Check dashboard
./monitor.sh stats      # Show trading stats
./monitor.sh errors     # Show recent errors
```

## 💾 Backups

### Manual Backup
```bash
./backup.sh
```

Backups are saved in `backups/` directory.

### Automated Backups

Add to crontab for daily backups at 2 AM:

```bash
crontab -e
```

Add this line:
```
0 2 * * * cd ~/workspace/projects-next-gen-trading && ./backup.sh
```

## ⚙️ Configuration

All settings are in `.env`. Key parameters:

```bash
# Trading Pair
BOT_SYMBOL=BTC/USDT

# Timeframe (1m, 5m, 15m, 1h, 4h, 1d)
BOT_TIMEFRAME=1h

# Initial Balance
BOT_INITIAL_USDT=1000.0

# Risk Management
BOT_STOP_LOSS_PCT=0.025      # 2.5%
BOT_TAKE_PROFIT_PCT=0.04     # 4%
BOT_TRAILING_STOP_PCT=0.015  # 1.5%

# Position Size
BOT_ORDER_PCT=0.25           # 25% per trade
```

After changing settings:
```bash
./restart.sh
```

## 🐛 Troubleshooting

### Bot Won't Start?

1. Check logs:
   ```bash
   cat logs/bot_error.log
   ```

2. Run in foreground to see errors:
   ```bash
   ./run.sh
   ```

3. Verify API keys in `.env`

### Dashboard Not Accessible?

1. Check if bot is running:
   ```bash
   ./status.sh
   ```

2. Try different port in `.env`:
   ```bash
   BOT_DASHBOARD_PORT=8080
   ```

3. Check firewall settings

### Database Issues?

Reset database:
```bash
./stop.sh
rm data/trading.db
./deploy.sh db
./start.sh
```

## 🔒 Security Tips

1. **Use strong passwords** in `.env`
2. **Never commit** `.env` to git
3. **Enable firewall** on your server
4. **Restrict dashboard access** (set `DASHBOARD_ALLOWED_ORIGINS`)
5. **Use read-only API keys** when possible

## 📈 Features

- ✅ Real-time trading signals
- ✅ Automatic stop-loss & take-profit
- ✅ Trailing stops
- ✅ Web dashboard with charts
- ✅ Trade history & statistics
- ✅ Backtesting engine
- ✅ Risk management
- ✅ Database logging
- ✅ Auto-restart on failure
- ✅ Email/SMS alerts (configurable)

## 🔄 Updates

To update to the latest version:

```bash
./stop.sh
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
./start.sh
```

## 🗑 Uninstall

```bash
./uninstall.sh
```

This will remove the bot but preserve your data by default.

## 📚 More Documentation

- [Full Deployment Guide](DEPLOYMENT.md) - Detailed setup & configuration
- [README](README.md) - Main documentation
- [Configuration Guide](config.py) - All settings explained
- [Database Schema](DATABASE_INTEGRATION.md) - Database details

## ⚡ Performance Tips

### 1. Increase Process Priority

```bash
sudo renice -10 -p $(pgrep -f "python3 main.py")
```

### 2. Monitor Resources

```bash
./monitor.sh watch
```

### 3. Optimize Database

```bash
sqlite3 data/trading.db "VACUUM; ANALYZE;"
```

## 📞 Getting Help

1. Check the logs: `./status.sh`
2. Run health check: `./monitor.sh`
3. Review documentation: `DEPLOYMENT.md`
4. Check GitHub issues

## 🎉 Success Checklist

After installation, verify:

- [ ] Bot service is running (`./status.sh`)
- [ ] Dashboard is accessible (http://localhost:8000)
- [ ] Can log in to dashboard
- [ ] Logs show trading activity (`tail -f logs/bot.log`)
- [ ] Database is recording trades
- [ ] Service restarts automatically after reboot

## 🚨 Important Notes

1. **Paper Trading**: This bot uses paper trading by default (simulated trades)
2. **Risk Warning**: Cryptocurrency trading involves substantial risk
3. **Test First**: Always test thoroughly before live trading
4. **Monitor Regularly**: Check logs and performance daily
5. **Keep Updated**: Pull updates regularly for bug fixes

## 💡 Pro Tips

1. **Start small**: Use small position sizes initially
2. **Use 1h timeframe**: Better signal quality than shorter timeframes
3. **Enable trailing stops**: Protect profits automatically
4. **Monitor win rate**: Aim for >50% win rate
5. **Review trades**: Analyze your trades weekly to improve strategy

---

**Ready to trade? Start here:**

```bash
./deploy.sh install
```

**Happy trading! 🚀📈💰**




