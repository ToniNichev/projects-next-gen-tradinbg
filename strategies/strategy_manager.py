"""
Strategy Manager - Coordinates multiple trading strategies

Supports different signal aggregation modes:
- VOTING: Strategies vote, majority wins (conservative)
- WEIGHTED_VOTING: Weighted by strategy confidence and weight
- UNANIMOUS: All strategies must agree (very conservative)
- ANY: Any strategy can trigger (aggressive)
- BEST: Use signal from most confident strategy
"""

import logging
from collections import deque
from enum import Enum
from typing import Dict, List, Optional

from .base_strategy import BaseStrategy, StrategySignal
from .constants import StrategyNames


class SignalAggregationMode(Enum):
    """Different modes for combining signals from multiple strategies"""
    VOTING = "voting"  # Majority vote (≥50% of enabled strategies)
    WEIGHTED_VOTING = "weighted_voting"  # Weighted by confidence and strategy weight
    UNANIMOUS = "unanimous"  # All enabled strategies must agree
    ANY = "any"  # Any strategy can trigger
    BEST = "best"  # Use most confident strategy's signal
    

class StrategyManager:
    """Manages multiple trading strategies and aggregates their signals"""
    
    def __init__(
        self,
        strategies: List[BaseStrategy],
        aggregation_mode: SignalAggregationMode = SignalAggregationMode.WEIGHTED_VOTING,
        min_confidence: float = 0.3,
    ):
        """
        Initialize strategy manager.
        
        Args:
            strategies: List of strategy instances
            aggregation_mode: How to combine signals from multiple strategies
            min_confidence: Minimum confidence threshold (0.0 to 1.0)
        """
        self.strategies = strategies
        self.aggregation_mode = aggregation_mode
        self.min_confidence = min_confidence
        self.logger = logging.getLogger(__name__)
        
        # Per-strategy last signal (keyed by strategy name)
        self.last_signals: dict = {}

        # Rolling indicator history for sparklines (last 50 candles)
        self.signal_history: dict = {
            s.name: deque(maxlen=50) for s in strategies
        }

        # Strategy performance tracking
        self.strategy_stats = {
            strategy.name: {
                "signals_generated": 0,
                "signals_used": 0,
                "total_confidence": 0.0,
                "avg_confidence": 0.0,
            }
            for strategy in strategies
        }
    
    def compute_aggregate_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        """
        Compute signals from all enabled strategies and aggregate them.
        
        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair
            timeframe: Candle timeframe
            candle_data: Optional pre-fetched candle data
            
        Returns:
            Aggregated StrategySignal
        """
        # Get signals from all enabled strategies
        signals = []
        for strategy in self.strategies:
            if not strategy.is_enabled():
                continue
            
            try:
                signal = strategy.compute_signal(exchange, symbol, timeframe, candle_data)
                signals.append(signal)
                self.last_signals[strategy.name] = signal
                self.signal_history[strategy.name].append({
                    "t": signal.timestamp.isoformat() if signal.timestamp else None,
                    "d": signal.direction,
                    "c": round(signal.confidence, 3),
                    "i": dict(signal.indicators or {}),
                })

                # Track stats
                self.strategy_stats[strategy.name]["signals_generated"] += 1
                self.strategy_stats[strategy.name]["total_confidence"] += signal.confidence
                self.strategy_stats[strategy.name]["avg_confidence"] = (
                    self.strategy_stats[strategy.name]["total_confidence"] /
                    self.strategy_stats[strategy.name]["signals_generated"]
                )
                
                self.logger.debug(
                    f"[{strategy.name}] Signal: {signal.direction} "
                    f"(confidence: {signal.confidence:.2f}, price: {signal.price:.2f})"
                )
                
            except Exception as e:
                self.logger.error(f"Strategy {strategy.name} failed: {e}", exc_info=True)
                continue
        
        if not signals:
            # No signals from any strategy - return neutral
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
        
        # Aggregate signals based on mode
        if self.aggregation_mode == SignalAggregationMode.VOTING:
            return self._aggregate_voting(signals, exchange, symbol, timeframe, candle_data)
        elif self.aggregation_mode == SignalAggregationMode.WEIGHTED_VOTING:
            return self._aggregate_weighted_voting(signals, exchange, symbol, timeframe, candle_data)
        elif self.aggregation_mode == SignalAggregationMode.UNANIMOUS:
            return self._aggregate_unanimous(signals, exchange, symbol, timeframe, candle_data)
        elif self.aggregation_mode == SignalAggregationMode.ANY:
            return self._aggregate_any(signals, exchange, symbol, timeframe, candle_data)
        elif self.aggregation_mode == SignalAggregationMode.BEST:
            return self._aggregate_best(signals, exchange, symbol, timeframe, candle_data)
        else:
            return self._aggregate_weighted_voting(signals, exchange, symbol, timeframe, candle_data)
    
    def _aggregate_voting(self, signals: List[StrategySignal], exchange, symbol, timeframe, candle_data) -> StrategySignal:
        """Simple majority voting"""
        # Filter by minimum confidence
        valid_signals = [s for s in signals if s.confidence >= self.min_confidence]
        
        if not valid_signals:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
        
        # Count votes
        bullish_votes = sum(1 for s in valid_signals if s.direction == "bullish")
        bearish_votes = sum(1 for s in valid_signals if s.direction == "bearish")
        total_votes = len(valid_signals)
        
        # Majority wins (need >50%)
        if bullish_votes > total_votes / 2:
            return self._create_aggregated_signal(signals, "bullish")
        elif bearish_votes > total_votes / 2:
            return self._create_aggregated_signal(signals, "bearish")
        else:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
    
    def _aggregate_weighted_voting(self, signals: List[StrategySignal], exchange, symbol, timeframe, candle_data) -> StrategySignal:
        """Weighted voting by confidence and strategy weight"""
        # Filter by minimum confidence
        valid_signals = [s for s in signals if s.confidence >= self.min_confidence]
        
        if not valid_signals:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
        
        # Calculate weighted scores
        bullish_weight = 0.0
        bearish_weight = 0.0
        
        for signal in valid_signals:
            strategy = self._get_strategy_by_name(signal.strategy_name)
            weight = strategy.get_weight() if strategy else 1.0
            weighted_confidence = signal.confidence * weight
            
            if signal.direction == "bullish":
                bullish_weight += weighted_confidence
            elif signal.direction == "bearish":
                bearish_weight += weighted_confidence
        
        # Determine direction based on weighted votes
        total_weight = bullish_weight + bearish_weight
        if total_weight == 0:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
        
        if bullish_weight > bearish_weight and bullish_weight / total_weight > 0.5:
            return self._create_aggregated_signal(signals, "bullish")
        elif bearish_weight > bullish_weight and bearish_weight / total_weight > 0.5:
            return self._create_aggregated_signal(signals, "bearish")
        else:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
    
    def _aggregate_unanimous(self, signals: List[StrategySignal], exchange, symbol, timeframe, candle_data) -> StrategySignal:
        """All strategies must agree"""
        valid_signals = [s for s in signals if s.confidence >= self.min_confidence and s.direction != "neutral"]
        
        if not valid_signals:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
        
        # All must have the same direction
        first_direction = valid_signals[0].direction
        if all(s.direction == first_direction for s in valid_signals):
            return self._create_aggregated_signal(signals, first_direction)
        else:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
    
    def _aggregate_any(self, signals: List[StrategySignal], exchange, symbol, timeframe, candle_data) -> StrategySignal:
        """Any strategy can trigger (use highest confidence)"""
        valid_signals = [s for s in signals if s.confidence >= self.min_confidence and s.direction != "neutral"]
        
        if not valid_signals:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
        
        # Use signal with highest confidence
        best_signal = max(valid_signals, key=lambda s: s.confidence)
        
        # Mark that this strategy's signal was used
        self.strategy_stats[best_signal.strategy_name]["signals_used"] += 1
        
        return best_signal
    
    def _aggregate_best(self, signals: List[StrategySignal], exchange, symbol, timeframe, candle_data) -> StrategySignal:
        """Use most confident strategy's signal"""
        valid_signals = [s for s in signals if s.confidence >= self.min_confidence]
        
        if not valid_signals:
            return self._create_neutral_signal(exchange, symbol, timeframe, candle_data)
        
        # Find signal with highest confidence
        best_signal = max(valid_signals, key=lambda s: s.confidence)
        
        # Mark that this strategy's signal was used
        self.strategy_stats[best_signal.strategy_name]["signals_used"] += 1
        
        return best_signal
    
    def _create_aggregated_signal(self, signals: List[StrategySignal], direction: str) -> StrategySignal:
        """
        Create an aggregated signal by combining multiple signals.
        
        Uses weighted average of stop loss, take profit, and position size.
        """
        relevant_signals = [s for s in signals if s.direction == direction and s.confidence >= self.min_confidence]
        
        if not relevant_signals:
            relevant_signals = [s for s in signals if s.direction == direction]
        
        if not relevant_signals:
            # Fallback to all signals
            relevant_signals = signals
        
        # Mark strategies as used
        for signal in relevant_signals:
            self.strategy_stats[signal.strategy_name]["signals_used"] += 1
        
        # Calculate weighted averages (guard against all-zero confidence signals)
        total_confidence = sum(s.confidence for s in relevant_signals)
        
        if total_confidence > 0:
            avg_price = sum(s.price * s.confidence for s in relevant_signals) / total_confidence
            avg_stop_loss = sum(s.stop_loss * s.confidence for s in relevant_signals) / total_confidence
            avg_take_profit = sum(s.take_profit * s.confidence for s in relevant_signals) / total_confidence
            avg_position_size = sum(s.position_size * s.confidence for s in relevant_signals) / total_confidence
        else:
            # All signals have zero confidence — fall back to simple (unweighted) average
            n = len(relevant_signals)
            avg_price = sum(s.price for s in relevant_signals) / n
            avg_stop_loss = sum(s.stop_loss for s in relevant_signals) / n
            avg_take_profit = sum(s.take_profit for s in relevant_signals) / n
            avg_position_size = sum(s.position_size for s in relevant_signals) / n
        avg_confidence = total_confidence / len(relevant_signals)
        
        # Combine indicators
        combined_indicators = {}
        for signal in relevant_signals:
            for key, value in signal.indicators.items():
                if key not in combined_indicators:
                    combined_indicators[key] = []
                combined_indicators[key].append(value)
        
        # Average indicator values
        avg_indicators = {
            key: sum(values) / len(values)
            for key, values in combined_indicators.items()
        }
        
        # Combine info
        combined_info = {
            "aggregation_mode": self.aggregation_mode.value,
            "strategies_used": [s.strategy_name for s in relevant_signals],
            "num_strategies": len(relevant_signals),
        }
        
        return StrategySignal(
            direction=direction,
            price=avg_price,
            confidence=min(1.0, avg_confidence),
            timestamp=relevant_signals[0].timestamp,
            strategy_name="Aggregated",
            stop_loss=avg_stop_loss,
            take_profit=avg_take_profit,
            position_size=avg_position_size,
            indicators=avg_indicators,
            info=combined_info,
        )
    
    def _create_neutral_signal(self, exchange, symbol, timeframe, candle_data) -> StrategySignal:
        """Create a neutral signal when no trading signal is generated"""
        # Get current price
        if candle_data and len(candle_data) > 0:
            price = float(candle_data[-1][4])  # Close price
            timestamp_ms = int(candle_data[-1][0])
        else:
            try:
                ticker = exchange.fetch_ticker(symbol)
                price = float(ticker['last'])
                timestamp_ms = int(ticker['timestamp'])
            except:
                price = 0.0
                timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        from datetime import datetime, timezone
        return StrategySignal(
            direction="neutral",
            price=price,
            confidence=0.0,
            timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
            strategy_name="Aggregated",
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
            indicators={},
            info={"aggregation_mode": self.aggregation_mode.value},
        )
    
    def _get_strategy_by_name(self, name: str) -> Optional[BaseStrategy]:
        """Get strategy instance by name"""
        for strategy in self.strategies:
            if strategy.name == name:
                return strategy
        return None
    
    def get_strategy_stats(self) -> Dict[str, Dict]:
        """Get performance statistics for all strategies"""
        return self.strategy_stats.copy()
    
    def get_enabled_strategies(self) -> List[BaseStrategy]:
        """Get list of enabled strategies"""
        return [s for s in self.strategies if s.is_enabled()]
    
    def enable_strategy(self, strategy_name: str):
        """Enable a strategy by name"""
        strategy = self._get_strategy_by_name(strategy_name)
        if strategy:
            strategy.set_enabled(True)
            self.logger.info(f"Enabled strategy: {strategy_name}")
        else:
            self.logger.warning(f"Strategy not found: {strategy_name}")
    
    def disable_strategy(self, strategy_name: str):
        """Disable a strategy by name"""
        strategy = self._get_strategy_by_name(strategy_name)
        if strategy:
            strategy.set_enabled(False)
            self.logger.info(f"Disabled strategy: {strategy_name}")
        else:
            self.logger.warning(f"Strategy not found: {strategy_name}")
    
    def set_aggregation_mode(self, mode: SignalAggregationMode):
        """Change signal aggregation mode"""
        self.aggregation_mode = mode
        self.logger.info(f"Changed aggregation mode to: {mode.value}")
    
    def reload_config(self, config):
        """
        Reload configuration for all strategies without recreating instances.
        This allows hot-reloading of parameters without restarting the bot.
        
        Args:
            config: BotConfig instance with updated parameters
        """
        self.logger.info("Reloading strategy configuration...")
        
        # Update aggregation mode
        try:
            mode_str = config.strategy_aggregation_mode
            self.aggregation_mode = SignalAggregationMode(mode_str)
            self.logger.info(f"Updated aggregation mode: {mode_str}")
        except Exception as e:
            self.logger.error(f"Failed to update aggregation mode: {e}")
        
        # Update minimum confidence
        self.min_confidence = config.min_signal_confidence
        self.logger.info(f"Updated min confidence: {self.min_confidence}")
        
        # Get strategy configs
        strategy_configs = config.get_strategy_configs()
        
        # Update each strategy using centralized constants
        for strategy in self.strategies:
            try:
                # Get config section name from constants
                config_section = StrategyNames.get_config_section(strategy.name)
                
                if not config_section:
                    self.logger.warning(f"No config section found for strategy: {strategy.name}")
                    continue
                
                # Load strategy config
                strategy_config = strategy_configs.get(config_section, {})
                
                # Update enabled state and weight
                strategy.set_enabled(strategy_config.get("enabled", True))
                strategy.weight = strategy_config.get("weight", 1.0)
                
                # Update strategy-specific parameters if available
                if hasattr(strategy, 'config'):
                    for key, value in strategy_config.items():
                        if hasattr(strategy.config, key):
                            setattr(strategy.config, key, value)
                
                # Log the reload
                display_name = StrategyNames.get_display_name(strategy.name)
                self.logger.info(
                    f"Reloaded {display_name}: "
                    f"enabled={strategy.is_enabled()}, "
                    f"weight={strategy.weight}"
                )
            
            except Exception as e:
                self.logger.error(f"Failed to reload strategy {strategy.name}: {e}", exc_info=True)
        
        self.logger.info(f"Configuration reload complete. Active strategies: {len(self.get_enabled_strategies())}")
