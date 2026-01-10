"""
EMA Crossover Strategy - Original strategy refactored to use BaseStrategy interface.

This is the original moving average crossover strategy with multiple filters:
- EMA crossover (trend detection)
- RSI filter (avoid overbought/oversold extremes)
- MACD confirmation (momentum confirmation)
- Volume confirmation (above average volume)
- ATR-based stop losses (volatility-adjusted)
- Dynamic position sizing (confidence-based)
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd

from .base_strategy import BaseStrategy, StrategySignal


class EMACrossoverStrategy(BaseStrategy):
    """EMA Crossover strategy with multiple technical filters"""
    
    def __init__(self, config: dict):
        super().__init__("EMA_Crossover", config)
        
        # EMA parameters
        self.short_window = config.get("short_window", 12)
        self.long_window = config.get("long_window", 26)
        
        # Filters
        self.min_trend_strength = config.get("min_trend_strength", 0.00005)
        self.rsi_period = config.get("rsi_period", 14)
        self.rsi_oversold = config.get("rsi_oversold", 25)
        self.rsi_overbought = config.get("rsi_overbought", 75)
        
        # Risk management
        self.atr_period = config.get("atr_period", 14)
        self.atr_stop_multiplier = config.get("atr_stop_multiplier", 2.5)
        self.use_atr_stops = config.get("use_atr_stops", True)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.025)
        self.take_profit_pct = config.get("take_profit_pct", 0.04)
        
        # MACD
        self.macd_fast = config.get("macd_fast", 12)
        self.macd_slow = config.get("macd_slow", 26)
        self.macd_signal = config.get("macd_signal", 9)
        self.require_macd_confirmation = config.get("require_macd_confirmation", False)
        
        # Volume
        self.require_volume_confirmation = config.get("require_volume_confirmation", True)
        self.volume_threshold = config.get("volume_threshold", 1.1)
        
        # Position sizing
        self.use_dynamic_sizing = config.get("use_dynamic_sizing", True)
        self.min_position_size = config.get("min_position_size", 0.15)
        self.max_position_size = config.get("max_position_size", 0.35)
    
    def compute_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        """Compute EMA crossover signal with filters"""
        
        # Use buffered candle data if provided, otherwise fetch from exchange
        if candle_data is not None and len(candle_data) > 0:
            ohlcv = candle_data
        else:
            history_limit = max(self.long_window * 2, 120)
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=history_limit)

        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        
        if len(df) < self.long_window:
            raise ValueError(f"Not enough candles for {self.name} (need {self.long_window}, got {len(df)})")

        # Calculate EMAs
        df["short_ema"] = df["close"].ewm(span=self.short_window, adjust=False).mean()
        df["long_ema"] = df["close"].ewm(span=self.long_window, adjust=False).mean()
        
        # Calculate RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # Calculate ATR
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift())
        df['low_close'] = abs(df['low'] - df['close'].shift())
        df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['true_range'].rolling(window=self.atr_period).mean()
        
        # Calculate MACD
        df['ema_fast'] = df['close'].ewm(span=self.macd_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.macd_slow, adjust=False).mean()
        df['macd'] = df['ema_fast'] - df['ema_slow']
        df['macd_signal'] = df['macd'].ewm(span=self.macd_signal, adjust=False).mean()
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
        confidence = 0.0
        
        # Volume confirmation check
        volume_confirmed = volume_ratio >= self.volume_threshold
        
        # MACD confirmation checks
        macd_bullish = macd_value > macd_signal_value and macd_histogram > 0
        macd_bearish = macd_value < macd_signal_value and macd_histogram < 0
        
        # Check for bullish crossover
        if last.short_ema > last.long_ema and prev.short_ema <= prev.long_ema:
            signal_valid = True
            confidence = min(1.0, trend_strength * 1000)  # Base confidence from trend strength
            
            # Apply filters
            if trend_strength < self.min_trend_strength:
                signal_valid = False
            if rsi_value >= self.rsi_overbought or rsi_value <= self.rsi_oversold:
                signal_valid = False
                confidence *= 0.5
            if self.require_volume_confirmation and not volume_confirmed:
                signal_valid = False
                confidence *= 0.7
            if self.require_macd_confirmation and not macd_bullish:
                signal_valid = False
                confidence *= 0.8
                
            if signal_valid:
                direction = "bullish"
                # Increase confidence if multiple confirmations
                if volume_confirmed:
                    confidence *= 1.2
                if macd_bullish:
                    confidence *= 1.1
        
        # Check for bearish crossover
        elif last.short_ema < last.long_ema and prev.short_ema >= prev.long_ema:
            signal_valid = True
            confidence = min(1.0, trend_strength * 1000)
            
            # Apply filters
            if trend_strength < self.min_trend_strength:
                signal_valid = False
            if rsi_value <= self.rsi_oversold or rsi_value >= self.rsi_overbought:
                signal_valid = False
                confidence *= 0.5
            if self.require_volume_confirmation and not volume_confirmed:
                signal_valid = False
                confidence *= 0.7
            if self.require_macd_confirmation and not macd_bearish:
                signal_valid = False
                confidence *= 0.8
                
            if signal_valid:
                direction = "bearish"
                if volume_confirmed:
                    confidence *= 1.2
                if macd_bearish:
                    confidence *= 1.1

        # Cap confidence at 1.0
        confidence = min(1.0, confidence)

        # Calculate stop loss and take profit levels
        stop_loss = 0.0
        take_profit = 0.0
        
        if direction == "bullish":
            if self.use_atr_stops:
                stop_loss = price - (atr_value * self.atr_stop_multiplier)
            else:
                stop_loss = price * (1 - self.stop_loss_pct)
            take_profit = price * (1 + self.take_profit_pct)
            
        elif direction == "bearish":
            if self.use_atr_stops:
                stop_loss = price + (atr_value * self.atr_stop_multiplier)
            else:
                stop_loss = price * (1 + self.stop_loss_pct)
            take_profit = price * (1 - self.take_profit_pct)
        
        # Calculate dynamic position size
        position_size = 0.0
        if direction != "neutral" and self.use_dynamic_sizing:
            position_size = self._calculate_position_size(
                confidence=confidence,
                rsi=rsi_value,
                atr=atr_value,
                price=price,
            )
        elif direction != "neutral":
            position_size = self.min_position_size

        # Build indicators dict
        indicators = {
            "short_ema": float(last.short_ema),
            "long_ema": float(last.long_ema),
            "rsi": rsi_value,
            "atr": atr_value,
            "macd": macd_value,
            "macd_signal": macd_signal_value,
            "macd_histogram": macd_histogram,
            "volume_ratio": volume_ratio,
            "trend_strength": trend_strength,
        }
        
        info = {
            "short_window": self.short_window,
            "long_window": self.long_window,
            "last_timestamp": int(last.timestamp),
            "trend_strength_pct": float(trend_strength * 100),
            "volume_confirmed": volume_confirmed,
            "macd_confirmed": (macd_bullish if direction == "bullish" else macd_bearish) if direction != "neutral" else False,
        }

        return StrategySignal(
            direction=direction,
            price=price,
            confidence=confidence,
            timestamp=datetime.fromtimestamp(int(last.timestamp) / 1000, tz=timezone.utc),
            strategy_name=self.name,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            indicators=indicators,
            info=info,
        )
    
    def _calculate_position_size(
        self,
        confidence: float,
        rsi: float,
        atr: float,
        price: float,
    ) -> float:
        """Calculate dynamic position size based on signal confidence and market conditions"""
        base_size = 0.2  # 20% base
        
        # Adjust for volatility (normalize ATR by price)
        atr_pct = (atr / price) if price > 0 else 0.02
        volatility_factor = min(1.0, 0.02 / atr_pct) if atr_pct > 0 else 1.0
        
        # Adjust for confidence
        confidence_factor = confidence
        
        # Reduce size near RSI extremes
        rsi_factor = 1.0
        if rsi > 70 or rsi < 30:
            rsi_factor = 0.7
        elif rsi > 60 or rsi < 40:
            rsi_factor = 0.85
        
        adjusted_size = base_size * volatility_factor * confidence_factor * rsi_factor
        return max(self.min_position_size, min(self.max_position_size, adjusted_size))
    
    def get_description(self) -> str:
        return f"EMA Crossover ({self.short_window}/{self.long_window}) with RSI, MACD, and Volume filters"
    
    def get_parameters(self) -> Dict[str, object]:
        return {
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
            "require_macd_confirmation": self.require_macd_confirmation,
            "require_volume_confirmation": self.require_volume_confirmation,
            "volume_threshold": self.volume_threshold,
            "use_dynamic_sizing": self.use_dynamic_sizing,
            "min_position_size": self.min_position_size,
            "max_position_size": self.max_position_size,
        }
