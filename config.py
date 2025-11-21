import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass
class BotConfig:
    binance_api_key: str
    binance_api_secret: str
    symbol: str = "BTC/USDT"
    timeframe: str = "5m"
    short_window: int = 20
    long_window: int = 50
    order_pct: float = 0.25
    initial_usdt: float = 1000.0
    fee_rate: float = 0.00075
    slippage: float = 0.0005
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    exchange_type: str = "spot"
    trades_log_path: str = "data/trade_log.csv"

    @classmethod
    def load(cls) -> "BotConfig":
        env = os.environ
        return cls(
            binance_api_key=env.get("BINANCE_US_KEY", ""),
            binance_api_secret=env.get("BINANCE_US_SECRET", ""),
            symbol=env.get("BOT_SYMBOL", "BTC/USDT"),
            timeframe=env.get("BOT_TIMEFRAME", "5m"),
            short_window=int(env.get("BOT_SHORT_WINDOW", 20)),
            long_window=int(env.get("BOT_LONG_WINDOW", 50)),
            order_pct=float(env.get("BOT_ORDER_PCT", 0.25)),
            initial_usdt=float(env.get("BOT_INITIAL_USDT", 1000.0)),
            fee_rate=float(env.get("BOT_FEE_RATE", 0.00075)),
            slippage=float(env.get("BOT_SLIPPAGE", 0.0005)),
            dashboard_host=env.get("BOT_DASHBOARD_HOST", "0.0.0.0"),
            dashboard_port=int(env.get("BOT_DASHBOARD_PORT", 8000)),
            exchange_type=env.get("BOT_EXCHANGE_TYPE", "spot"),
            trades_log_path=env.get("BOT_TRADES_LOG_PATH", "data/trade_log.csv"),
        )

