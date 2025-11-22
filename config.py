import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass
class BotConfig:
    binance_api_key: str
    binance_api_secret: str
    symbol: str = "BTC/USDT"
    timeframe: str = "1h"  # Hourly timeframe for better signal quality (CRITICAL: don't use 5m!)
    short_window: int = 12
    long_window: int = 26  # Using shorter windows for hourly (equivalent to daily 12/26)
    order_pct: float = 0.25  # 25% per trade for balanced risk/reward
    initial_usdt: float = 1000.0
    fee_rate: float = 0.00075
    slippage: float = 0.0005
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    exchange_type: str = "spot"
    trades_log_path: str = "data/trade_log.csv"
    
    # Database configuration
    database_url: str = "sqlite:///data/trading.db"
    enable_database: bool = True
    enable_csv_logging: bool = True  # Keep CSV for backward compatibility
    
    # Strategy filters
    min_trend_strength: float = 0.00005  # Minimum 0.005% separation (lowered for more signals)
    rsi_period: int = 14
    rsi_oversold: float = 25  # Filter oversold (adjusted from 20)
    rsi_overbought: float = 75  # Filter overbought (adjusted from 80)
    
    # Risk Management (Priority 1)
    stop_loss_pct: float = 0.025  # 2.5% stop loss (slightly wider)
    take_profit_pct: float = 0.04  # 4% take profit (2:1 reward:risk)
    trailing_stop_pct: float = 0.015  # 1.5% trailing stop
    max_position_risk_pct: float = 0.01  # Risk 1% of portfolio per trade
    max_portfolio_drawdown: float = 0.10  # Stop trading at 10% drawdown
    use_trailing_stop: bool = True
    
    # Position Sizing (Priority 2)
    max_position_size: float = 0.35  # Max 35% per trade
    min_position_size: float = 0.15  # Min 15% per trade (increased)
    use_dynamic_sizing: bool = True  # Enable dynamic position sizing
    
    # Volatility & Indicators (Priority 3 & 4)
    atr_period: int = 14
    atr_stop_multiplier: float = 2.5  # Stop loss at 2.5x ATR (wider to avoid false stops)
    use_atr_stops: bool = True  # Use ATR-based stops instead of fixed percentage
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    require_macd_confirmation: bool = False  # 🔑 DISABLED - Too restrictive, blocks good trades
    
    # Additional Safety
    require_volume_confirmation: bool = True
    volume_threshold: float = 1.1  # Require 110% of average volume (lowered from 120%)
    max_trades_per_day: int = 5  # Prevent overtrading

    @classmethod
    def load(cls) -> "BotConfig":
        env = os.environ
        return cls(
            binance_api_key=env.get("BINANCE_US_KEY", ""),
            binance_api_secret=env.get("BINANCE_US_SECRET", ""),
            symbol=env.get("BOT_SYMBOL", "BTC/USDT"),
            timeframe=env.get("BOT_TIMEFRAME", "1h"),
            short_window=int(env.get("BOT_SHORT_WINDOW", 12)),
            long_window=int(env.get("BOT_LONG_WINDOW", 26)),
            order_pct=float(env.get("BOT_ORDER_PCT", 0.25)),
            initial_usdt=float(env.get("BOT_INITIAL_USDT", 1000.0)),
            fee_rate=float(env.get("BOT_FEE_RATE", 0.00075)),
            slippage=float(env.get("BOT_SLIPPAGE", 0.0005)),
            dashboard_host=env.get("BOT_DASHBOARD_HOST", "0.0.0.0"),
            dashboard_port=int(env.get("BOT_DASHBOARD_PORT", 8000)),
            exchange_type=env.get("BOT_EXCHANGE_TYPE", "spot"),
            trades_log_path=env.get("BOT_TRADES_LOG_PATH", "data/trade_log.csv"),
            min_trend_strength=float(env.get("BOT_MIN_TREND_STRENGTH", 0.00005)),
            rsi_period=int(env.get("BOT_RSI_PERIOD", 14)),
            rsi_oversold=float(env.get("BOT_RSI_OVERSOLD", 25)),
            rsi_overbought=float(env.get("BOT_RSI_OVERBOUGHT", 75)),
            # Risk Management
            stop_loss_pct=float(env.get("BOT_STOP_LOSS_PCT", 0.025)),
            take_profit_pct=float(env.get("BOT_TAKE_PROFIT_PCT", 0.04)),
            trailing_stop_pct=float(env.get("BOT_TRAILING_STOP_PCT", 0.015)),
            max_position_risk_pct=float(env.get("BOT_MAX_POSITION_RISK_PCT", 0.01)),
            max_portfolio_drawdown=float(env.get("BOT_MAX_PORTFOLIO_DRAWDOWN", 0.10)),
            use_trailing_stop=env.get("BOT_USE_TRAILING_STOP", "true").lower() == "true",
            # Position Sizing
            max_position_size=float(env.get("BOT_MAX_POSITION_SIZE", 0.35)),
            min_position_size=float(env.get("BOT_MIN_POSITION_SIZE", 0.15)),
            use_dynamic_sizing=env.get("BOT_USE_DYNAMIC_SIZING", "true").lower() == "true",
            # ATR and MACD
            atr_period=int(env.get("BOT_ATR_PERIOD", 14)),
            atr_stop_multiplier=float(env.get("BOT_ATR_STOP_MULTIPLIER", 2.5)),
            use_atr_stops=env.get("BOT_USE_ATR_STOPS", "true").lower() == "true",
            macd_fast=int(env.get("BOT_MACD_FAST", 12)),
            macd_slow=int(env.get("BOT_MACD_SLOW", 26)),
            macd_signal=int(env.get("BOT_MACD_SIGNAL", 9)),
            require_macd_confirmation=env.get("BOT_REQUIRE_MACD_CONFIRMATION", "false").lower() == "true",
            # Additional Safety
            require_volume_confirmation=env.get("BOT_REQUIRE_VOLUME_CONFIRMATION", "true").lower() == "true",
            volume_threshold=float(env.get("BOT_VOLUME_THRESHOLD", 1.1)),
            max_trades_per_day=int(env.get("BOT_MAX_TRADES_PER_DAY", 5)),
            # Database
            database_url=env.get("BOT_DATABASE_URL", "sqlite:///data/trading.db"),
            enable_database=env.get("BOT_ENABLE_DATABASE", "true").lower() == "true",
            enable_csv_logging=env.get("BOT_ENABLE_CSV_LOGGING", "true").lower() == "true",
        )

