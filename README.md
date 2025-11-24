# Next-Gen Trading Bot

Lightweight Python engine that reads Binance.US market data, applies a moving-average crossover strategy, and simulates fills via a paper trader while exposing a tiny dashboard for monitoring.

> **Note**: If your directory is named `next-gen-tradinbg`, please rename it to `next-gen-trading` to fix the typo.

## Setup

1. Install the runtime dependencies (includes security packages):
   ```
   pip install -r requirements.txt
   ```
   This installs Flask, authentication libraries, rate limiting, CORS support, and all trading dependencies.

2. Export your Binance.US credentials (they are optional in paper mode but required when you go live):
   ```bash
   export BINANCE_US_KEY=yourkey
   export BINANCE_US_SECRET=yoursecret
   ```
   or copy `.env.example` to `.env` and edit the values when you install `python-dotenv`.
3. Customize parameters via environment variables (optional):
   - `BOT_SYMBOL` (default `BTC/USDT`)
   - `BOT_TIMEFRAME` (default `5m`)
   - `BOT_SHORT_WINDOW` / `BOT_LONG_WINDOW` (20/50)
   - `BOT_ORDER_PCT` (fraction of available cash per trade)
   - `BOT_INITIAL_USDT` (paper starting cash)
   - `BOT_TRADES_LOG_PATH` (CSV append path, default `data/trade_log.csv`)

## macOS Server Deployment 🚀

**New!** Automated deployment scripts for running as a background service on macOS.

### Quick Deploy
```bash
./deploy.sh install
```

This will:
- ✅ Setup virtual environment
- ✅ Install all dependencies
- ✅ Initialize database
- ✅ Create macOS LaunchAgent (auto-start service)
- ✅ Generate management scripts

### Management Commands
```bash
./start.sh      # Start bot as background service
./stop.sh       # Stop bot service
./restart.sh    # Restart bot service
./status.sh     # Check status and view logs
./monitor.sh    # Health check and diagnostics
./backup.sh     # Backup data and configuration
./run.sh        # Run in foreground (testing)
```

### Documentation
- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Comprehensive deployment guide
- **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)** - Scripts overview

## Running

Execute the orchestrator:

```
python3 main.py
```

Or use the deployment scripts (recommended for macOS server):

```bash
./run.sh        # Foreground (testing)
./start.sh      # Background service (production)
```

The bot now relies on Binance's kline websocket stream instead of polling. Whenever a closed candle arrives on `<symbol>@kline_<timeframe>`, it recomputes the signal, feeds the paper trader, writes to `data/trade_log.csv`, and updates the dashboard. The dashboard starts automatically and listens on `BOT_DASHBOARD_HOST:BOT_DASHBOARD_PORT` (default `0.0.0.0:8000`).

## Dashboard
The dashboard automatically starts on `http://localhost:8000` by default. Simply visit `http://localhost:8000` in your browser to access the main UI with live price charts, buy/sell markers, and trade summaries. You can also access the JSON API at `http://<host>:<port>/state` to retrieve the latest balances, signal, and trade summary programmatically.

### Available Endpoints
- `/` - Homepage (redirects to main dashboard)
- `/ui` - Main dashboard UI with live chart
- `/health` - Health check (no authentication required)
- `/state` - Current bot state (JSON)
- `/history` - Trade history with price data
- `/api/trades` - Query trades with filters
- `/api/stats` - Trading statistics
- `/api/positions` - Open positions
- `/api/config` - Current configuration
- `/api/backtest/run` - Run backtest (POST)
- `/api/backtest/results` - Get backtest results
- `/api/backtest/clear` - Clear all backtest results (POST/DELETE)
- `/backtest` - Backtest runner page
- `/settings` - Settings page
- `/logout` - Logout (clears browser credentials)

Rate limiting: 60 requests/minute by default (configurable)

## Security & Authentication

The dashboard is protected with multi-layer security by default:

### Authentication
All dashboard endpoints require authentication (except `/health`). Two methods are supported:

**1. Basic HTTP Authentication (for browser access):**
```bash
# Access in browser - you'll be prompted for username/password
http://localhost:8000

# Or use curl with credentials
curl -u admin:changeme http://localhost:8000/api/stats
```

**2. API Key Authentication (for scripts/programmatic access):**
```bash
# Set DASHBOARD_API_KEY in your .env file
curl -H "Authorization: Bearer YOUR_API_KEY" http://localhost:8000/api/stats
```

### Configuration
Set these environment variables in your `.env` file:

```bash
# Enable/disable authentication (default: enabled)
DASHBOARD_AUTH_ENABLED=true

# Credentials for Basic Auth
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=your_secure_password

# API key for Bearer token auth (optional)
DASHBOARD_API_KEY=your_api_key_here

# Security settings
DASHBOARD_REQUIRE_HTTPS=false
DASHBOARD_ENABLE_RATE_LIMITING=true
DASHBOARD_RATE_LIMIT_PER_MINUTE=60
DASHBOARD_ALLOWED_ORIGINS=*
```

### Production Security Best Practices
1. **Use bcrypt hashed passwords** instead of plaintext:
   ```bash
   python -c "from auth import hash_password_cli; print(hash_password_cli('your_password'))"
   ```
   Then set `DASHBOARD_PASSWORD` to the hash output.

2. **Enable HTTPS** when running on public servers by setting `DASHBOARD_REQUIRE_HTTPS=true`

3. **Restrict CORS origins** to trusted domains:
   ```bash
   DASHBOARD_ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
   ```

4. **Use strong API keys** with sufficient entropy (32+ random characters)

5. **Keep credentials secure** - never commit `.env` to version control

### Logging Out
To logout from the dashboard:
- **Browser**: Click the "Logout" link in the navigation menu or visit `http://localhost:8000/logout`
- **Complete logout**: Close all browser tabs/windows after logging out
- **API Keys**: Simply stop including the API key in your requests

The logout page will guide you through clearing browser-cached credentials.

### Disabling Authentication (Development Only)
For local development, you can disable authentication:
```bash
DASHBOARD_AUTH_ENABLED=false
```
**⚠️ WARNING:** Never disable authentication on public servers!

## Dotenv support

Copy `env.example` to `.env` and edit your API keys or parameters. The bot loads those values automatically via `python-dotenv` when you run `python3 main.py`.

## Going Live

1. Provide real Binance.US credentials as environment variables.
2. Adjust `BOT_ORDER_PCT` / risk parameters to match your appetite.
3. Change `BOT_EXCHANGE_TYPE` to `spot` or `future` as needed.
4. Monitor `data/trade_log.csv` and the `/state` endpoint while the script runs on your Mac server.

