# bot_barebone.py
import logging
import signal
import threading
import time

import ccxt

from config import BotConfig
from dashboard import start_dashboard, update_state
from paper_trader import PaperTrader
from strategy import compute_signal


def build_exchange(config: BotConfig) -> ccxt.binanceus:
    exchange = ccxt.binanceus(
        {
            "apiKey": config.binance_api_key,
            "secret": config.binance_api_secret,
            "enableRateLimit": True,
        }
    )
    exchange.options["defaultType"] = (
        "future" if config.exchange_type == "future" else "spot"
    )
    return exchange


def main():
    config = BotConfig.load()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not config.binance_api_key or not config.binance_api_secret:
        logging.warning(
            "BINANCE_US_KEY/BINANCE_US_SECRET missing; data is restricted to public endpoints."
        )

    exchange = build_exchange(config)
    trader = PaperTrader(
        initial_usdt=config.initial_usdt,
        fee_rate=config.fee_rate,
        slippage=config.slippage,
        log_path=config.trades_log_path,
    )
    start_dashboard(config.dashboard_host, config.dashboard_port)
    stop_event = threading.Event()

    def stop_handler(*_):
        logging.info("Received shutdown signal.")
        stop_event.set()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    logging.info(
        "Starting trading loop (symbol=%s timeframe=%s)",
        config.symbol,
        config.timeframe,
    )

    while not stop_event.is_set():
        try:
            signal_obj = compute_signal(
                exchange,
                config.symbol,
                config.timeframe,
                short_window=config.short_window,
                long_window=config.long_window,
            )
            trade = trader.handle_signal(signal_obj, config.order_pct)
            update_state(
                balances=trader.get_balances(),
                last_signal=signal_obj.to_dict(),
                last_trade=trade.to_dict() if trade else None,
                price=signal_obj.price,
                signal_direction=signal_obj.direction,
                timestamp=signal_obj.timestamp.isoformat(),
                trade_side=trade.side if trade else None,
            )

            logging.info(
                "Signal=%s price=%.2f short=%.2f long=%.2f trend=%.4f",
                signal_obj.direction,
                signal_obj.price,
                signal_obj.short_ema,
                signal_obj.long_ema,
                signal_obj.trend_strength,
            )
        except Exception as exc:
            logging.exception("cycle failed: %s", exc)
        time.sleep(config.poll_interval)

    logging.info("Trading loop terminated.")


if __name__ == "__main__":
    main()