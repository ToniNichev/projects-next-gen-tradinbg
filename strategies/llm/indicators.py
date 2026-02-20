"""
Technical Indicators Module

Calculates technical indicators for market analysis using pandas_ta library.
Falls back to custom implementations if pandas_ta is not available.
"""

import logging
import numpy as np
from typing import Tuple, List

logger = logging.getLogger(__name__)

# Try to import pandas_ta for optimized indicator calculations
try:
    import pandas as pd
    import pandas_ta as ta
    HAS_PANDAS_TA = True
    logger.info("Technical indicators: Using pandas_ta library (optimized)")
except ImportError:
    HAS_PANDAS_TA = False
    logger.warning("pandas_ta not installed. Using custom indicator implementations. Install with: pip install pandas_ta")


class TechnicalIndicators:
    """Calculate technical indicators from price data"""
    
    @staticmethod
    def calculate_rsi(closes: np.ndarray, period: int = 14) -> float:
        """
        Calculate RSI (Relative Strength Index)
        
        Args:
            closes: Array of closing prices
            period: RSI period (default: 14)
            
        Returns:
            RSI value (0-100)
        """
        if HAS_PANDAS_TA:
            # Use pandas_ta for optimized calculation
            df = pd.DataFrame({'close': closes})
            rsi_series = ta.rsi(df['close'], length=period)
            return float(rsi_series.iloc[-1])
        
        # Fallback: Custom implementation
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:]) if len(gains) >= period else np.mean(gains)
        avg_loss = np.mean(losses[-period:]) if len(losses) >= period else np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)
    
    @staticmethod
    def calculate_macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float, float]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            closes: Array of closing prices
            fast: Fast EMA period (default: 12)
            slow: Slow EMA period (default: 26)
            signal: Signal line period (default: 9)
            
        Returns:
            Tuple of (macd_line, signal_line, histogram)
        """
        if HAS_PANDAS_TA:
            # Use pandas_ta for optimized calculation
            df = pd.DataFrame({'close': closes})
            macd_df = ta.macd(df['close'], fast=fast, slow=slow, signal=signal)
            
            if macd_df is None or len(macd_df) == 0:
                return 0.0, 0.0, 0.0
            
            macd_line = float(macd_df[f'MACD_{fast}_{slow}_{signal}'].iloc[-1])
            signal_line = float(macd_df[f'MACDs_{fast}_{slow}_{signal}'].iloc[-1])
            histogram = float(macd_df[f'MACDh_{fast}_{slow}_{signal}'].iloc[-1])
            
            return macd_line, signal_line, histogram
        
        # Fallback: Custom implementation
        if len(closes) < slow + signal:
            return 0.0, 0.0, 0.0
        
        # Calculate MACD line for all periods (need historical values for signal line EMA)
        macd_values = []
        for i in range(slow, len(closes) + 1):
            ema_f = TechnicalIndicators._calculate_ema(closes[:i], fast)
            ema_s = TechnicalIndicators._calculate_ema(closes[:i], slow)
            macd_values.append(ema_f - ema_s)
        
        macd_array = np.array(macd_values)
        macd_line = macd_array[-1]
        signal_line = TechnicalIndicators._calculate_ema(macd_array, signal)
        histogram = macd_line - signal_line
        
        return float(macd_line), float(signal_line), float(histogram)
    
    @staticmethod
    def _calculate_ema(data: np.ndarray, period: int) -> float:
        """Calculate EMA (Exponential Moving Average) - helper method"""
        if len(data) == 0:
            return 0.0
        if len(data) == 1:
            return float(data[0])
        
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
        return float(ema)
    
    @staticmethod
    def calculate_sma(closes: np.ndarray, period: int) -> float:
        """
        Calculate SMA (Simple Moving Average)
        
        Args:
            closes: Array of closing prices
            period: SMA period
            
        Returns:
            SMA value
        """
        if len(closes) < period:
            return float(np.mean(closes))
        return float(np.mean(closes[-period:]))
    
    @staticmethod
    def calculate_volume_ratio(volumes: np.ndarray, period: int = 50) -> float:
        """
        Calculate current volume ratio vs average
        
        Args:
            volumes: Array of volume data
            period: Period for average calculation (default: 50)
            
        Returns:
            Volume ratio (current / average)
        """
        if len(volumes) == 0:
            return 1.0
        
        avg_volume = np.mean(volumes[-period:]) if len(volumes) >= period else np.mean(volumes)
        current_volume = volumes[-1]
        
        return float(current_volume / avg_volume if avg_volume > 0 else 1.0)
    
    @staticmethod
    def find_support_levels(lows: np.ndarray, current_price: float, num_levels: int = 3) -> List[float]:
        """
        Find support levels from recent swing lows
        
        Args:
            lows: Array of low prices
            current_price: Current market price
            num_levels: Number of support levels to return
            
        Returns:
            List of support levels
        """
        # Find local minima
        support_candidates = []
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                support_candidates.append(float(lows[i]))
        
        # Filter to levels below current price and cluster nearby levels
        supports = [s for s in support_candidates if s < current_price * 0.98]
        supports = sorted(set([TechnicalIndicators._round_price_level(s) for s in supports]))
        
        return supports[-num_levels:] if len(supports) > num_levels else supports
    
    @staticmethod
    def find_resistance_levels(highs: np.ndarray, current_price: float, num_levels: int = 3) -> List[float]:
        """
        Find resistance levels from recent swing highs
        
        Args:
            highs: Array of high prices
            current_price: Current market price
            num_levels: Number of resistance levels to return
            
        Returns:
            List of resistance levels
        """
        # Find local maxima
        resistance_candidates = []
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                resistance_candidates.append(float(highs[i]))
        
        # Filter to levels above current price and cluster nearby levels
        resistances = [r for r in resistance_candidates if r > current_price * 1.02]
        resistances = sorted(set([TechnicalIndicators._round_price_level(r) for r in resistances]))
        
        return resistances[:num_levels] if len(resistances) > num_levels else resistances
    
    @staticmethod
    def _round_price_level(price: float) -> float:
        """Round price to appropriate precision based on magnitude"""
        if price >= 10000:
            return round(price, -2)  # Nearest 100 (e.g., BTC)
        elif price >= 1000:
            return round(price, -1)  # Nearest 10 (e.g., ETH)
        elif price >= 100:
            return round(price, 0)   # Nearest 1
        elif price >= 1:
            return round(price, 1)   # 1 decimal
        else:
            return round(price, 4)   # 4 decimals for small prices
    
    @staticmethod
    def determine_trend(closes: np.ndarray, short_period: int = 20, long_period: int = 50) -> str:
        """
        Determine price trend based on moving averages
        
        Args:
            closes: Array of closing prices
            short_period: Short-term MA period (default: 20)
            long_period: Long-term MA period (default: 50)
            
        Returns:
            Trend: "bullish", "bearish", or "neutral"
        """
        sma_short = TechnicalIndicators.calculate_sma(closes, short_period)
        sma_long = TechnicalIndicators.calculate_sma(closes, long_period)
        
        if sma_short > sma_long:
            return "bullish"
        elif sma_short < sma_long:
            return "bearish"
        else:
            return "neutral"
