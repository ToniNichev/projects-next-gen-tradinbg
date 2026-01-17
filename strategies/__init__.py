"""
Multi-strategy trading system for Next-Gen Trading Bot.

Supports multiple concurrent trading strategies with signal aggregation.
"""

from .base_strategy import BaseStrategy, StrategySignal
from .ema_crossover_strategy import EMACrossoverStrategy
from .rsi_bb_strategy import RSIBollingerBandsStrategy
from .macd_volume_strategy import MACDVolumeStrategy
from .strategy_manager import StrategyManager, SignalAggregationMode

__all__ = [
    'BaseStrategy',
    'StrategySignal',
    'EMACrossoverStrategy',
    'RSIBollingerBandsStrategy',
    'MACDVolumeStrategy',
    'StrategyManager',
    'SignalAggregationMode',
]
