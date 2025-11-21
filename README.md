# Crypto Bot

Lightweight Python engine that reads Binance.US market data, applies a moving-average crossover strategy, and simulates fills via a paper trader while exposing a tiny dashboard for monitoring.

## Setup

1. Install the runtime dependencies:
   ```
   pip install -r requirements.txt
   ```
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
   - `BOT_POLL_INTERVAL` (seconds between cycles)
   - `BOT_INITIAL_USDT` (paper starting cash)
   - `BOT_TRADES_LOG_PATH` (CSV append path)

## Running

Execute the orchestrator:

```
python3 main.py
```

The loop fetches candles, generates a signal, and logs simulated trades to `trade_log.csv`. The dashboard starts automatically and listens on `BOT_DASHBOARD_HOST:BOT_DASHBOARD_PORT` (default `0.0.0.0:8000`).

## Dashboard
Visit `http://<host>:<port>/state` to retrieve JSON with the latest balances, signal, and trade summary. This endpoint can be proxied behind your own domain, and the new UI at `http://<host>:<port>/ui` renders a live price chart with buy/sell markers and the most recent trade summary.

## Dotenv support

Copy `.env.example` to `.env` and edit your API keys or parameters. The bot loads those values automatically via `python-dotenv` when you run `python3 main.py`.

## Going Live

1. Provide real Binance.US credentials as environment variables.
2. Adjust `BOT_ORDER_PCT` / risk parameters to match your appetite.
3. Change `BOT_EXCHANGE_TYPE` to `spot` or `future` as needed.
4. Monitor `trade_log.csv` and the `/state` endpoint while the script runs on your Mac server.

