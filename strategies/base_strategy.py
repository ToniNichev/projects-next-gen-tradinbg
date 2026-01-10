"""
Base strategy interface for multi-strategy trading system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Literal, Optional


@dataclass
class StrategySignal:
    """Trading signal with risk management parameters"""
    
    direction: Literal["bullish", "bearish", "neutral"]
    price: float
    confidence: float  # 0.0 to 1.0 - signal confidence/strength
    timestamp: datetime
    strategy_name: str  # Which strategy generated this signal
    
    # Risk management fields
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_size: float = 0.0  # Dynamic position size (0.0 to 1.0)
    
    # Technical indicator values
    indicators: Dict[str, float] = None
    
    # Additional metadata
    info: Dict[str, object] = None

    def __post_init__(self):
        if self.indicators is None:
            self.indicators = {}
        if self.info is None:
            self.info = {}
    
    def to_dict(self) -> Dict[str, object]:
        return {
            "direction": self.direction,
            "price": self.price,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "strategy_name": self.strategy_name,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "position_size": self.position_size,
            "indicators": self.indicators,
            "info": self.info,
        }


class BaseStrategy(ABC):
    """Abstract base class for trading strategies"""
    
    def __init__(self, name: str, config: dict):
        """
        Initialize strategy.
        
        Args:
            name: Strategy identifier
            config: Strategy-specific configuration
        """
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", True)
        self.weight = config.get("weight", 1.0)  # For weighted voting
        
    @abstractmethod
    def compute_signal(
        self,
        exchange,
        symbol: str,
        timeframe: str,
        candle_data: Optional[list] = None,
    ) -> StrategySignal:
        """
        Compute trading signal based on strategy logic.
        
        Args:
            exchange: CCXT exchange instance
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Candle timeframe (e.g., "1h")
            candle_data: Optional pre-fetched candle data
            
        Returns:
            StrategySignal object with direction and risk parameters
        """
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Return human-readable strategy description"""
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict[str, object]:
        """Return current strategy parameters"""
        pass
    
    def is_enabled(self) -> bool:
        """Check if strategy is enabled"""
        return self.enabled
    
    def set_enabled(self, enabled: bool):
        """Enable or disable strategy"""
        self.enabled = enabled
    
    def get_weight(self) -> float:
        """Get strategy weight for voting"""
        return self.weight
