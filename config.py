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
    min_position_size: float = 0.10  # Min 10% per trade (flexible for manual trading)
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
    
    # Multi-Strategy Configuration
    use_multi_strategy: bool = True  # Enable multiple strategies
    strategy_aggregation_mode: str = "weighted_voting"  # voting, weighted_voting, unanimous, any, best
    min_signal_confidence: float = 0.3  # Minimum confidence threshold
    
    # Strategy: EMA Crossover (enabled by default)
    strategy_ema_enabled: bool = True
    strategy_ema_weight: float = 1.0
    
    # Strategy: RSI + Bollinger Bands Mean Reversion
    strategy_rsi_bb_enabled: bool = True
    strategy_rsi_bb_weight: float = 1.0
    strategy_rsi_bb_rsi_oversold: float = 30
    strategy_rsi_bb_rsi_overbought: float = 70
    strategy_rsi_bb_bb_period: int = 20
    strategy_rsi_bb_bb_std_dev: float = 2.0
    strategy_rsi_bb_stop_loss_pct: float = 0.02
    strategy_rsi_bb_take_profit_pct: float = 0.03
    strategy_rsi_bb_rsi_extreme_oversold: float = 20
    strategy_rsi_bb_rsi_extreme_overbought: float = 80
    strategy_rsi_bb_bb_touch_threshold: float = 0.995
    strategy_rsi_bb_require_both_signals: bool = True
    strategy_rsi_bb_use_volume_filter: bool = True
    strategy_rsi_bb_volume_threshold: float = 1.0

    # Strategy: MACD + Volume Momentum
    strategy_macd_enabled: bool = True
    strategy_macd_weight: float = 1.0
    strategy_macd_fast_period: int = 12
    strategy_macd_slow_period: int = 26
    strategy_macd_signal_period: int = 9
    strategy_macd_volume_multiplier: float = 1.3
    strategy_macd_require_zero_cross: bool = False
    # |histogram| / price minimum to count as a confirmed signal (not a raw
    # dollar value — see strategies/macd_volume_strategy.py comment). Used to
    # be stuck at the code default of 0.0 because it was never read here,
    # which let every fresh crossover's near-zero histogram count as
    # "confirmed" and caused overtrading (docs/backtest_reports, 2026-07-08).
    strategy_macd_histogram_threshold: float = 0.0003
    strategy_macd_stop_loss_pct: float = 0.025
    strategy_macd_take_profit_pct: float = 0.05
    strategy_macd_signal_lookback: int = 3
    strategy_macd_volume_ma_period: int = 20
    strategy_macd_use_momentum_filter: bool = True
    strategy_macd_momentum_period: int = 10
    strategy_macd_min_momentum: float = 0.005
    strategy_macd_detect_divergence: bool = True
    strategy_macd_divergence_lookback: int = 14
    
    # Strategy: LLM Pattern Analysis (Ollama)
    # Disabled by default: unvalidated in backtests (produces zero trades,
    # see docs/LLM_NO_TRADES_ANALYSIS.md) and its Ollama-call timeout only
    # enforces on the main thread, so a hung local LLM call has no hard
    # timeout if this strategy runs on a worker thread during live trading.
    strategy_llm_enabled: bool = False
    strategy_llm_weight: float = 1.0
    llm_ollama_url: str = "http://localhost:11434"
    llm_ollama_model: str = "mistral"  # or llama2, codellama, phi, etc.
    llm_lookback_days: int = 7
    llm_cache_minutes: int = 15  # How often to refresh analysis
    llm_timeout_seconds: int = 120  # Increased for slower systems
    llm_temperature: float = 0.3  # LLM temperature for response consistency (0.0-1.0)
    llm_num_predict: int = 1000  # Max tokens to generate (affects speed and detail)
    llm_require_patterns: bool = False  # Require at least one pattern found
    llm_backtest_sample_interval: int = 12  # Analyze every Nth candle in backtests (12 = once per hour on 5m)
    
    # RAG (Retrieval Augmented Generation) for LLM
    llm_use_rag: bool = True  # Use semantic search to retrieve relevant trades
    llm_rag_num_results: int = 10  # Number of similar trades to retrieve
    llm_rag_min_trades: int = 5  # Minimum trades needed to use RAG
    llm_rag_persist_dir: str = "./data/chroma_db"  # Vector database storage location
    
    # Dashboard Security Settings
    dashboard_auth_enabled: bool = True  # Enable/disable authentication
    dashboard_username: str = "admin"  # Username for dashboard access
    dashboard_password: str = ""  # Password (can be bcrypt hash or plaintext)
    dashboard_api_key: str = ""  # API key for programmatic access
    dashboard_require_https: bool = False  # Require HTTPS for dashboard access
    enable_rate_limiting: bool = True  # Enable rate limiting
    rate_limit_per_minute: int = 60  # Max requests per minute
    allowed_origins: str = "*"  # CORS allowed origins (comma-separated)
    
    # Live Trading Configuration (CRITICAL - Handle with care!)
    trading_mode: str = "paper"  # "paper" | "dry_run" | "live"
    live_trading_enabled: bool = False  # Safety flag - must be explicitly enabled
    require_trade_confirmation: bool = True  # Require confirmation for trades > threshold
    confirmation_threshold_usd: float = 100.0  # Threshold for trade confirmation
    max_single_trade_usd: float = 500.0  # Maximum single trade size in USD
    api_retry_attempts: int = 3  # Number of retry attempts for API calls
    api_retry_delay_seconds: float = 1.0  # Delay between retry attempts (exponential backoff applied per attempt)
    order_poll_timeout_seconds: float = 10.0  # Max time to wait for a market order to reach a terminal state
    order_poll_interval_seconds: float = 0.5  # Polling cadence while waiting for terminal state

    # Exchange-native protective orders (Binance spot STOP_LOSS_LIMIT)
    exchange_stop_loss_enabled: bool = True  # Place a stop-limit sell after each buy (live only)
    exchange_stop_update_on_trailing: bool = True  # Replace the order when the trailing stop ratchets up

    # All-time peak portfolio equity (USDT) for drawdown kill-switch
    portfolio_drawdown_kill_enabled: bool = True

    # Kline websocket watchdog — alert if no candle activity for this long
    ws_watchdog_enabled: bool = True
    ws_stale_alert_seconds: float = 180.0

    @classmethod
    def load(cls) -> "BotConfig":
        """
        Load configuration from database (if available) with fallback to environment variables.
        Database values take precedence over env vars for strategy parameters.
        """
        env = os.environ
        
        # Try to load strategy-specific configs from database
        db_config = {}
        try:
            from database import get_database
            db = get_database()
            db_config = db.get_all_strategy_configs()
        except Exception:
            # Database not available or not initialized, use env vars only
            pass
        
        # Helper function to get value: database first, then env, then default
        def get_val(db_key, env_key, default, value_type=str):
            # Check database first
            if db_key in db_config:
                db_val = db_config[db_key]
                # Database stores all values as strings, need to convert based on type
                if value_type == bool:
                    # Handle both string "True"/"False" and actual booleans
                    if isinstance(db_val, bool):
                        return db_val
                    return str(db_val).lower() in ("true", "1", "yes")
                elif value_type == int:
                    return int(db_val)
                elif value_type == float:
                    return float(db_val)
                else:
                    return db_val
            
            # Fall back to environment variable
            env_val = env.get(env_key)
            if env_val is None:
                return default
            
            if value_type == bool:
                return env_val.lower() == "true"
            elif value_type == int:
                return int(env_val)
            elif value_type == float:
                return float(env_val)
            else:
                return env_val
        
        return cls(
            binance_api_key=env.get("BINANCE_US_KEY", ""),
            binance_api_secret=env.get("BINANCE_US_SECRET", ""),
            symbol=get_val("symbol", "BOT_SYMBOL", "BTC/USDT", str),
            timeframe=get_val("timeframe", "BOT_TIMEFRAME", "1h", str),
            short_window=get_val("short_window", "BOT_SHORT_WINDOW", 12, int),
            long_window=get_val("long_window", "BOT_LONG_WINDOW", 26, int),
            order_pct=get_val("order_pct", "BOT_ORDER_PCT", 0.25, float),
            initial_usdt=get_val("initial_usdt", "BOT_INITIAL_USDT", 1000.0, float),
            fee_rate=float(env.get("BOT_FEE_RATE", 0.00075)),
            slippage=float(env.get("BOT_SLIPPAGE", 0.0005)),
            dashboard_host=env.get("BOT_DASHBOARD_HOST", "0.0.0.0"),
            dashboard_port=int(env.get("BOT_DASHBOARD_PORT", 8000)),
            exchange_type=env.get("BOT_EXCHANGE_TYPE", "spot"),
            trades_log_path=env.get("BOT_TRADES_LOG_PATH", "data/trade_log.csv"),
            min_trend_strength=get_val("min_trend_strength", "BOT_MIN_TREND_STRENGTH", 0.00005, float),
            rsi_period=get_val("rsi_period", "BOT_RSI_PERIOD", 14, int),
            rsi_oversold=get_val("rsi_oversold", "BOT_RSI_OVERSOLD", 25.0, float),
            rsi_overbought=get_val("rsi_overbought", "BOT_RSI_OVERBOUGHT", 75.0, float),
            # Risk Management
            stop_loss_pct=get_val("stop_loss_pct", "BOT_STOP_LOSS_PCT", 0.025, float),
            take_profit_pct=get_val("take_profit_pct", "BOT_TAKE_PROFIT_PCT", 0.04, float),
            trailing_stop_pct=get_val("trailing_stop_pct", "BOT_TRAILING_STOP_PCT", 0.015, float),
            max_position_risk_pct=float(env.get("BOT_MAX_POSITION_RISK_PCT", 0.01)),
            max_portfolio_drawdown=float(env.get("BOT_MAX_PORTFOLIO_DRAWDOWN", 0.10)),
            use_trailing_stop=get_val("use_trailing_stop", "BOT_USE_TRAILING_STOP", True, bool),
            # Position Sizing
            max_position_size=get_val("max_position_size", "BOT_MAX_POSITION_SIZE", 0.35, float),
            min_position_size=get_val("min_position_size", "BOT_MIN_POSITION_SIZE", 0.10, float),
            use_dynamic_sizing=get_val("use_dynamic_sizing", "BOT_USE_DYNAMIC_SIZING", True, bool),
            # ATR and MACD
            atr_period=get_val("atr_period", "BOT_ATR_PERIOD", 14, int),
            atr_stop_multiplier=get_val("atr_stop_multiplier", "BOT_ATR_STOP_MULTIPLIER", 2.5, float),
            use_atr_stops=get_val("use_atr_stops", "BOT_USE_ATR_STOPS", True, bool),
            macd_fast=int(env.get("BOT_MACD_FAST", 12)),
            macd_slow=int(env.get("BOT_MACD_SLOW", 26)),
            macd_signal=int(env.get("BOT_MACD_SIGNAL", 9)),
            require_macd_confirmation=get_val("require_macd_confirmation", "BOT_REQUIRE_MACD_CONFIRMATION", False, bool),
            # Additional Safety
            require_volume_confirmation=get_val("require_volume_confirmation", "BOT_REQUIRE_VOLUME_CONFIRMATION", True, bool),
            volume_threshold=get_val("volume_threshold", "BOT_VOLUME_THRESHOLD", 1.1, float),
            max_trades_per_day=get_val("max_trades_per_day", "BOT_MAX_TRADES_PER_DAY", 5, int),
            # Database
            database_url=env.get("BOT_DATABASE_URL", "sqlite:///data/trading.db"),
            enable_database=env.get("BOT_ENABLE_DATABASE", "true").lower() == "true",
            enable_csv_logging=env.get("BOT_ENABLE_CSV_LOGGING", "true").lower() == "true",
            # Multi-Strategy (can be overridden by database)
            use_multi_strategy=env.get("BOT_USE_MULTI_STRATEGY", "true").lower() == "true",
            strategy_aggregation_mode=get_val("strategy_aggregation_mode", "BOT_STRATEGY_AGGREGATION_MODE", "weighted_voting", str),
            min_signal_confidence=get_val("min_signal_confidence", "BOT_MIN_SIGNAL_CONFIDENCE", 0.3, float),
            # EMA Strategy (can be overridden by database)
            strategy_ema_enabled=get_val("strategy_ema_enabled", "BOT_STRATEGY_EMA_ENABLED", True, bool),
            strategy_ema_weight=get_val("strategy_ema_weight", "BOT_STRATEGY_EMA_WEIGHT", 1.0, float),
            # RSI+BB Strategy (can be overridden by database)
            strategy_rsi_bb_enabled=get_val("strategy_rsi_bb_enabled", "BOT_STRATEGY_RSI_BB_ENABLED", True, bool),
            strategy_rsi_bb_weight=get_val("strategy_rsi_bb_weight", "BOT_STRATEGY_RSI_BB_WEIGHT", 1.0, float),
            strategy_rsi_bb_rsi_oversold=get_val("strategy_rsi_bb_rsi_oversold", "BOT_STRATEGY_RSI_BB_RSI_OVERSOLD", 30.0, float),
            strategy_rsi_bb_rsi_overbought=get_val("strategy_rsi_bb_rsi_overbought", "BOT_STRATEGY_RSI_BB_RSI_OVERBOUGHT", 70.0, float),
            strategy_rsi_bb_bb_period=get_val("strategy_rsi_bb_bb_period", "BOT_STRATEGY_RSI_BB_BB_PERIOD", 20, int),
            strategy_rsi_bb_bb_std_dev=get_val("strategy_rsi_bb_bb_std_dev", "BOT_STRATEGY_RSI_BB_BB_STD_DEV", 2.0, float),
            strategy_rsi_bb_stop_loss_pct=get_val("strategy_rsi_bb_stop_loss_pct", "BOT_STRATEGY_RSI_BB_STOP_LOSS_PCT", 0.02, float),
            strategy_rsi_bb_take_profit_pct=get_val("strategy_rsi_bb_take_profit_pct", "BOT_STRATEGY_RSI_BB_TAKE_PROFIT_PCT", 0.03, float),
            strategy_rsi_bb_rsi_extreme_oversold=get_val("strategy_rsi_bb_rsi_extreme_oversold", "BOT_STRATEGY_RSI_BB_RSI_EXTREME_OVERSOLD", 20.0, float),
            strategy_rsi_bb_rsi_extreme_overbought=get_val("strategy_rsi_bb_rsi_extreme_overbought", "BOT_STRATEGY_RSI_BB_RSI_EXTREME_OVERBOUGHT", 80.0, float),
            strategy_rsi_bb_bb_touch_threshold=get_val("strategy_rsi_bb_bb_touch_threshold", "BOT_STRATEGY_RSI_BB_BB_TOUCH_THRESHOLD", 0.995, float),
            strategy_rsi_bb_require_both_signals=get_val("strategy_rsi_bb_require_both_signals", "BOT_STRATEGY_RSI_BB_REQUIRE_BOTH_SIGNALS", True, bool),
            strategy_rsi_bb_use_volume_filter=get_val("strategy_rsi_bb_use_volume_filter", "BOT_STRATEGY_RSI_BB_USE_VOLUME_FILTER", True, bool),
            strategy_rsi_bb_volume_threshold=get_val("strategy_rsi_bb_volume_threshold", "BOT_STRATEGY_RSI_BB_VOLUME_THRESHOLD", 1.0, float),
            # MACD+Volume Strategy (can be overridden by database)
            strategy_macd_enabled=get_val("strategy_macd_enabled", "BOT_STRATEGY_MACD_ENABLED", True, bool),
            strategy_macd_weight=get_val("strategy_macd_weight", "BOT_STRATEGY_MACD_WEIGHT", 1.0, float),
            strategy_macd_fast_period=get_val("strategy_macd_fast_period", "BOT_STRATEGY_MACD_FAST_PERIOD", 12, int),
            strategy_macd_slow_period=get_val("strategy_macd_slow_period", "BOT_STRATEGY_MACD_SLOW_PERIOD", 26, int),
            strategy_macd_signal_period=get_val("strategy_macd_signal_period", "BOT_STRATEGY_MACD_SIGNAL_PERIOD", 9, int),
            strategy_macd_volume_multiplier=get_val("strategy_macd_volume_multiplier", "BOT_STRATEGY_MACD_VOLUME_MULTIPLIER", 1.3, float),
            strategy_macd_require_zero_cross=get_val("strategy_macd_require_zero_cross", "BOT_STRATEGY_MACD_REQUIRE_ZERO_CROSS", False, bool),
            strategy_macd_histogram_threshold=get_val("strategy_macd_histogram_threshold", "BOT_STRATEGY_MACD_HISTOGRAM_THRESHOLD", 0.0003, float),
            strategy_macd_stop_loss_pct=get_val("strategy_macd_stop_loss_pct", "BOT_STRATEGY_MACD_STOP_LOSS_PCT", 0.025, float),
            strategy_macd_take_profit_pct=get_val("strategy_macd_take_profit_pct", "BOT_STRATEGY_MACD_TAKE_PROFIT_PCT", 0.05, float),
            strategy_macd_signal_lookback=get_val("strategy_macd_signal_lookback", "BOT_STRATEGY_MACD_SIGNAL_LOOKBACK", 3, int),
            strategy_macd_volume_ma_period=get_val("strategy_macd_volume_ma_period", "BOT_STRATEGY_MACD_VOLUME_MA_PERIOD", 20, int),
            strategy_macd_use_momentum_filter=get_val("strategy_macd_use_momentum_filter", "BOT_STRATEGY_MACD_USE_MOMENTUM_FILTER", True, bool),
            strategy_macd_momentum_period=get_val("strategy_macd_momentum_period", "BOT_STRATEGY_MACD_MOMENTUM_PERIOD", 10, int),
            strategy_macd_min_momentum=get_val("strategy_macd_min_momentum", "BOT_STRATEGY_MACD_MIN_MOMENTUM", 0.005, float),
            strategy_macd_detect_divergence=get_val("strategy_macd_detect_divergence", "BOT_STRATEGY_MACD_DETECT_DIVERGENCE", True, bool),
            strategy_macd_divergence_lookback=get_val("strategy_macd_divergence_lookback", "BOT_STRATEGY_MACD_DIVERGENCE_LOOKBACK", 14, int),
            # LLM Pattern Strategy (can be overridden by database)
            strategy_llm_enabled=get_val("strategy_llm_enabled", "BOT_STRATEGY_LLM_ENABLED", True, bool),
            strategy_llm_weight=get_val("strategy_llm_weight", "BOT_STRATEGY_LLM_WEIGHT", 1.0, float),
            llm_ollama_url=get_val("llm_ollama_url", "BOT_LLM_OLLAMA_URL", "http://localhost:11434", str),
            llm_ollama_model=get_val("llm_ollama_model", "BOT_LLM_OLLAMA_MODEL", "mistral", str),
            llm_lookback_days=get_val("llm_lookback_days", "BOT_LLM_LOOKBACK_DAYS", 7, int),
            llm_cache_minutes=get_val("llm_cache_minutes", "BOT_LLM_CACHE_MINUTES", 15, int),
            llm_timeout_seconds=get_val("llm_timeout_seconds", "BOT_LLM_TIMEOUT_SECONDS", 60, int),
            llm_temperature=get_val("llm_temperature", "BOT_LLM_TEMPERATURE", 0.3, float),
            llm_num_predict=get_val("llm_num_predict", "BOT_LLM_NUM_PREDICT", 1000, int),
            llm_require_patterns=get_val("llm_require_patterns", "BOT_LLM_REQUIRE_PATTERNS", False, bool),
            llm_backtest_sample_interval=get_val("llm_backtest_sample_interval", "BOT_LLM_BACKTEST_SAMPLE_INTERVAL", 12, int),
            # RAG Configuration
            llm_use_rag=get_val("llm_use_rag", "BOT_LLM_USE_RAG", True, bool),
            llm_rag_num_results=get_val("llm_rag_num_results", "BOT_LLM_RAG_NUM_RESULTS", 10, int),
            llm_rag_min_trades=get_val("llm_rag_min_trades", "BOT_LLM_RAG_MIN_TRADES", 5, int),
            llm_rag_persist_dir=get_val("llm_rag_persist_dir", "BOT_LLM_RAG_PERSIST_DIR", "./data/chroma_db", str),
            # Dashboard Security
            dashboard_auth_enabled=env.get("DASHBOARD_AUTH_ENABLED", "true").lower() == "true",
            dashboard_username=env.get("DASHBOARD_USERNAME", "admin"),
            dashboard_password=env.get("DASHBOARD_PASSWORD", ""),
            dashboard_api_key=env.get("DASHBOARD_API_KEY", ""),
            dashboard_require_https=env.get("DASHBOARD_REQUIRE_HTTPS", "false").lower() == "true",
            enable_rate_limiting=env.get("DASHBOARD_ENABLE_RATE_LIMITING", "true").lower() == "true",
            rate_limit_per_minute=int(env.get("DASHBOARD_RATE_LIMIT_PER_MINUTE", 60)),
            allowed_origins=env.get("DASHBOARD_ALLOWED_ORIGINS", "*"),
            # Live Trading Configuration
            trading_mode=env.get("BOT_TRADING_MODE", "paper"),
            live_trading_enabled=env.get("BOT_LIVE_TRADING_ENABLED", "false").lower() == "true",
            require_trade_confirmation=env.get("BOT_REQUIRE_TRADE_CONFIRMATION", "true").lower() == "true",
            confirmation_threshold_usd=float(env.get("BOT_CONFIRMATION_THRESHOLD_USD", 100.0)),
            max_single_trade_usd=float(env.get("BOT_MAX_SINGLE_TRADE_USD", 500.0)),
            api_retry_attempts=int(env.get("BOT_API_RETRY_ATTEMPTS", 3)),
            api_retry_delay_seconds=float(env.get("BOT_API_RETRY_DELAY_SECONDS", 1.0)),
            order_poll_timeout_seconds=float(env.get("BOT_ORDER_POLL_TIMEOUT_SECONDS", 10.0)),
            order_poll_interval_seconds=float(env.get("BOT_ORDER_POLL_INTERVAL_SECONDS", 0.5)),
            exchange_stop_loss_enabled=env.get("BOT_EXCHANGE_STOP_LOSS_ENABLED", "true").lower() == "true",
            exchange_stop_update_on_trailing=env.get("BOT_EXCHANGE_STOP_UPDATE_ON_TRAILING", "true").lower() == "true",
            portfolio_drawdown_kill_enabled=env.get("BOT_PORTFOLIO_DRAWDOWN_KILL_ENABLED", "true").lower() == "true",
            ws_watchdog_enabled=env.get("BOT_WS_WATCHDOG_ENABLED", "true").lower() == "true",
            ws_stale_alert_seconds=float(env.get("BOT_WS_STALE_ALERT_SECONDS", 180.0)),
        )
    
    def get_strategy_configs(self) -> dict:
        """Get configuration for all strategies"""
        return {
            "ema_crossover": {
                "enabled": self.strategy_ema_enabled,
                "weight": self.strategy_ema_weight,
                "short_window": self.short_window,
                "long_window": self.long_window,
                "min_trend_strength": self.min_trend_strength,
                "rsi_period": self.rsi_period,
                "rsi_oversold": self.rsi_oversold,
                "rsi_overbought": self.rsi_overbought,
                "atr_period": self.atr_period,
                "atr_stop_multiplier": self.atr_stop_multiplier,
                "use_atr_stops": self.use_atr_stops,
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
                "macd_fast": self.macd_fast,
                "macd_slow": self.macd_slow,
                "macd_signal": self.macd_signal,
                "require_macd_confirmation": self.require_macd_confirmation,
                "require_volume_confirmation": self.require_volume_confirmation,
                "volume_threshold": self.volume_threshold,
                "use_dynamic_sizing": self.use_dynamic_sizing,
                "min_position_size": self.min_position_size,
                "max_position_size": self.max_position_size,
            },
            "rsi_bb": {
                "enabled": self.strategy_rsi_bb_enabled,
                "weight": self.strategy_rsi_bb_weight,
                "rsi_period": self.rsi_period,
                "rsi_oversold": self.strategy_rsi_bb_rsi_oversold,
                "rsi_overbought": self.strategy_rsi_bb_rsi_overbought,
                "bb_period": self.strategy_rsi_bb_bb_period,
                "bb_std_dev": self.strategy_rsi_bb_bb_std_dev,
                "atr_period": self.atr_period,
                "atr_stop_multiplier": self.atr_stop_multiplier,
                "use_atr_stops": self.use_atr_stops,
                "stop_loss_pct": self.strategy_rsi_bb_stop_loss_pct,
                "take_profit_pct": self.strategy_rsi_bb_take_profit_pct,
                "rsi_extreme_oversold": self.strategy_rsi_bb_rsi_extreme_oversold,
                "rsi_extreme_overbought": self.strategy_rsi_bb_rsi_extreme_overbought,
                "bb_touch_threshold": self.strategy_rsi_bb_bb_touch_threshold,
                "require_both_signals": self.strategy_rsi_bb_require_both_signals,
                "use_volume_filter": self.strategy_rsi_bb_use_volume_filter,
                "volume_threshold": self.strategy_rsi_bb_volume_threshold,
                "use_dynamic_sizing": self.use_dynamic_sizing,
                "min_position_size": self.min_position_size,
                "max_position_size": self.max_position_size,
            },
            "macd_volume": {
                "enabled": self.strategy_macd_enabled,
                "weight": self.strategy_macd_weight,
                "macd_fast_period": self.strategy_macd_fast_period,
                "macd_slow_period": self.strategy_macd_slow_period,
                "macd_signal_period": self.strategy_macd_signal_period,
                "volume_multiplier": self.strategy_macd_volume_multiplier,
                "require_zero_cross": self.strategy_macd_require_zero_cross,
                "histogram_threshold": self.strategy_macd_histogram_threshold,
                "atr_period": self.atr_period,
                "atr_stop_multiplier": self.atr_stop_multiplier,
                "use_atr_stops": self.use_atr_stops,
                "stop_loss_pct": self.strategy_macd_stop_loss_pct,
                "take_profit_pct": self.strategy_macd_take_profit_pct,
                "signal_lookback": self.strategy_macd_signal_lookback,
                "volume_ma_period": self.strategy_macd_volume_ma_period,
                "use_momentum_filter": self.strategy_macd_use_momentum_filter,
                "momentum_period": self.strategy_macd_momentum_period,
                "min_momentum": self.strategy_macd_min_momentum,
                "detect_divergence": self.strategy_macd_detect_divergence,
                "divergence_lookback": self.strategy_macd_divergence_lookback,
                "use_dynamic_sizing": self.use_dynamic_sizing,
                "min_position_size": self.min_position_size,
                "max_position_size": self.max_position_size,
                "use_volume_filter": self.require_volume_confirmation,
            },
            "llm_pattern": {
                "enabled": self.strategy_llm_enabled,
                "weight": self.strategy_llm_weight,
                "llm_ollama_url": self.llm_ollama_url,
                "llm_ollama_model": self.llm_ollama_model,
                "llm_lookback_days": self.llm_lookback_days,
                "llm_cache_minutes": self.llm_cache_minutes,
                "llm_timeout_seconds": self.llm_timeout_seconds,
                "llm_temperature": self.llm_temperature,
                "llm_num_predict": self.llm_num_predict,
                "llm_require_patterns": self.llm_require_patterns,
                "llm_backtest_sample_interval": self.llm_backtest_sample_interval,
                # RAG Configuration
                "llm_use_rag": self.llm_use_rag,
                "llm_rag_num_results": self.llm_rag_num_results,
                "llm_rag_min_trades": self.llm_rag_min_trades,
                "llm_rag_persist_dir": self.llm_rag_persist_dir,
                # Include other risk management params for fallback
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
                "min_position_size": self.min_position_size,
                "max_position_size": self.max_position_size,
            }
        }

