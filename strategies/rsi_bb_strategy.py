"""
RSI + Bollinger Bands Mean Reversion Strategy

This strategy complements the EMA Crossover by trading:
- Oversold bounces (RSI < 30 + BB lower band touch)
- Overbought reversals (RSI > 70 + BB upper band touch)
- Mean reversion opportunities (price deviates significantly from BB middle)

Works well in ranging markets where EMA crossover underperforms.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

import pandas as pd
import numpy as np

from .base_strategy import BaseStrategy, StrategySignal


class RSIBollingerBandsStrategy(BaseStrategy):
    """Mean reversion strategy using RSI and Bollinger Bands"""
    
    def __init__(self, config: dict):
        super().__init__("RSI_BB_MeanReversion", config)
        
        # RSI parameters
        self.rsi_period = config.get("rsi_period", 14)
        self.rsi_oversold = config.get("rsi_oversold", 30)
        self.rsi_overbought = config.get("rsi_overbought", 70)
        self.rsi_extreme_oversold = config.get("rsi_extreme_oversold", 20)
        self.rsi_extreme_overbought = config.get("rsi_extreme_overbought", 80)
        
        # Bollinger Bands parameters
        self.bb_period = config.get("bb_period", 20)
        self.bb_std_dev = config.get("bb_std_dev", 2.0)
        
        # Mean reversion settings
        self.bb_touch_threshold = config.get("bb_touch_threshold", 0.995)  # 99.5% of band width
        self.require_both_signals = config.get("require_both_signals", True)  # RSI + BB must align
        
        # Risk management
        self.atr_period = config.get("atr_period", 14)
        self.atr_stop_multiplier = config.get("atr_stop_multiplier", 2.0)
        self.use_atr_stops = config.get("use_atr_stops", True)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.02)  # Tighter for mean reversion
        self.take_profit_pct = config.get("take_profit_pct", 0.03)  # Smaller target for mean reversion
        
        # Position sizing
        self.use_dynamic_sizing = config.get("use_dynamic_sizing", True)
        self.min_position_size = config.get("min_position_size", 0.10)
        self.max_position_size = config.get("max_position_size", 0.30)
        
        # Additional filters
        self.use_volume_filter = config.get("use_volume_filter", True)
        self.volume_threshold = config.get("volume_threshold", 1.0)  # Lower threshold for mean reversion
    
    def compute_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        """Compute mean reversion signal using RSI and Bollinger Bands"""
        
        # Use buffered candle data if provided, otherwise fetch from exchange
        if candle_data is not None and len(candle_data) > 0:
            ohlcv = candle_data
        else:
            history_limit = max(self.bb_period * 2, 100)
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=history_limit)

        df = pd.DataFrame(
            ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        
        if len(df) < self.bb_period:
            raise ValueError(f"Not enough candles for {self.name} (need {self.bb_period}, got {len(df)})")

        # Calculate RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # Calculate Bollinger Bands
        df["bb_middle"] = df["close"].rolling(window=self.bb_period).mean()
        df["bb_std"] = df["close"].rolling(window=self.bb_period).std()
        df["bb_upper"] = df["bb_middle"] + (df["bb_std"] * self.bb_std_dev)
        df["bb_lower"] = df["bb_middle"] - (df["bb_std"] * self.bb_std_dev)
        
        # Calculate %B (position within bands)
        df["bb_percent"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
        
        # Calculate band width (volatility indicator)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        
        # Calculate ATR for stop losses
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = abs(df['high'] - df['close'].shift())
        df['low_close'] = abs(df['low'] - df['close'].shift())
        df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['true_range'].rolling(window=self.atr_period).mean()
        
        # Calculate volume
        if self.use_volume_filter:
            df["volume_ma"] = df["volume"].rolling(window=20).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Get values
        price = float(last.close)
        rsi_value = float(last.rsi) if pd.notna(last.rsi) else 50.0
        bb_percent = float(last.bb_percent) if pd.notna(last.bb_percent) else 0.5
        bb_width = float(last.bb_width) if pd.notna(last.bb_width) else 0.0
        atr_value = float(last.atr) if pd.notna(last.atr) else price * 0.02
        bb_upper = float(last.bb_upper) if pd.notna(last.bb_upper) else price
        bb_lower = float(last.bb_lower) if pd.notna(last.bb_lower) else price
        bb_middle = float(last.bb_middle) if pd.notna(last.bb_middle) else price
        
        # Volume check
        volume_confirmed = True
        volume_ratio = 1.0
        if self.use_volume_filter and pd.notna(last.volume_ma) and last.volume_ma > 0:
            volume_ratio = float(last.volume / last.volume_ma)
            volume_confirmed = volume_ratio >= self.volume_threshold
        
        # Initialize
        direction = "neutral"
        confidence = 0.0
        
        # Check for BULLISH mean reversion signal (oversold bounce)
        # Conditions:
        # 1. RSI is oversold (< 30) or extremely oversold (< 20)
        # 2. Price touched or breached lower BB
        # 3. Volume is above average (for confirmation)
        
        rsi_bullish = rsi_value < self.rsi_oversold
        bb_lower_touch = bb_percent < (1 - self.bb_touch_threshold)  # Near or below lower band
        
        if rsi_bullish and (bb_lower_touch or not self.require_both_signals):
            # Calculate confidence based on extremity
            rsi_strength = max(0, (self.rsi_oversold - rsi_value) / self.rsi_oversold)  # 0 to 1
            bb_strength = max(0, min(1, (0.1 - bb_percent) * 10))  # How far below lower band
            
            # Extreme signals get higher confidence
            if rsi_value < self.rsi_extreme_oversold:
                rsi_strength *= 1.5
            
            confidence = (rsi_strength + bb_strength) / 2
            
            # Apply filters
            if self.require_both_signals and not bb_lower_touch:
                confidence *= 0.5
            if self.use_volume_filter and not volume_confirmed:
                confidence *= 0.7
            else:
                confidence *= 1.2  # Boost for volume confirmation
            
            # Check for RSI divergence (price makes lower low but RSI doesn't)
            if len(df) > 5:
                recent_lows_price = df["close"].tail(10).min()
                recent_lows_rsi = df["rsi"].tail(10).min()
                if price <= recent_lows_price * 1.01 and rsi_value > recent_lows_rsi * 1.05:
                    confidence *= 1.3  # Bullish divergence boost
            
            confidence = min(1.0, confidence)
            
            if confidence > 0.3:  # Minimum confidence threshold
                direction = "bullish"
        
        # Check for BEARISH mean reversion signal (overbought reversal)
        # Conditions:
        # 1. RSI is overbought (> 70) or extremely overbought (> 80)
        # 2. Price touched or breached upper BB
        # 3. Volume is above average (for confirmation)
        
        rsi_bearish = rsi_value > self.rsi_overbought
        bb_upper_touch = bb_percent > self.bb_touch_threshold  # Near or above upper band
        
        if rsi_bearish and (bb_upper_touch or not self.require_both_signals):
            # Calculate confidence
            rsi_strength = max(0, (rsi_value - self.rsi_overbought) / (100 - self.rsi_overbought))
            bb_strength = max(0, min(1, (bb_percent - 0.9) * 10))  # How far above upper band
            
            # Extreme signals get higher confidence
            if rsi_value > self.rsi_extreme_overbought:
                rsi_strength *= 1.5
            
            confidence = (rsi_strength + bb_strength) / 2
            
            # Apply filters
            if self.require_both_signals and not bb_upper_touch:
                confidence *= 0.5
            if self.use_volume_filter and not volume_confirmed:
                confidence *= 0.7
            else:
                confidence *= 1.2
            
            # Check for bearish divergence (price makes higher high but RSI doesn't)
            if len(df) > 5:
                recent_highs_price = df["close"].tail(10).max()
                recent_highs_rsi = df["rsi"].tail(10).max()
                if price >= recent_highs_price * 0.99 and rsi_value < recent_highs_rsi * 0.95:
                    confidence *= 1.3  # Bearish divergence boost
            
            confidence = min(1.0, confidence)
            
            if confidence > 0.3:  # Minimum confidence threshold
                direction = "bearish"
        
        # Calculate stop loss and take profit
        stop_loss = 0.0
        take_profit = 0.0
        
        if direction == "bullish":
            if self.use_atr_stops:
                stop_loss = price - (atr_value * self.atr_stop_multiplier)
            else:
                stop_loss = price * (1 - self.stop_loss_pct)
            # Target is BB middle or take profit, whichever is closer
            target_bb_middle = bb_middle
            target_pct = price * (1 + self.take_profit_pct)
            take_profit = min(target_bb_middle, target_pct)
            
        elif direction == "bearish":
            if self.use_atr_stops:
                stop_loss = price + (atr_value * self.atr_stop_multiplier)
            else:
                stop_loss = price * (1 + self.stop_loss_pct)
            # Target is BB middle or take profit, whichever is closer
            target_bb_middle = bb_middle
            target_pct = price * (1 - self.take_profit_pct)
            take_profit = max(target_bb_middle, target_pct)
        
        # Calculate position size
        position_size = 0.0
        if direction != "neutral" and self.use_dynamic_sizing:
            position_size = self._calculate_position_size(confidence, bb_width)
        elif direction != "neutral":
            position_size = self.min_position_size
        
        # Build indicators dict
        indicators = {
            "rsi": rsi_value,
            "bb_upper": bb_upper,
            "bb_middle": bb_middle,
            "bb_lower": bb_lower,
            "bb_percent": bb_percent,
            "bb_width": bb_width,
            "atr": atr_value,
            "volume_ratio": volume_ratio,
        }
        
        info = {
            "rsi_period": self.rsi_period,
            "bb_period": self.bb_period,
            "bb_std_dev": self.bb_std_dev,
            "last_timestamp": int(last.timestamp),
            "rsi_bullish": rsi_bullish,
            "rsi_bearish": rsi_bearish,
            "bb_lower_touch": bb_lower_touch,
            "bb_upper_touch": bb_upper_touch,
            "volume_confirmed": volume_confirmed,
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
    
    def _calculate_position_size(self, confidence: float, bb_width: float) -> float:
        """
        Calculate position size based on confidence and market volatility.
        
        Higher confidence -> Larger position
        Higher BB width (volatility) -> Smaller position
        """
        base_size = 0.15  # 15% base for mean reversion
        
        # Confidence factor (0.3 to 1.0 confidence maps to 0.5x to 1.5x)
        confidence_factor = 0.5 + (confidence * 1.0)
        
        # Volatility factor (wider bands = more volatility = smaller position)
        # Typical BB width is 0.04 to 0.12
        volatility_factor = max(0.5, min(1.5, 0.08 / bb_width)) if bb_width > 0 else 1.0
        
        adjusted_size = base_size * confidence_factor * volatility_factor
        return max(self.min_position_size, min(self.max_position_size, adjusted_size))
    
    def get_description(self) -> str:
        return f"RSI ({self.rsi_period}) + Bollinger Bands ({self.bb_period}, {self.bb_std_dev}σ) Mean Reversion"
    
    def get_parameters(self) -> Dict[str, object]:
        return {
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "rsi_extreme_oversold": self.rsi_extreme_oversold,
            "rsi_extreme_overbought": self.rsi_extreme_overbought,
            "bb_period": self.bb_period,
            "bb_std_dev": self.bb_std_dev,
            "bb_touch_threshold": self.bb_touch_threshold,
            "require_both_signals": self.require_both_signals,
            "atr_period": self.atr_period,
            "atr_stop_multiplier": self.atr_stop_multiplier,
            "use_atr_stops": self.use_atr_stops,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "use_dynamic_sizing": self.use_dynamic_sizing,
            "min_position_size": self.min_position_size,
            "max_position_size": self.max_position_size,
            "use_volume_filter": self.use_volume_filter,
            "volume_threshold": self.volume_threshold,
        }
