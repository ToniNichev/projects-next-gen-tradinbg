"""
Strategy name constants to prevent typos and mismatches.

This module provides centralized constants for all strategy names,
display names, and configuration keys. Using these constants ensures
consistency across the codebase and prevents bugs from typos.

Usage:
    from strategies.constants import StrategyNames
    
    # Use constant instead of string
    if strategy.name == StrategyNames.EMA_CROSSOVER:
        ...
    
    # Get display name for UI
    display = StrategyNames.get_display_name(strategy.name)
    
    # Get config key for database
    config_key = StrategyNames.get_config_key(strategy.name)
"""

from typing import Optional


class StrategyNames:
    """Centralized strategy name constants"""
    
    # Internal strategy names (match class definitions)
    EMA_CROSSOVER = "EMA_Crossover"
    RSI_BB_MEAN_REVERSION = "RSI_BB_MeanReversion"
    MACD_VOLUME_MOMENTUM = "MACD_Volume_Momentum"
    LLM_PATTERN = "llm_pattern"
    
    # Display names for UI (user-friendly)
    DISPLAY_NAMES = {
        EMA_CROSSOVER: "EMA Crossover",
        RSI_BB_MEAN_REVERSION: "RSI + Bollinger Bands",
        MACD_VOLUME_MOMENTUM: "MACD + Volume Momentum",
        LLM_PATTERN: "LLM Pattern Analysis",
    }
    
    # Config keys for database persistence
    CONFIG_KEYS = {
        EMA_CROSSOVER: "strategy_ema_enabled",
        RSI_BB_MEAN_REVERSION: "strategy_rsi_bb_enabled",
        MACD_VOLUME_MOMENTUM: "strategy_macd_enabled",
        LLM_PATTERN: "strategy_llm_enabled",
    }
    
    # Strategy configuration section names
    CONFIG_SECTIONS = {
        EMA_CROSSOVER: "ema_crossover",
        RSI_BB_MEAN_REVERSION: "rsi_bb",
        MACD_VOLUME_MOMENTUM: "macd_volume",
        LLM_PATTERN: "llm_pattern",
    }
    
    # Strategy types/categories
    STRATEGY_TYPES = {
        EMA_CROSSOVER: "Trend Following",
        RSI_BB_MEAN_REVERSION: "Mean Reversion",
        MACD_VOLUME_MOMENTUM: "Momentum Breakout",
        LLM_PATTERN: "AI Pattern Recognition",
    }
    
    # Strategy icons (for UI)
    STRATEGY_ICONS = {
        EMA_CROSSOVER: "📈",
        RSI_BB_MEAN_REVERSION: "🌊",
        MACD_VOLUME_MOMENTUM: "📊",
        LLM_PATTERN: "🤖",
    }
    
    @classmethod
    def all_names(cls) -> list[str]:
        """
        Get list of all strategy names.
        
        Returns:
            List of internal strategy names
        """
        return [
            cls.EMA_CROSSOVER,
            cls.RSI_BB_MEAN_REVERSION,
            cls.MACD_VOLUME_MOMENTUM,
            cls.LLM_PATTERN,
        ]
    
    @classmethod
    def get_display_name(cls, strategy_name: str) -> str:
        """
        Get user-friendly display name for a strategy.
        
        Args:
            strategy_name: Internal strategy name
            
        Returns:
            Display name for UI, or original name if not found
        """
        return cls.DISPLAY_NAMES.get(strategy_name, strategy_name)
    
    @classmethod
    def get_config_key(cls, strategy_name: str) -> Optional[str]:
        """
        Get database configuration key for a strategy.
        
        Args:
            strategy_name: Internal strategy name
            
        Returns:
            Configuration key for database, or None if not found
        """
        return cls.CONFIG_KEYS.get(strategy_name)
    
    @classmethod
    def get_config_section(cls, strategy_name: str) -> Optional[str]:
        """
        Get configuration section name for a strategy.
        
        Args:
            strategy_name: Internal strategy name
            
        Returns:
            Configuration section name, or None if not found
        """
        return cls.CONFIG_SECTIONS.get(strategy_name)
    
    @classmethod
    def get_strategy_type(cls, strategy_name: str) -> str:
        """
        Get strategy type/category.
        
        Args:
            strategy_name: Internal strategy name
            
        Returns:
            Strategy type, or "Unknown" if not found
        """
        return cls.STRATEGY_TYPES.get(strategy_name, "Unknown")
    
    @classmethod
    def get_icon(cls, strategy_name: str) -> str:
        """
        Get icon emoji for a strategy.
        
        Args:
            strategy_name: Internal strategy name
            
        Returns:
            Icon emoji, or default icon if not found
        """
        return cls.STRATEGY_ICONS.get(strategy_name, "📊")
    
    @classmethod
    def is_valid_strategy(cls, strategy_name: str) -> bool:
        """
        Check if a strategy name is valid.
        
        Args:
            strategy_name: Strategy name to check
            
        Returns:
            True if valid, False otherwise
        """
        return strategy_name in cls.all_names()
    
    @classmethod
    def validate_strategy_name(cls, strategy_name: str) -> str:
        """
        Validate and return strategy name, or raise error.
        
        Args:
            strategy_name: Strategy name to validate
            
        Returns:
            Validated strategy name
            
        Raises:
            ValueError: If strategy name is not valid
        """
        if not cls.is_valid_strategy(strategy_name):
            valid_names = ", ".join(cls.all_names())
            raise ValueError(
                f"Invalid strategy name: '{strategy_name}'. "
                f"Valid names are: {valid_names}"
            )
        return strategy_name


# Convenience aliases for backward compatibility
STRATEGY_EMA = StrategyNames.EMA_CROSSOVER
STRATEGY_RSI_BB = StrategyNames.RSI_BB_MEAN_REVERSION
STRATEGY_MACD = StrategyNames.MACD_VOLUME_MOMENTUM
STRATEGY_LLM = StrategyNames.LLM_PATTERN
