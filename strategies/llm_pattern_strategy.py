"""
LLM Market Analysis Strategy - Uses local LLM to analyze market data and patterns.

This strategy uses Ollama (local LLM) to analyze recent market price action,
technical indicators, and chart patterns. The LLM generates trading signals
based on technical analysis and market conditions.

Key Features:
- Analyzes recent price candles and market data
- Calculates technical indicators (RSI, MACD, volume, support/resistance)
- Detects chart patterns and trends
- Optionally includes trade history for context (if available)
- Provides confidence scores and reasoning
- Caches analysis results to avoid repeated expensive LLM calls
"""

import json
import logging
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from .base_strategy import BaseStrategy, StrategySignal
from .constants import StrategyNames

logger = logging.getLogger(__name__)


class LLMPatternStrategy(BaseStrategy):
    """LLM-powered pattern analysis strategy using Ollama"""
    
    def __init__(self, config: dict, db_manager=None, progress_callback=None):
        super().__init__(StrategyNames.LLM_PATTERN, config)
        
        # LLM configuration
        self.ollama_url = config.get("llm_ollama_url", "http://localhost:11434")
        self.model = config.get("llm_ollama_model", "mistral")
        self.lookback_days = config.get("llm_lookback_days", 7)
        self.cache_minutes = config.get("llm_cache_minutes", 15)
        self.timeout_seconds = config.get("llm_timeout_seconds", 60)
        self.temperature = config.get("llm_temperature", 0.3)
        self.num_predict = config.get("llm_num_predict", 1000)
        self.require_patterns = config.get("llm_require_patterns", False)
        
        # Validate temperature (0.0 - 1.0)
        if not 0.0 <= self.temperature <= 1.0:
            logger.warning(f"{self.name}: Invalid temperature {self.temperature}, using default 0.3")
            self.temperature = 0.3
        
        # Validate num_predict (minimum 300, maximum 2000)
        if self.num_predict < 300:
            logger.warning(f"{self.name}: num_predict {self.num_predict} too low, using 500")
            self.num_predict = 500
        elif self.num_predict > 2000:
            logger.warning(f"{self.name}: num_predict {self.num_predict} too high, using 2000")
            self.num_predict = 2000
        
        # Warn if temperature is high (might cause inconsistent results)
        if self.temperature > 0.5:
            logger.warning(f"{self.name}: High temperature ({self.temperature}) may cause inconsistent analysis")
        
        # Backtest sampling - only analyze every Nth candle to speed up backtests
        # Default: 12 candles (= 1 hour on 5m timeframe, 5 hours on 1h timeframe)
        self.backtest_sample_interval = config.get("llm_backtest_sample_interval", 12)
        
        # Backtest state tracking
        self._backtest_candle_count = 0
        self._last_backtest_analysis = None
        
        # Backtest progress tracking
        self._backtest_total_candles = 0
        self._backtest_total_analyses = 0
        self._backtest_current_analysis = 0
        self._backtest_analysis_times = []  # Track timing for averaging
        self._backtest_started = False
        self._progress_callback = progress_callback  # Optional callback for UI progress updates
        
        # Database manager for trade history and caching
        self.db_manager = db_manager
        
        # Import ollama library
        try:
            import ollama
            self.ollama = ollama
            self.ollama_client = ollama.Client(host=self.ollama_url)
        except ImportError:
            logger.error("ollama package not installed. Install with: pip install ollama")
            raise ImportError("ollama package required for LLM strategy")
        
        # Risk management (fallback to config defaults if LLM doesn't suggest)
        self.stop_loss_pct = config.get("stop_loss_pct", 0.025)
        self.take_profit_pct = config.get("take_profit_pct", 0.04)
        self.min_position_size = config.get("min_position_size", 0.15)
        self.max_position_size = config.get("max_position_size", 0.35)
    
    def compute_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        """
        Compute LLM-based signal by analyzing market data and technical indicators.
        
        This method:
        1. Checks for cached analysis (within cache_minutes)
        2. If no valid cache, fetches recent market data (candles)
        3. Calculates technical indicators (RSI, MACD, support/resistance, etc.)
        4. Optionally includes trade history for context
        5. Sends market data to LLM for analysis
        6. Generates signal based on LLM's recommendation
        7. Caches the result for future use
        
        IMPORTANT: When candle_data is provided (backtesting), uses the last candle's
        close price instead of fetching live price. This ensures backtest accuracy.
        """
        
        # Get current price - use candle data if provided (for backtesting accuracy)
        # Otherwise fetch live price from exchange
        if candle_data and len(candle_data) > 0:
            current_price = float(candle_data[-1][4])  # Close price of last candle
            is_backtest_mode = True
        else:
            current_price = self._get_current_price(exchange, symbol)
            is_backtest_mode = False
        
        # BACKTEST SAMPLING: Only analyze every Nth candle to speed up backtests
        if is_backtest_mode:
            # Initialize backtest tracking on first candle
            if not self._backtest_started:
                self._backtest_started = True
                self._backtest_total_candles = len(candle_data) if candle_data else 0
                self._backtest_total_analyses = max(1, self._backtest_total_candles // self.backtest_sample_interval)
                self._backtest_current_analysis = 0
                self._backtest_analysis_times = []
                
                logger.info(f"{self.name}: 📊 Starting backtest - {self._backtest_total_candles} candles, analyzing every {self.backtest_sample_interval} = {self._backtest_total_analyses} analyses")
                
                # Notify UI of total analyses
                if self._progress_callback:
                    self._progress_callback(
                        total_analyses=self._backtest_total_analyses,
                        total_candles=self._backtest_total_candles,
                        completed_analyses=0,
                        current_candle=0
                    )
            
            self._backtest_candle_count += 1
            should_analyze = (self._backtest_candle_count % self.backtest_sample_interval == 0)
            
            if not should_analyze and self._last_backtest_analysis:
                # Reuse last analysis for this candle
                logger.debug(f"{self.name}: Skipping candle {self._backtest_candle_count} (sampling every {self.backtest_sample_interval})")
                return self._signal_from_analysis(self._last_backtest_analysis, exchange, symbol, current_price)
            elif not should_analyze:
                # No previous analysis yet, return neutral
                logger.debug(f"{self.name}: No previous analysis yet, returning neutral")
                return self._neutral_signal(exchange, symbol, current_price)
            else:
                # Time to analyze this candle!
                self._backtest_current_analysis += 1
                progress_pct = (self._backtest_current_analysis / self._backtest_total_analyses * 100) if self._backtest_total_analyses > 0 else 0
                
                # Calculate ETA based on average analysis time
                eta_str = ""
                if len(self._backtest_analysis_times) > 0:
                    avg_time = sum(self._backtest_analysis_times) / len(self._backtest_analysis_times)
                    remaining_analyses = self._backtest_total_analyses - self._backtest_current_analysis
                    eta_seconds = remaining_analyses * avg_time
                    eta_minutes = eta_seconds / 60
                    eta_str = f" - Est. {eta_minutes:.0f} min remaining (avg: {avg_time:.1f}s/analysis)"
                
                logger.info(f"{self.name}: 🔍 Analysis {self._backtest_current_analysis}/{self._backtest_total_analyses} ({progress_pct:.0f}%) - Candle {self._backtest_candle_count}{eta_str}")
        
        # Check for cached analysis (skip in backtest mode to ensure fresh analysis per candle)
        if self.db_manager and not is_backtest_mode and self.cache_minutes > 0:
            cached = self._get_cached_analysis()
            if cached:
                logger.info(f"{self.name}: Using cached analysis (valid until {cached['cache_valid_until']})")
                return self._signal_from_analysis(cached, exchange, symbol, current_price)
        
        # Fetch and prepare market data
        try:
            market_data = self._fetch_market_data(exchange, symbol, timeframe, candle_data)
            
            # Optionally fetch trade history for additional context (skip in backtest mode)
            trade_context = None
            if self.db_manager and not is_backtest_mode:
                try:
                    end_date = datetime.utcnow()
                    start_date = end_date - timedelta(days=self.lookback_days)
                    trades = self.db_manager.get_trades(
                        limit=100,
                        start_date=start_date,
                        end_date=end_date
                    )
                    if len(trades) >= 3:
                        trade_context = self._prepare_trade_context(trades)
                        logger.info(f"{self.name}: Including {len(trades)} trades as context")
                except Exception as e:
                    logger.debug(f"{self.name}: Could not fetch trade history for context: {e}")
            
            # Perform LLM analysis with market data
            analysis = self._analyze_with_llm(market_data, trade_context, current_price, symbol)
            
            # Track analysis timing for backtest progress estimation
            if is_backtest_mode and analysis and "analysis_duration_ms" in analysis:
                analysis_time_seconds = analysis["analysis_duration_ms"] / 1000
                self._backtest_analysis_times.append(analysis_time_seconds)
                # Keep only last 10 analyses for moving average
                if len(self._backtest_analysis_times) > 10:
                    self._backtest_analysis_times.pop(0)
                
                # Calculate ETA
                avg_time = sum(self._backtest_analysis_times) / len(self._backtest_analysis_times)
                remaining_analyses = self._backtest_total_analyses - self._backtest_current_analysis
                eta_seconds = remaining_analyses * avg_time
                
                # Notify UI of progress update
                if self._progress_callback:
                    self._progress_callback(
                        completed_analyses=self._backtest_current_analysis,
                        current_candle=self._backtest_candle_count,
                        eta_seconds=int(eta_seconds),
                        avg_time_per_analysis=avg_time
                    )
                
                # Log completion if this was the last analysis
                if self._backtest_current_analysis >= self._backtest_total_analyses:
                    avg_time = sum(self._backtest_analysis_times) / len(self._backtest_analysis_times)
                    total_time = sum(self._backtest_analysis_times)
                    logger.info(f"{self.name}: ✅ All {self._backtest_total_analyses} analyses complete! Total LLM time: {total_time/60:.1f} min (avg: {avg_time:.1f}s/analysis)")
            
            # Save analysis for backtest sampling (reuse for next N-1 candles)
            if is_backtest_mode and analysis:
                self._last_backtest_analysis = analysis
            
            # Cache the analysis (only in live mode, not during backtesting)
            if analysis and self.db_manager and not is_backtest_mode and self.cache_minutes > 0:
                self._cache_analysis(analysis)
            
            return self._signal_from_analysis(analysis, exchange, symbol, current_price)
            
        except ConnectionError as e:
            logger.error(f"{self.name}: Cannot connect to Ollama - returning neutral signal")
            return self._neutral_signal(exchange, symbol, current_price)
        except TimeoutError as e:
            logger.error(f"{self.name}: Ollama request timed out - returning neutral signal")
            return self._neutral_signal(exchange, symbol, current_price)
        except Exception as e:
            logger.error(f"{self.name}: LLM analysis failed: {e}", exc_info=True)
            return self._neutral_signal(exchange, symbol, current_price)
    
    def _get_cached_analysis(self) -> Optional[Dict]:
        """Get valid cached LLM analysis from database"""
        if not self.db_manager:
            return None
        
        try:
            cached = self.db_manager.get_valid_cached_analysis()
            if not cached:
                return None
            
            # Convert to dict
            return {
                "direction": cached.direction,
                "confidence": cached.confidence,
                "reasoning": cached.reasoning,
                "patterns_found": json.loads(cached.patterns_found) if cached.patterns_found else [],
                "suggested_stop_loss": cached.suggested_stop_loss,
                "suggested_take_profit": cached.suggested_take_profit,
                "suggested_position_size": cached.suggested_position_size,
                "current_price": cached.current_price,
                "cache_valid_until": cached.cache_valid_until,
                "model_used": cached.model_used,
            }
        except Exception as e:
            logger.warning(f"{self.name}: Error fetching cached analysis: {e}")
            return None
    
    def _fetch_market_data(self, exchange, symbol: str, timeframe: str, candle_data: Optional[list]) -> Dict:
        """
        Fetch recent market data and calculate technical indicators.
        
        Returns dict with:
        - Recent candles (OHLCV)
        - RSI
        - MACD
        - Volume analysis
        - Support/resistance levels
        - Price trend
        """
        import numpy as np
        
        # Fetch candles if not provided
        if candle_data is None or len(candle_data) < 50:
            logger.info(f"{self.name}: Fetching market data from exchange...")
            # Fetch enough candles for indicator calculation (100 candles)
            candles = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        else:
            candles = candle_data[-100:]  # Use last 100 candles
        
        # Need at least 50 candles for all indicators (MACD needs 26+9=35, plus buffer for support/resistance)
        if len(candles) < 50:
            raise ValueError(f"Not enough candles for analysis (need 50+, got {len(candles)}). For backtesting, use '--days 3' or more for 1h timeframe.")
        
        # Extract OHLCV data
        closes = np.array([c[4] for c in candles])
        highs = np.array([c[2] for c in candles])
        lows = np.array([c[3] for c in candles])
        volumes = np.array([c[5] for c in candles])
        
        current_price = closes[-1]
        
        # Calculate RSI (14 period)
        rsi = self._calculate_rsi(closes, period=14)
        
        # Calculate MACD
        macd_line, signal_line, macd_histogram = self._calculate_macd(closes)
        
        # Calculate volume analysis (use longer period for more stable baseline)
        avg_volume = np.mean(volumes[-50:]) if len(volumes) >= 50 else np.mean(volumes)
        current_volume = volumes[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        # Identify support/resistance levels (swing highs/lows from last 50 candles)
        support_levels = self._find_support_levels(lows[-50:], current_price)
        resistance_levels = self._find_resistance_levels(highs[-50:], current_price)
        
        # Calculate price trend (SMA 20 vs SMA 50)
        sma_20 = np.mean(closes[-20:])
        sma_50 = np.mean(closes[-50:]) if len(closes) >= 50 else sma_20
        trend = "bullish" if sma_20 > sma_50 else "bearish" if sma_20 < sma_50 else "neutral"
        
        # Recent price action (last 7 candles)
        recent_candles = []
        for i in range(max(-7, -len(candles)), 0):
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
        
        # Price change statistics (account for different timeframes)
        # Convert timeframe to hours for accurate 24h/7d calculations
        timeframe_hours_map = {'5m': 1/12, '15m': 1/4, '30m': 0.5, '1h': 1, '2h': 2, '4h': 4, '6h': 6, '12h': 12, '1d': 24}
        hours_per_candle = timeframe_hours_map.get(timeframe, 1)
        
        # Calculate candles needed for 24h and 7d
        candles_24h = max(1, int(24 / hours_per_candle))
        candles_7d = max(1, int(168 / hours_per_candle))  # 168 hours = 7 days
        
        price_change_24h = ((current_price - closes[-min(candles_24h, len(closes))]) / closes[-min(candles_24h, len(closes))] * 100) if len(closes) >= 2 else 0
        price_change_7d = ((current_price - closes[-min(candles_7d, len(closes))]) / closes[-min(candles_7d, len(closes))] * 100) if len(closes) >= 2 else 0
        
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
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "trend": trend,
            "sma_20": sma_20,
            "sma_50": sma_50,
            "price_change_24h": price_change_24h,
            "price_change_7d": price_change_7d,
            "recent_candles": recent_candles,
        }
    
    def _calculate_rsi(self, closes: np.ndarray, period: int = 14) -> float:
        """Calculate RSI indicator"""
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
    
    def _calculate_macd(self, closes: np.ndarray, fast=12, slow=26, signal=9):
        """Calculate MACD indicator"""
        import numpy as np
        
        # Need enough data for MACD calculation
        if len(closes) < slow + signal:
            # Not enough data, return zeros
            return 0.0, 0.0, 0.0
        
        # Calculate MACD line for all periods (need historical values for signal line EMA)
        macd_values = []
        for i in range(slow, len(closes) + 1):
            ema_f = self._calculate_ema(closes[:i], fast)
            ema_s = self._calculate_ema(closes[:i], slow)
            macd_values.append(ema_f - ema_s)
        
        # Convert to numpy array
        macd_array = np.array(macd_values)
        
        # Current MACD line (most recent value)
        macd_line = macd_array[-1]
        
        # Signal line is EMA of MACD values
        signal_line = self._calculate_ema(macd_array, signal)
        
        # MACD histogram
        macd_histogram = macd_line - signal_line
        
        return float(macd_line), float(signal_line), float(macd_histogram)
    
    def _calculate_ema(self, data: np.ndarray, period: int) -> float:
        """Calculate EMA (Exponential Moving Average)"""
        if len(data) == 0:
            return 0.0
        if len(data) == 1:
            return float(data[0])
        
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
        return float(ema)
    
    def _find_support_levels(self, lows: np.ndarray, current_price: float, num_levels: int = 3) -> list:
        """Find support levels from recent swing lows"""
        # Find local minima
        support_candidates = []
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                support_candidates.append(float(lows[i]))
        
        # Filter to levels below current price and cluster nearby levels
        supports = [s for s in support_candidates if s < current_price * 0.98]
        supports = sorted(set([self._round_price_level(s) for s in supports]))  # Round and deduplicate
        
        return supports[-num_levels:] if len(supports) > num_levels else supports
    
    def _find_resistance_levels(self, highs: np.ndarray, current_price: float, num_levels: int = 3) -> list:
        """Find resistance levels from recent swing highs"""
        # Find local maxima
        resistance_candidates = []
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                resistance_candidates.append(float(highs[i]))
        
        # Filter to levels above current price and cluster nearby levels
        resistances = [r for r in resistance_candidates if r > current_price * 1.02]
        resistances = sorted(set([self._round_price_level(r) for r in resistances]))  # Round and deduplicate
        
        return resistances[:num_levels] if len(resistances) > num_levels else resistances
    
    def _round_price_level(self, price: float) -> float:
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
    
    def _prepare_trade_context(self, trades: list) -> Dict:
        """Prepare trade history as optional context for LLM"""
        winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl and t.pnl < 0]
        
        total_pnl = sum(t.pnl for t in trades if t.pnl) if trades else 0.0
        
        return {
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": (len(winning_trades) / len(trades) * 100) if trades else 0.0,
            "total_pnl": total_pnl,
        }
    
    def _analyze_with_llm(self, market_data: Dict, trade_context: Optional[Dict], current_price: float, symbol: str) -> Dict:
        """
        Send market data to LLM for technical analysis.
        
        Returns:
            Dict with analysis results including direction, confidence, reasoning, patterns, etc.
        """
        start_time = datetime.utcnow()
        
        # Create prompt for LLM with market data
        prompt = self._create_market_analysis_prompt(market_data, trade_context, symbol)
        
        logger.info(f"{self.name}: Sending market analysis request to Ollama ({self.model})...")
        
        try:
            # Call Ollama API with timeout
            response = self.ollama_client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
                options={
                    "temperature": self.temperature,  # Configurable (0.0-1.0, default 0.3)
                    "num_predict": self.num_predict,  # Configurable max tokens (default 1000)
                    "timeout": self.timeout_seconds,  # Request timeout
                }
            )
            
            analysis_duration = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Parse LLM response
            llm_output = response.get("response", "")
            logger.info(f"{self.name}: LLM response received in {analysis_duration}ms")
            logger.debug(f"{self.name}: LLM output: {llm_output[:500]}...")
            
            # Extract structured data from LLM response
            analysis = self._parse_llm_response(llm_output, current_price)
            analysis["analysis_duration_ms"] = analysis_duration
            analysis["model_used"] = self.model
            analysis["num_trades_analyzed"] = trade_context["total_trades"] if trade_context else 0
            analysis["analysis_period_days"] = self.lookback_days
            
            # Include market indicators for later use
            analysis["rsi"] = market_data["rsi"]
            analysis["macd_histogram"] = market_data["macd_histogram"]
            analysis["trend"] = market_data["trend"]
            
            # Include trade context stats if available
            if trade_context:
                analysis["recent_win_rate"] = trade_context["win_rate"] / 100
                analysis["recent_pnl"] = trade_context["total_pnl"]
            else:
                analysis["recent_win_rate"] = 0.0
                analysis["recent_pnl"] = 0.0
            
            return analysis
            
        except ConnectionError as e:
            logger.error(f"{self.name}: Cannot connect to Ollama at {self.ollama_url}. Is Ollama running?")
            raise ConnectionError(f"Ollama connection failed: {e}")
        except TimeoutError as e:
            logger.error(f"{self.name}: Ollama request timed out after {self.timeout_seconds}s")
            raise TimeoutError(f"Ollama timeout: {e}")
        except Exception as e:
            logger.error(f"{self.name}: Ollama API call failed: {e}")
            raise
    
    def _create_market_analysis_prompt(self, market_data: Dict, trade_context: Optional[Dict], symbol: str) -> str:
        """Create prompt for LLM market analysis"""
        
        # Format support/resistance levels
        support_str = ', '.join([f'${s:.0f}' for s in market_data['support_levels']]) if market_data['support_levels'] else "None identified"
        resistance_str = ', '.join([f'${r:.0f}' for r in market_data['resistance_levels']]) if market_data['resistance_levels'] else "None identified"
        
        # Format recent candles
        candle_summary = "\n".join([
            f"  {c['timestamp'][:10]}: Open ${c['open']:.2f}, High ${c['high']:.2f}, Low ${c['low']:.2f}, Close ${c['close']:.2f}, Change: {c['change_pct']:+.2f}%"
            for c in market_data['recent_candles'][-5:]  # Last 5 candles
        ])
        
        # Build prompt with market data
        prompt = f"""You are an expert cryptocurrency technical analyst. Analyze the current market data and provide a trading recommendation.

SYMBOL: {symbol}
CURRENT PRICE: ${market_data['current_price']:.2f}
TIMEFRAME: {market_data['timeframe']}

=== TECHNICAL INDICATORS ===
- RSI (14): {market_data['rsi']:.1f} {'(Oversold)' if market_data['rsi'] < 30 else '(Overbought)' if market_data['rsi'] > 70 else '(Neutral)'}
- MACD Line: {market_data['macd_line']:.2f}
- MACD Signal: {market_data['macd_signal']:.2f}
- MACD Histogram: {market_data['macd_histogram']:.2f} {'(Bullish crossover)' if market_data['macd_histogram'] > 0 else '(Bearish crossover)'}
- SMA 20: ${market_data['sma_20']:.2f}
- SMA 50: ${market_data['sma_50']:.2f}
- Trend: {market_data['trend'].upper()}

=== VOLUME ANALYSIS ===
- Current Volume Ratio: {market_data['volume_ratio']:.2f}x average {'(High volume)' if market_data['volume_ratio'] > 1.5 else '(Above average)' if market_data['volume_ratio'] > 1.0 else '(Below average)'}

=== SUPPORT & RESISTANCE ===
- Support Levels: {support_str}
- Resistance Levels: {resistance_str}

=== PRICE ACTION ===
- 24h Change: {market_data['price_change_24h']:+.2f}%
- 7d Change: {market_data['price_change_7d']:+.2f}%

RECENT CANDLES (Last 5):
{candle_summary}
"""
        
        # Optionally add trade context
        if trade_context and trade_context['total_trades'] > 0:
            prompt += f"""
=== YOUR BOT'S RECENT PERFORMANCE (Context) ===
- Recent Trades: {trade_context['total_trades']} ({trade_context['winning_trades']} wins, {trade_context['losing_trades']} losses)
- Win Rate: {trade_context['win_rate']:.1f}%
- Total P&L: ${trade_context['total_pnl']:.2f}
"""
        
        prompt += """
=== ANALYSIS TASK ===
Based on the technical indicators, price action, and market conditions above, provide a trading recommendation:

1. What chart patterns or signals do you see?
2. Is the momentum bullish, bearish, or neutral?
3. Are we near important support/resistance levels?
4. What is the probability of a price move in either direction?
5. Should we BUY, SELL, or HOLD (neutral)?

Provide your response in the following JSON format:
{
    "direction": "bullish|bearish|neutral",
    "confidence": 0.0-1.0,
    "reasoning": "Your detailed technical explanation here",
    "patterns_found": ["pattern1", "pattern2", "pattern3"],
    "stop_loss_pct": 0.025,
    "take_profit_pct": 0.04,
    "position_size": 0.15-0.40
}

IMPORTANT GUIDELINES:
- Set "direction" to "neutral" if signals are mixed or weak
- "confidence" should be 0.0-1.0 (0.7+ = strong signal, 0.5-0.7 = moderate, <0.5 = weak)
- List 2-5 specific technical patterns in "patterns_found" (e.g., "RSI oversold + MACD bullish crossover", "Price bouncing off support at $64000")
- Suggest stop_loss_pct and take_profit_pct based on ATR/volatility (typical: 2-3% stop, 3-5% profit)
- Suggest position_size (0.15-0.40) based on confidence and signal strength
- Be conservative - only suggest non-neutral if you see clear technical setup

Response:"""
        
        return prompt
    
    def _parse_llm_response(self, llm_output: str, current_price: float) -> Dict:
        """
        Parse LLM response to extract structured data.
        
        Handles both JSON and natural language responses.
        """
        # Try to find JSON in the response (support nested JSON)
        import re
        
        # Find all potential JSON blocks (including nested braces)
        json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
        json_matches = re.findall(json_pattern, llm_output, re.DOTALL)
        
        json_match = None
        for match in json_matches:
            if '"direction"' in match:
                json_match = match
                break
        
        if json_match:
            try:
                data = json.loads(json_match)
                
                # Validate and normalize
                direction = data.get("direction", "neutral").lower()
                if direction not in ["bullish", "bearish", "neutral"]:
                    direction = "neutral"
                
                confidence = float(data.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))
                
                reasoning = data.get("reasoning", "LLM analysis completed")
                patterns_found = data.get("patterns_found", [])
                
                stop_loss_pct = float(data.get("stop_loss_pct", self.stop_loss_pct))
                take_profit_pct = float(data.get("take_profit_pct", self.take_profit_pct))
                position_size = float(data.get("position_size", 0.25))
                position_size = max(self.min_position_size, min(self.max_position_size, position_size))
                
                # Calculate absolute stop/target prices
                if direction == "bullish":
                    stop_loss = current_price * (1 - stop_loss_pct)
                    take_profit = current_price * (1 + take_profit_pct)
                elif direction == "bearish":
                    stop_loss = current_price * (1 + stop_loss_pct)
                    take_profit = current_price * (1 - take_profit_pct)
                else:
                    stop_loss = 0.0
                    take_profit = 0.0
                
                # If require_patterns is True and no patterns found, log warning and reduce confidence
                if self.require_patterns and not patterns_found:
                    logger.warning(f"{self.name}: require_patterns=True but no patterns found. LLM provided {direction} signal with {confidence:.1%} confidence but no specific patterns. Consider disabling require_patterns or using a more detailed prompt.")
                    # Reduce confidence but don't force neutral (LLM analysis may still be valid)
                    confidence = confidence * 0.5
                
                return {
                    "direction": direction,
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "patterns_found": json.dumps(patterns_found),
                    "suggested_stop_loss": stop_loss,
                    "suggested_take_profit": take_profit,
                    "suggested_position_size": position_size,
                    "current_price": current_price,
                    # Include percentages for recalculation in backtest mode
                    "stop_loss_pct": stop_loss_pct,
                    "take_profit_pct": take_profit_pct,
                }
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning(f"{self.name}: Failed to parse JSON from LLM: {e}")
        
        # Fallback: Parse natural language response
        logger.warning(f"{self.name}: No valid JSON found, parsing natural language")
        
        direction = "neutral"
        confidence = 0.3
        
        llm_lower = llm_output.lower()
        if "buy" in llm_lower or "bullish" in llm_lower or "long" in llm_lower:
            direction = "bullish"
            confidence = 0.5
        elif "sell" in llm_lower or "bearish" in llm_lower or "short" in llm_lower:
            direction = "bearish"
            confidence = 0.5
        
        # If require_patterns is True, warn about lack of structured patterns
        if self.require_patterns:
            logger.warning(f"{self.name}: require_patterns=True but LLM response was not parseable JSON. Falling back to natural language parsing. Consider improving the LLM prompt or disabling require_patterns.")
            # Reduce confidence since we couldn't get structured output
            confidence = confidence * 0.3
        
        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": llm_output[:500],  # First 500 chars
            "patterns_found": "[]",
            "suggested_stop_loss": current_price * (1 - self.stop_loss_pct) if direction == "bullish" else current_price * (1 + self.stop_loss_pct),
            "suggested_take_profit": current_price * (1 + self.take_profit_pct) if direction == "bullish" else current_price * (1 - self.take_profit_pct),
            "suggested_position_size": 0.2,
            # Include percentages for recalculation in backtest mode
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "current_price": current_price,
        }
    
    def _cache_analysis(self, analysis: Dict):
        """Cache analysis results in database"""
        if not self.db_manager:
            return
        
        try:
            cache_valid_until = datetime.utcnow() + timedelta(minutes=self.cache_minutes)
            
            analysis_data = {
                "timestamp": datetime.utcnow(),
                "analysis_period_days": analysis.get("analysis_period_days", self.lookback_days),
                "num_trades_analyzed": analysis.get("num_trades_analyzed", 0),
                "direction": analysis["direction"],
                "confidence": analysis["confidence"],
                "reasoning": analysis["reasoning"],
                "patterns_found": analysis["patterns_found"],  # Already JSON string
                "suggested_stop_loss": analysis["suggested_stop_loss"],
                "suggested_take_profit": analysis["suggested_take_profit"],
                "suggested_position_size": analysis["suggested_position_size"],
                "current_price": analysis["current_price"],
                "recent_win_rate": analysis.get("recent_win_rate", 0.0),
                "recent_pnl": analysis.get("recent_pnl", 0.0),
                "model_used": analysis.get("model_used", self.model),
                "analysis_duration_ms": analysis.get("analysis_duration_ms", 0),
                "cache_valid_until": cache_valid_until,
            }
            
            self.db_manager.add_llm_analysis(analysis_data)
            logger.info(f"{self.name}: Analysis cached until {cache_valid_until}")
            
        except Exception as e:
            logger.warning(f"{self.name}: Failed to cache analysis: {e}")
    
    def _signal_from_analysis(self, analysis: Dict, exchange, symbol: str, override_price: float = None) -> StrategySignal:
        """
        Convert LLM analysis to StrategySignal.
        
        Args:
            analysis: LLM analysis results
            exchange: CCXT exchange instance
            symbol: Trading pair
            override_price: If provided, use this price instead of analysis price or live price.
                           This is used during backtesting to ensure correct historical price.
        """
        
        # Priority: override_price (backtest) > analysis price > live price
        if override_price and override_price > 0:
            current_price = override_price
        else:
            current_price = analysis.get("current_price", 0.0)
            if current_price <= 0:
                current_price = self._get_current_price(exchange, symbol)
        
        # Safety check: never return a signal with 0 price (causes division by zero in paper trader)
        if current_price <= 0:
            logger.warning(f"{self.name}: Cannot determine valid price, returning neutral")
            return StrategySignal(
                direction="neutral",
                price=1.0,  # Dummy price to avoid division by zero
                confidence=0.0,
                timestamp=datetime.now(timezone.utc),
                strategy_name=self.name,
                stop_loss=0.0,
                take_profit=0.0,
                position_size=0.0,
                indicators={},
                info={"reason": "Invalid price data"},
            )
        
        patterns_list = []
        if isinstance(analysis.get("patterns_found"), str):
            try:
                patterns_list = json.loads(analysis["patterns_found"])
            except:
                pass
        elif isinstance(analysis.get("patterns_found"), list):
            patterns_list = analysis["patterns_found"]
        
        # Indicators should only contain numeric values (they get averaged by strategy manager)
        indicators = {
            "patterns_count": len(patterns_list),
            "rsi": analysis.get("rsi", 50.0),  # Include technical indicators for aggregation
            "confidence_pct": analysis["confidence"] * 100,
        }
        
        info = {
            "reasoning": analysis.get("reasoning", "No reasoning provided"),
            "patterns": patterns_list,
            "model": analysis.get("model_used", self.model),
            "cached": "cache_valid_until" in analysis,
        }
        
        # Recalculate stop loss and take profit based on the correct price
        # This ensures backtest uses candle price, not analysis price
        direction = analysis["direction"]
        stop_loss_pct = analysis.get("stop_loss_pct", self.stop_loss_pct)
        take_profit_pct = analysis.get("take_profit_pct", self.take_profit_pct)
        
        if direction == "bullish":
            stop_loss = current_price * (1 - stop_loss_pct)
            take_profit = current_price * (1 + take_profit_pct)
        elif direction == "bearish":
            stop_loss = current_price * (1 + stop_loss_pct)
            take_profit = current_price * (1 - take_profit_pct)
        else:
            stop_loss = 0.0
            take_profit = 0.0
        
        return StrategySignal(
            direction=direction,
            price=current_price,
            confidence=analysis["confidence"],
            timestamp=datetime.now(timezone.utc),
            strategy_name=self.name,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=analysis.get("suggested_position_size", 0.2),
            indicators=indicators,
            info=info,
        )
    
    def _neutral_signal(self, exchange, symbol: str, override_price: float = None) -> StrategySignal:
        """
        Return a neutral signal (no trade).
        
        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair
            override_price: If provided, use this price instead of fetching live price.
        """
        if override_price and override_price > 0:
            current_price = override_price
        else:
            current_price = self._get_current_price(exchange, symbol)
        
        # If we can't get current price, use dummy price (signal won't be traded anyway since it's neutral)
        if current_price <= 0:
            logger.warning(f"{self.name}: Cannot fetch current price for neutral signal, using dummy price")
            current_price = 1.0
        
        return StrategySignal(
            direction="neutral",
            price=current_price,
            confidence=0.0,
            timestamp=datetime.now(timezone.utc),
            strategy_name=self.name,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
            indicators={},
            info={"reason": "Insufficient data or LLM unavailable"},
        )
    
    def _get_current_price(self, exchange, symbol: str) -> float:
        """Get current market price"""
        try:
            ticker = exchange.fetch_ticker(symbol)
            return float(ticker["last"])
        except Exception as e:
            logger.warning(f"{self.name}: Failed to fetch current price: {e}")
            return 0.0
    
    def get_description(self) -> str:
        return f"LLM Market Analysis using {self.model} (analyzes technical indicators, patterns, cache: {self.cache_minutes}min)"
    
    def get_parameters(self) -> Dict[str, object]:
        return {
            "ollama_url": self.ollama_url,
            "model": self.model,
            "lookback_days": self.lookback_days,
            "cache_minutes": self.cache_minutes,
            "timeout_seconds": self.timeout_seconds,
            "temperature": self.temperature,
            "num_predict": self.num_predict,
            "require_patterns": self.require_patterns,
            "backtest_sample_interval": self.backtest_sample_interval,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "min_position_size": self.min_position_size,
            "max_position_size": self.max_position_size,
        }
