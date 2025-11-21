import logging
import signal
import threading
from datetime import datetime

import ccxt
from binance import ThreadedWebsocketManager

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
        "Starting websocket stream (symbol=%s timeframe=%s)",
        config.symbol,
        config.timeframe,
    )

    binance_symbol = config.symbol.replace("/", "").upper()
    twm = ThreadedWebsocketManager(
        api_key=config.binance_api_key,
        api_secret=config.binance_api_secret,
        tld="us",
    )
    twm.start()
    trader_lock = threading.Lock()

    def handle_kline(msg: dict) -> None:
        if msg.get("e") != "kline":
            return
        kline = msg.get("k", {})
        started_at = datetime.utcfromtimestamp(int(kline.get("t", 0)) / 1000)
        ended_at = datetime.utcfromtimestamp(int(kline.get("T", 0)) / 1000)
        logging.info(
            "Kline %s %s-%s open=%.2f high=%.2f low=%.2f close=%.2f volume=%.2f closed=%s",
            config.symbol,
            started_at.isoformat(),
            ended_at.isoformat(),
            float(kline.get("o", 0.0)),
            float(kline.get("h", 0.0)),
            float(kline.get("l", 0.0)),
            float(kline.get("c", 0.0)),
            float(kline.get("v", 0.0)),
            kline.get("x"),
        )
        if not kline.get("x"):
            return
        if kline.get("s") != binance_symbol:
            return

        try:
            with trader_lock:
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
                ohlc={
                    "open": float(kline.get("o", 0.0)),
                    "high": float(kline.get("h", 0.0)),
                    "low": float(kline.get("l", 0.0)),
                    "close": float(kline.get("c", 0.0)),
                },
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
            logging.exception("websocket cycle failed: %s", exc)

    twm.start_kline_socket(
        callback=handle_kline,
        symbol=binance_symbol,
        interval=config.timeframe,
    )

    try:
        stop_event.wait()
    finally:
        logging.info("Shutting down websocket stream.")
        twm.stop()
        logging.info("Trading loop terminated.")


if __name__ == "__main__":
    main()