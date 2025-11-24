from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Literal

import pandas as pd


@dataclass
class StrategySignal:
    direction: Literal["bullish", "bearish", "neutral"]
    price: float
    short_ema: float
    long_ema: float
    trend_strength: float
    timestamp: datetime
    info: Dict[str, float]
    # New risk management fields
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_size: float = 0.0  # Dynamic position size
    atr: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "direction": self.direction,
            "price": self.price,
            "short_ema": self.short_ema,
            "long_ema": self.long_ema,
            "trend_strength": self.trend_strength,
            "timestamp": self.timestamp.isoformat(),
            "info": self.info,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": self.position_size,
            "atr": self.atr,
        }


def calculate_dynamic_position_size(
    signal_strength: float,
    rsi: float,
    atr: float,
    price: float,
    min_size: float = 0.1,
    max_size: float = 0.3,
) -> float:
    """
    Calculate dynamic position size based on:
    - Signal confidence (trend strength)
    - Market volatility (ATR)
    - RSI positioning
    """
    base_size = 0.2  # 20% base
    
    # Reduce size in high volatility (normalize ATR by price)
    atr_pct = (atr / price) if price > 0 else 0.02
    volatility_factor = min(1.0, 0.02 / atr_pct) if atr_pct > 0 else 1.0
    
    # Increase size for strong trends (trend_strength is already a ratio)
    strength_factor = min(1.5, 1.0 + (signal_strength * 500))
    
    # Reduce size near RSI extremes
    rsi_factor = 1.0
    if rsi > 70 or rsi < 30:
        rsi_factor = 0.7
    elif rsi > 60 or rsi < 40:
        rsi_factor = 0.85
    
    adjusted_size = base_size * volatility_factor * strength_factor * rsi_factor
    return max(min_size, min(max_size, adjusted_size))


def compute_signal(
    exchange,
    symbol: str,
    timeframe: str,
    short_window: int = 20,
    long_window: int = 50,
    candle_data: list = None,
    min_trend_strength: float = 0.0001,
    rsi_period: int = 14,
    rsi_oversold: float = 20,
    rsi_overbought: float = 80,
    # New parameters for Priority 1-4
    atr_period: int = 14,
    atr_stop_multiplier: float = 2.0,
    use_atr_stops: bool = True,
    stop_loss_pct: float = 0.02,
    take_profit_pct: float = 0.04,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    require_macd_confirmation: bool = True,
    require_volume_confirmation: bool = True,
    volume_threshold: float = 1.2,
    use_dynamic_sizing: bool = True,
    min_position_size: float = 0.1,
    max_position_size: float = 0.3,
) -> StrategySignal:
    """
    Enhanced strategy with multiple filters and risk management:
    1. EMA crossover (trend detection)
    2. Minimum trend strength filter (avoid weak signals)
    3. RSI filter (avoid overbought/oversold extremes)
    4. MACD confirmation (momentum confirmation)
    5. Volume confirmation (above average volume)
    6. ATR-based stop losses (volatility-adjusted)
    7. Dynamic position sizing (confidence-based)
    """
    # Use buffered candle data if provided, otherwise fetch from exchange
    if candle_data is not None and len(candle_data) > 0:
        ohlcv = candle_data
    else:
        history_limit = max(long_window * 2, 120)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=history_limit)

    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    if len(df) < long_window:
        raise ValueError("not enough candles for the configured long window")

    # Calculate EMAs
    df["short_ema"] = df["close"].ewm(span=short_window, adjust=False).mean()
    df["long_ema"] = df["close"].ewm(span=long_window, adjust=False).mean()
    
    # Calculate RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))
    
    # Calculate ATR (Average True Range) - Priority 3
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift())
    df['low_close'] = abs(df['low'] - df['close'].shift())
    df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['atr'] = df['true_range'].rolling(window=atr_period).mean()
    
    # Calculate MACD - Priority 4
    df['ema_fast'] = df['close'].ewm(span=macd_fast, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=macd_slow, adjust=False).mean()
    df['macd'] = df['ema_fast'] - df['ema_slow']
    df['macd_signal'] = df['macd'].ewm(span=macd_signal, adjust=False).mean()
    df['macd_histogram'] = df['macd'] - df['macd_signal']
    
    # Calculate volume moving average
    df["volume_ma"] = df["volume"].rolling(window=20).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Calculate trend strength
    price = float(last.close)
    trend_strength = abs(last.short_ema - last.long_ema) / price
    
    # Get indicator values
    rsi_value = float(last.rsi) if pd.notna(last.rsi) else 50.0
    atr_value = float(last.atr) if pd.notna(last.atr) else price * 0.02
    volume_ratio = float(last.volume / last.volume_ma) if pd.notna(last.volume_ma) and last.volume_ma > 0 else 1.0
    macd_value = float(last.macd) if pd.notna(last.macd) else 0.0
    macd_signal_value = float(last.macd_signal) if pd.notna(last.macd_signal) else 0.0
    macd_histogram = float(last.macd_histogram) if pd.notna(last.macd_histogram) else 0.0
    
    # Initialize as neutral
    direction = "neutral"
    
    # Volume confirmation check
    volume_confirmed = volume_ratio >= volume_threshold
    
    # MACD confirmation checks
    macd_bullish = macd_value > macd_signal_value and macd_histogram > 0
    macd_bearish = macd_value < macd_signal_value and macd_histogram < 0
    
    # Check for bullish crossover
    if last.short_ema > last.long_ema and prev.short_ema <= prev.long_ema:
        signal_valid = True
        
        # Apply filters
        if trend_strength < min_trend_strength:
            signal_valid = False
        if rsi_value >= rsi_overbought or rsi_value <= rsi_oversold:
            signal_valid = False
        if require_volume_confirmation and not volume_confirmed:
            signal_valid = False
        if require_macd_confirmation and not macd_bullish:
            signal_valid = False
            
        if signal_valid:
            direction = "bullish"
    
    # Check for bearish crossover
    elif last.short_ema < last.long_ema and prev.short_ema >= prev.long_ema:
        signal_valid = True
        
        # Apply filters
        if trend_strength < min_trend_strength:
            signal_valid = False
        if rsi_value <= rsi_oversold or rsi_value >= rsi_overbought:
            signal_valid = False
        if require_volume_confirmation and not volume_confirmed:
            signal_valid = False
        if require_macd_confirmation and not macd_bearish:
            signal_valid = False
            
        if signal_valid:
            direction = "bearish"

    # Calculate stop loss and take profit levels - Priority 1
    stop_loss = 0.0
    take_profit = 0.0
    
    if direction == "bullish":
        if use_atr_stops:
            # ATR-based stop loss (more dynamic)
            stop_loss = price - (atr_value * atr_stop_multiplier)
        else:
            # Fixed percentage stop loss
            stop_loss = price * (1 - stop_loss_pct)
        take_profit = price * (1 + take_profit_pct)
        
    elif direction == "bearish":
        if use_atr_stops:
            # ATR-based stop loss
            stop_loss = price + (atr_value * atr_stop_multiplier)
        else:
            # Fixed percentage stop loss
            stop_loss = price * (1 + stop_loss_pct)
        take_profit = price * (1 - take_profit_pct)
    
    # Calculate dynamic position size - Priority 2
    position_size = 0.0
    if direction != "neutral" and use_dynamic_sizing:
        position_size = calculate_dynamic_position_size(
            signal_strength=trend_strength,
            rsi=rsi_value,
            atr=atr_value,
            price=price,
            min_size=min_position_size,
            max_size=max_position_size,
        )
    elif direction != "neutral":
        # Use default position size if dynamic sizing disabled
        position_size = min_position_size

    info = {
        "short_window": short_window,
        "long_window": long_window,
        "last_timestamp": int(last.timestamp),
        "rsi": rsi_value,
        "volume_ratio": volume_ratio,
        "trend_strength_pct": float(trend_strength * 100),
        "macd": macd_value,
        "macd_signal": macd_signal_value,
        "macd_histogram": macd_histogram,
        "volume_confirmed": volume_confirmed,
        "macd_confirmed": (macd_bullish if direction == "bullish" else macd_bearish) if direction != "neutral" else False,
    }

    return StrategySignal(
        direction=direction,
        price=price,
        short_ema=float(last.short_ema),
        long_ema=float(last.long_ema),
        trend_strength=trend_strength,
        timestamp=datetime.fromtimestamp(int(last.timestamp) / 1000, tz=timezone.utc),
        info=info,
        stop_loss=stop_loss,
        take_profit=take_profit,
        position_size=position_size,
        atr=atr_value,
    )

