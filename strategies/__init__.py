"""
Multi-strategy trading system for Next-Gen Trading Bot.

Supports multiple concurrent trading strategies with signal aggregation.
"""

from .base_strategy import BaseStrategy, StrategySignal
from .ema_crossover_strategy import EMACrossoverStrategy
from .rsi_bb_strategy import RSIBollingerBandsStrategy
from .macd_volume_strategy import MACDVolumeStrategy
from .strategy_manager import StrategyManager, SignalAggregationMode
from .constants import StrategyNames

# LLM strategy is optional (requires database and Ollama)
try:
    from .llm.strategy import LLMPatternStrategy
    LLM_AVAILABLE = True
except ImportError:
    LLMPatternStrategy = None
    LLM_AVAILABLE = False

__all__ = [
    'BaseStrategy',
    'StrategySignal',
    'EMACrossoverStrategy',
    'RSIBollingerBandsStrategy',
    'MACDVolumeStrategy',
    'StrategyManager',
    'SignalAggregationMode',
    'StrategyNames',
    'LLMPatternStrategy',
    'LLM_AVAILABLE',
]
