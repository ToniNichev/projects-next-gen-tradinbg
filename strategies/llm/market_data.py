"""
Market Data Module

Handles fetching and preprocessing market data from exchanges.
"""

import logging
import numpy as np
from datetime import datetime
from typing import Dict, Optional, Tuple

from .indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """Fetch and process market data for LLM analysis"""
    
    @staticmethod
    def fetch_market_data(
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None
    ) -> Dict:
        """
        Fetch recent market data and calculate technical indicators.
        
        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Candle timeframe (e.g., "5m", "1h")
            candle_data: Optional pre-fetched candle data (for backtesting)
        
        Returns:
            Dict with:
            - Recent candles (OHLCV)
            - RSI
            - MACD
            - Volume analysis
            - Support/resistance levels
            - Price trend
        """
        # Fetch candles if not provided
        if candle_data is None:
            logger.info(f"Fetching market data from exchange...")
            # Fetch enough candles for indicator calculation (100 candles)
            candles = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        elif len(candle_data) < 50:
            # During backtesting the sliding window may be smaller than 50 at the very start.
            # Never fall back to a live exchange fetch here — that would pollute historical
            # simulation with current market data.  Raise a clear error instead.
            raise ValueError(
                f"Not enough candles in backtest window for analysis "
                f"(need 50+, got {len(candle_data)}). "
                f"The backtest should skip LLM analysis until at least 50 candles are available."
            )
        else:
            candles = candle_data[-100:]  # Use last 100 candles
        
        # Need at least 50 candles for all indicators
        if len(candles) < 50:
            raise ValueError(
                f"Not enough candles for analysis (need 50+, got {len(candles)}). "
                f"For backtesting, use '--days 3' or more for 1h timeframe."
            )
        
        # Extract OHLCV data
        closes = np.array([c[4] for c in candles])
        highs = np.array([c[2] for c in candles])
        lows = np.array([c[3] for c in candles])
        volumes = np.array([c[5] for c in candles])
        
        current_price = closes[-1]
        
        # Calculate technical indicators using the indicators module
        rsi = TechnicalIndicators.calculate_rsi(closes, period=14)
        macd_line, signal_line, macd_histogram = TechnicalIndicators.calculate_macd(closes)
        
        # Volume analysis
        volume_ratio = TechnicalIndicators.calculate_volume_ratio(volumes, period=50)
        avg_volume = np.mean(volumes[-50:]) if len(volumes) >= 50 else np.mean(volumes)
        current_volume = volumes[-1]
        
        # Support/resistance levels
        support_levels = TechnicalIndicators.find_support_levels(lows[-50:], current_price)
        resistance_levels = TechnicalIndicators.find_resistance_levels(highs[-50:], current_price)
        
        # Trend calculation
        trend = TechnicalIndicators.determine_trend(closes, short_period=20, long_period=50)
        sma_20 = TechnicalIndicators.calculate_sma(closes, 20)
        sma_50 = TechnicalIndicators.calculate_sma(closes, 50)
        
        # Recent price action (last 7 candles)
        recent_candles = MarketDataFetcher._format_recent_candles(candles)
        
        # Price change statistics
        price_change_24h, price_change_7d = MarketDataFetcher._calculate_price_changes(
            closes, timeframe
        )
        
        return {
            "symbol": symbol,
            "current_price": current_price,
            "timeframe": timeframe,
            "rsi": rsi,
            "macd_line": macd_line,
            "macd_signal": signal_line,
            "macd_histogram": macd_histogram,
            "volume_ratio": volume_ratio,
            "avg_volume": avg_volume,
            "current_volume": current_volume,
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "trend": trend,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "price_change_24h": price_change_24h,
            "price_change_7d": price_change_7d,
            "recent_candles": recent_candles,
        }
    
    @staticmethod
    def _format_recent_candles(candles: list, num_candles: int = 7) -> list:
        """
        Format recent candles for display
        
        Args:
            candles: List of OHLCV candles
            num_candles: Number of recent candles to include
            
        Returns:
            List of formatted candle dicts
        """
        recent_candles = []
        for i in range(max(-num_candles, -len(candles)), 0):
            c = candles[i]
            recent_candles.append({
                "timestamp": datetime.fromtimestamp(c[0] / 1000).isoformat(),
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
                "change_pct": ((c[4] - c[1]) / c[1] * 100) if c[1] > 0 else 0
            })
        return recent_candles
    
    @staticmethod
    def _calculate_price_changes(closes: np.ndarray, timeframe: str) -> Tuple[float, float]:
        """
        Calculate price changes over 24h and 7d periods
        
        Args:
            closes: Array of closing prices
            timeframe: Candle timeframe (e.g., "5m", "1h")
            
        Returns:
            Tuple of (24h change %, 7d change %)
        """
        # Convert timeframe to hours for accurate calculations
        timeframe_hours_map = {
            '5m': 1/12, '15m': 1/4, '30m': 0.5,
            '1h': 1, '2h': 2, '4h': 4, '6h': 6,
            '12h': 12, '1d': 24
        }
        hours_per_candle = timeframe_hours_map.get(timeframe, 1)
        
        # Calculate candles needed for 24h and 7d
        candles_24h = max(1, int(24 / hours_per_candle))
        candles_7d = max(1, int(168 / hours_per_candle))  # 168 hours = 7 days
        
        # Calculate price changes
        if len(closes) >= 2:
            price_24h_ago = closes[-min(candles_24h, len(closes))]
            price_7d_ago = closes[-min(candles_7d, len(closes))]
            current_price = closes[-1]
            
            price_change_24h = (current_price - price_24h_ago) / price_24h_ago * 100
            price_change_7d = (current_price - price_7d_ago) / price_7d_ago * 100
        else:
            price_change_24h = 0.0
            price_change_7d = 0.0
        
        return float(price_change_24h), float(price_change_7d)
    
    @staticmethod
    def get_current_price(exchange, symbol: str) -> float:
        """
        Get current market price
        
        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair
            
        Returns:
            Current price, or 0.0 if failed
        """
        try:
            ticker = exchange.fetch_ticker(symbol)
            return float(ticker["last"])
        except Exception as e:
            logger.warning(f"Failed to fetch current price: {e}")
            return 0.0
