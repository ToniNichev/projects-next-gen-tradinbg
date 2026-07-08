"""
MACD + Volume Momentum Strategy

This strategy focuses on momentum breakouts by combining:
- MACD (Moving Average Convergence Divergence) for momentum direction
- Volume confirmation for breakout strength
- Histogram analysis for momentum acceleration

Complements EMA (trend) and RSI+BB (mean-reversion) strategies by:
- Catching strong breakout moves early
- Confirming trend strength with volume
- Detecting momentum divergences for reversal warnings

Best in: Trending markets with volume, breakout scenarios
Avoids: Choppy, low-volume consolidation periods
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd
import numpy as np

from .base_strategy import BaseStrategy, StrategySignal


class MACDVolumeStrategy(BaseStrategy):
    """Momentum breakout strategy using MACD and Volume confirmation"""
    
    def __init__(self, config: dict):
        super().__init__("MACD_Volume_Momentum", config)
        
        # MACD parameters
        self.macd_fast_period = config.get("macd_fast_period", 12)
        self.macd_slow_period = config.get("macd_slow_period", 26)
        self.macd_signal_period = config.get("macd_signal_period", 9)
        
        # Signal thresholds
        self.histogram_threshold = config.get("histogram_threshold", 0.0)  # Min histogram value
        self.require_zero_cross = config.get("require_zero_cross", False)  # MACD must cross 0-line
        self.signal_lookback = config.get("signal_lookback", 3)  # Bars to confirm crossover
        
        # Volume confirmation
        self.use_volume_filter = config.get("use_volume_filter", True)
        self.volume_ma_period = config.get("volume_ma_period", 20)
        self.volume_multiplier = config.get("volume_multiplier", 1.3)  # Volume > 1.3x average
        
        # Momentum filters
        self.use_momentum_filter = config.get("use_momentum_filter", True)
        self.momentum_period = config.get("momentum_period", 10)
        self.min_momentum = config.get("min_momentum", 0.005)  # 0.5% minimum momentum
        
        # Divergence detection
        self.detect_divergence = config.get("detect_divergence", True)
        self.divergence_lookback = config.get("divergence_lookback", 14)
        
        # Risk management
        self.atr_period = config.get("atr_period", 14)
        self.atr_stop_multiplier = config.get("atr_stop_multiplier", 2.5)  # Wider for momentum trades
        self.use_atr_stops = config.get("use_atr_stops", True)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.025)  # 2.5% default
        self.take_profit_pct = config.get("take_profit_pct", 0.05)  # 5% target (higher for breakouts)
        
        # Position sizing
        self.use_dynamic_sizing = config.get("use_dynamic_sizing", True)
        self.min_position_size = config.get("min_position_size", 0.10)
        self.max_position_size = config.get("max_position_size", 0.35)  # Higher for momentum
    
    def compute_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        """Compute momentum signal using MACD and Volume"""
        
        # Use buffered candle data if provided, otherwise fetch from exchange
        if candle_data is not None and len(candle_data) > 0:
            ohlcv = candle_data
        else:
            history_limit = max(self.macd_slow_period * 3, 100)
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=history_limit)

        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        
        min_periods = self.macd_slow_period + self.macd_signal_period
        if len(df) < min_periods:
            raise ValueError(f"Not enough candles for {self.name} (need {min_periods}, got {len(df)})")

        # Calculate MACD
        df["ema_fast"] = df["close"].ewm(span=self.macd_fast_period, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.macd_slow_period, adjust=False).mean()
        df["macd_line"] = df["ema_fast"] - df["ema_slow"]
        df["signal_line"] = df["macd_line"].ewm(span=self.macd_signal_period, adjust=False).mean()
        df["histogram"] = df["macd_line"] - df["signal_line"]
        
        # Calculate histogram change (acceleration)
        df["histogram_change"] = df["histogram"].diff()
        df["histogram_accel"] = df["histogram_change"].diff()  # Acceleration of momentum
        
        # Calculate ATR for stop losses
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift())
        df['low_close'] = abs(df['low'] - df['close'].shift())
        df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['true_range'].rolling(window=self.atr_period).mean()
        
        # Calculate Volume MA
        if self.use_volume_filter:
            df["volume_ma"] = df["volume"].rolling(window=self.volume_ma_period).mean()
            df["volume_ratio"] = df["volume"] / df["volume_ma"]
        
        # Calculate Momentum
        if self.use_momentum_filter:
            df["momentum"] = (df["close"] - df["close"].shift(self.momentum_period)) / df["close"].shift(self.momentum_period)
        
        # Get current and previous values
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) > 2 else prev
        
        price = float(last.close)
        macd_line = float(last.macd_line) if pd.notna(last.macd_line) else 0.0
        signal_line = float(last.signal_line) if pd.notna(last.signal_line) else 0.0
        histogram = float(last.histogram) if pd.notna(last.histogram) else 0.0
        histogram_change = float(last.histogram_change) if pd.notna(last.histogram_change) else 0.0
        atr_value = float(last.atr) if pd.notna(last.atr) else price * 0.02
        
        prev_macd = float(prev.macd_line) if pd.notna(prev.macd_line) else 0.0
        prev_signal = float(prev.signal_line) if pd.notna(prev.signal_line) else 0.0
        prev_histogram = float(prev.histogram) if pd.notna(prev.histogram) else 0.0
        
        # Volume analysis
        volume_confirmed = True
        volume_ratio = 1.0
        if self.use_volume_filter and pd.notna(last.volume_ma) and last.volume_ma > 0:
            volume_ratio = float(last.volume / last.volume_ma)
            volume_confirmed = volume_ratio >= self.volume_multiplier
        
        # Momentum analysis
        momentum_confirmed = True
        momentum_value = 0.0
        if self.use_momentum_filter and pd.notna(last.momentum):
            momentum_value = float(last.momentum)
            momentum_confirmed = abs(momentum_value) >= self.min_momentum
        
        # Initialize
        direction = "neutral"
        confidence = 0.0
        
        # Detect MACD crossovers
        bullish_crossover = (prev_macd <= prev_signal) and (macd_line > signal_line)
        bearish_crossover = (prev_macd >= prev_signal) and (macd_line < signal_line)
        
        # Check for recent crossover (within signal_lookback bars)
        recent_bullish_cross = False
        recent_bearish_cross = False
        if len(df) > self.signal_lookback:
            for i in range(1, self.signal_lookback + 1):
                row = df.iloc[-i]
                row_prev = df.iloc[-i-1] if len(df) > i else row
                if pd.notna(row.macd_line) and pd.notna(row.signal_line):
                    if row_prev.macd_line <= row_prev.signal_line and row.macd_line > row.signal_line:
                        recent_bullish_cross = True
                    if row_prev.macd_line >= row_prev.signal_line and row.macd_line < row.signal_line:
                        recent_bearish_cross = True
        
        # Detect divergence (advanced signal)
        bullish_divergence = False
        bearish_divergence = False
        if self.detect_divergence and len(df) > self.divergence_lookback:
            lookback_df = df.tail(self.divergence_lookback)
            
            # Bullish divergence: price makes lower low, MACD makes higher low
            price_low_idx = lookback_df["close"].idxmin()
            macd_at_price_low = lookback_df.loc[price_low_idx, "macd_line"]
            
            if price <= lookback_df["close"].min() * 1.005 and macd_line > macd_at_price_low:
                bullish_divergence = True
            
            # Bearish divergence: price makes higher high, MACD makes lower high
            price_high_idx = lookback_df["close"].idxmax()
            macd_at_price_high = lookback_df.loc[price_high_idx, "macd_line"]
            
            if price >= lookback_df["close"].max() * 0.995 and macd_line < macd_at_price_high:
                bearish_divergence = True
        
        # ═══════════════════════════════════════════════════════════════
        # BULLISH SIGNAL CONDITIONS
        # ═══════════════════════════════════════════════════════════════
        # 1. MACD crossed above signal line (recently or now)
        # 2. Histogram is positive and growing
        # 3. Volume confirms (above average)
        # 4. (Optional) MACD above zero line
        # 5. (Optional) Bullish divergence boost
        
        macd_bullish = bullish_crossover or (recent_bullish_cross and histogram > 0)
        histogram_bullish = histogram > self.histogram_threshold and histogram_change > 0
        zero_line_bullish = macd_line > 0 if self.require_zero_cross else True
        
        if macd_bullish and histogram_bullish and zero_line_bullish:
            # Calculate base confidence from MACD strength
            macd_strength = min(1.0, abs(histogram) / (atr_value * 0.01)) if atr_value > 0 else 0.5
            
            # Histogram acceleration bonus
            accel_bonus = 0.1 if abs(histogram_change) > abs(prev_histogram) * 0.1 else 0.0
            
            confidence = macd_strength * 0.6 + accel_bonus
            
            # Volume confirmation
            if self.use_volume_filter:
                if volume_confirmed:
                    confidence += 0.2  # Strong volume = higher confidence
                    if volume_ratio > self.volume_multiplier * 1.5:
                        confidence += 0.1  # Very high volume bonus
                else:
                    confidence *= 0.7  # Reduce confidence without volume
            
            # Momentum confirmation
            if self.use_momentum_filter:
                if momentum_confirmed and momentum_value > 0:
                    confidence += 0.1
                elif not momentum_confirmed:
                    confidence *= 0.8
            
            # Zero line bonus (stronger signal)
            if macd_line > 0:
                confidence += 0.1
            
            # Divergence boost
            if bullish_divergence:
                confidence *= 1.3
            
            confidence = min(1.0, confidence)
            
            if confidence > 0.35:  # Minimum confidence threshold
                direction = "bullish"
        
        # ═══════════════════════════════════════════════════════════════
        # BEARISH SIGNAL CONDITIONS
        # ═══════════════════════════════════════════════════════════════
        # 1. MACD crossed below signal line (recently or now)
        # 2. Histogram is negative and falling
        # 3. Volume confirms (above average)
        # 4. (Optional) MACD below zero line
        # 5. (Optional) Bearish divergence boost
        
        macd_bearish = bearish_crossover or (recent_bearish_cross and histogram < 0)
        histogram_bearish = histogram < -self.histogram_threshold and histogram_change < 0
        zero_line_bearish = macd_line < 0 if self.require_zero_cross else True
        
        if direction == "neutral" and macd_bearish and histogram_bearish and zero_line_bearish:
            # Calculate base confidence
            macd_strength = min(1.0, abs(histogram) / (atr_value * 0.01)) if atr_value > 0 else 0.5
            
            # Histogram acceleration bonus
            accel_bonus = 0.1 if abs(histogram_change) > abs(prev_histogram) * 0.1 else 0.0
            
            confidence = macd_strength * 0.6 + accel_bonus
            
            # Volume confirmation
            if self.use_volume_filter:
                if volume_confirmed:
                    confidence += 0.2
                    if volume_ratio > self.volume_multiplier * 1.5:
                        confidence += 0.1
                else:
                    confidence *= 0.7
            
            # Momentum confirmation
            if self.use_momentum_filter:
                if momentum_confirmed and momentum_value < 0:
                    confidence += 0.1
                elif not momentum_confirmed:
                    confidence *= 0.8
            
            # Zero line bonus
            if macd_line < 0:
                confidence += 0.1
            
            # Divergence boost
            if bearish_divergence:
                confidence *= 1.3
            
            confidence = min(1.0, confidence)
            
            if confidence > 0.35:
                direction = "bearish"
        
        # ═══════════════════════════════════════════════════════════════
        # CALCULATE STOP LOSS AND TAKE PROFIT
        # ═══════════════════════════════════════════════════════════════
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
        
        # ═══════════════════════════════════════════════════════════════
        # DYNAMIC POSITION SIZING
        # ═══════════════════════════════════════════════════════════════
        position_size = 0.0
        if direction != "neutral" and self.use_dynamic_sizing:
            position_size = self._calculate_position_size(confidence, volume_ratio, atr_value, price)
        elif direction != "neutral":
            position_size = self.min_position_size
        
        # Build indicators dict
        indicators = {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram,
            "histogram_change": histogram_change,
            "ema_fast": float(last.ema_fast) if pd.notna(last.ema_fast) else 0.0,
            "ema_slow": float(last.ema_slow) if pd.notna(last.ema_slow) else 0.0,
            "atr": atr_value,
            "volume_ratio": volume_ratio,
            "momentum": momentum_value,
        }
        
        info = {
            "macd_fast_period": self.macd_fast_period,
            "macd_slow_period": self.macd_slow_period,
            "macd_signal_period": self.macd_signal_period,
            "last_timestamp": int(last.timestamp),
            "bullish_crossover": bullish_crossover,
            "bearish_crossover": bearish_crossover,
            "recent_bullish_cross": recent_bullish_cross,
            "recent_bearish_cross": recent_bearish_cross,
            "volume_confirmed": volume_confirmed,
            "momentum_confirmed": momentum_confirmed,
            "bullish_divergence": bullish_divergence,
            "bearish_divergence": bearish_divergence,
            "macd_above_zero": macd_line > 0,
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
        volume_ratio: float, 
        atr_value: float, 
        price: float
    ) -> float:
        """
        Calculate position size based on confidence, volume, and volatility.
        
        Higher confidence + volume -> Larger position
        Higher volatility (ATR) -> Smaller position
        """
        base_size = 0.20  # 20% base for momentum (higher than mean-reversion)
        
        # Confidence factor (0.35 to 1.0 confidence maps to 0.7x to 1.3x)
        confidence_factor = 0.7 + (confidence * 0.6)
        
        # Volume factor (higher volume = more conviction)
        volume_factor = min(1.3, 0.8 + (volume_ratio * 0.25)) if volume_ratio > 0 else 1.0
        
        # Volatility factor (higher ATR = smaller position for risk management)
        atr_pct = atr_value / price if price > 0 else 0.02
        volatility_factor = max(0.6, min(1.2, 0.02 / atr_pct)) if atr_pct > 0 else 1.0
        
        adjusted_size = base_size * confidence_factor * volume_factor * volatility_factor
        return max(self.min_position_size, min(self.max_position_size, adjusted_size))
    
    def get_description(self) -> str:
        return f"MACD ({self.macd_fast_period}/{self.macd_slow_period}/{self.macd_signal_period}) + Volume Momentum"
    
    def get_parameters(self) -> Dict[str, object]:
        return {
            "macd_fast_period": self.macd_fast_period,
            "macd_slow_period": self.macd_slow_period,
            "macd_signal_period": self.macd_signal_period,
            "histogram_threshold": self.histogram_threshold,
            "require_zero_cross": self.require_zero_cross,
            "signal_lookback": self.signal_lookback,
            "use_volume_filter": self.use_volume_filter,
            "volume_ma_period": self.volume_ma_period,
            "volume_multiplier": self.volume_multiplier,
            "use_momentum_filter": self.use_momentum_filter,
            "momentum_period": self.momentum_period,
            "min_momentum": self.min_momentum,
            "detect_divergence": self.detect_divergence,
            "divergence_lookback": self.divergence_lookback,
            "atr_period": self.atr_period,
            "atr_stop_multiplier": self.atr_stop_multiplier,
            "use_atr_stops": self.use_atr_stops,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "use_dynamic_sizing": self.use_dynamic_sizing,
            "min_position_size": self.min_position_size,
            "max_position_size": self.max_position_size,
        }
