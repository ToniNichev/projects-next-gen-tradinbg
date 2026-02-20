"""
Configuration Service Module

Provides centralized configuration management with:
- Database-first loading with environment variable fallback
- Configuration caching for performance
- Validation logic for all configuration fields
- Preset management (save, load, apply, delete)
"""

import logging
from threading import Lock
from typing import Dict, Any, List, Optional, Tuple

from config import BotConfig


class ConfigService:
    """
    Manages configuration loading, validation, and updates.
    
    Provides thread-safe configuration management with database persistence,
    caching, and validation.
    """
    
    def __init__(self, db_manager=None):
        """
        Initialize ConfigService.
        
        Args:
            db_manager: DatabaseManager instance (optional)
        """
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self._config_cache: Optional[BotConfig] = None
        self._cache_lock = Lock()
    
    def load_config(self, force_reload: bool = False) -> BotConfig:
        """
        Load configuration from database with fallback to environment variables.
        
        Implements caching to reduce database queries. Database values take
        precedence over environment variables for strategy parameters.
        
        Args:
            force_reload: Force reload from database, bypassing cache
            
        Returns:
            BotConfig instance
            
        Validates: Requirements 6.1, 6.2, 6.3, 6.4
        """
        with self._cache_lock:
            # Step 1: Check cache
            if not force_reload and self._config_cache is not None:
                self.logger.debug("Returning cached configuration")
                return self._config_cache
            
            # Step 2: Load configuration (BotConfig.load() handles database fallback)
            try:
                config = BotConfig.load()
                self.logger.info("Configuration loaded successfully")
                
                # Step 3: Cache configuration
                self._config_cache = config
                
                return config
            except Exception as e:
                self.logger.error(f"Failed to load configuration: {e}")
                raise
    
    def get_strategy_config(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get strategy configuration.
        
        Args:
            strategy_name: Specific strategy name (e.g., 'ema_crossover', 'rsi_bb')
                          If None, returns all strategy configurations
            
        Returns:
            Dictionary with strategy configuration
        """
        config = self.load_config()
        all_strategies = config.get_strategy_configs()
        
        if strategy_name:
            if strategy_name not in all_strategies:
                raise ValueError(f"Unknown strategy: {strategy_name}")
            return all_strategies[strategy_name]
        
        return all_strategies
    
    def update_strategy_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update strategy configuration with validation.
        
        Args:
            updates: Dictionary of configuration updates
            
        Returns:
            Dictionary with success status and updated configuration
            
        Validates: Requirements 6.5, 6.6, 6.7, 6.8
        """
        # Step 1: Validate configuration
        is_valid, errors = self.validate_config(updates)
        
        if not is_valid:
            self.logger.warning(f"Configuration validation failed: {errors}")
            return {
                "success": False,
                "errors": errors,
                "message": "Configuration validation failed"
            }
        
        # Step 2: Apply changes to database
        if self.db_manager:
            try:
                # Convert updates to database format
                db_configs = {}
                for key, value in updates.items():
                    # Determine value type
                    if isinstance(value, bool):
                        value_type = "bool"
                    elif isinstance(value, int):
                        value_type = "int"
                    elif isinstance(value, float):
                        value_type = "float"
                    else:
                        value_type = "str"
                    
                    # Determine category based on key prefix
                    if key.startswith("strategy_ema_"):
                        category = "ema"
                    elif key.startswith("strategy_rsi_bb_"):
                        category = "rsi_bb"
                    elif key.startswith("strategy_macd_"):
                        category = "macd_volume"
                    elif key.startswith("strategy_llm_") or key.startswith("llm_"):
                        category = "llm_pattern"
                    elif key in ["use_multi_strategy", "strategy_aggregation_mode", "min_signal_confidence"]:
                        category = "multi_strategy"
                    else:
                        category = "general"
                    
                    db_configs[key] = {
                        "value": value,
                        "type": value_type,
                        "category": category,
                        "description": f"Configuration for {key}"
                    }
                
                # Save to database
                count = self.db_manager.set_multiple_strategy_configs(db_configs)
                self.logger.info(f"Updated {count} configuration values in database")
                
            except Exception as e:
                self.logger.error(f"Failed to persist configuration to database: {e}")
                return {
                    "success": False,
                    "errors": [f"Database error: {str(e)}"],
                    "message": "Failed to persist configuration"
                }
        
        # Step 3: Invalidate cache
        with self._cache_lock:
            self._config_cache = None
            self.logger.debug("Configuration cache invalidated")
        
        # Step 4: Return success
        return {
            "success": True,
            "data": updates,
            "message": f"Successfully updated {len(updates)} configuration values"
        }
    
    def validate_config(self, config_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate configuration data.
        
        Checks all field constraints:
        - stop_loss_pct > 0
        - order_pct between 0 and 1
        - strategy weights >= 0
        - etc.
        
        Args:
            config_data: Configuration dictionary to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
            
        Validates: Requirements 6.9, 6.10, 6.11
        """
        errors = []
        
        # Validate stop_loss_pct
        if "stop_loss_pct" in config_data:
            value = config_data["stop_loss_pct"]
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append("stop_loss_pct must be greater than 0")
        
        # Validate take_profit_pct
        if "take_profit_pct" in config_data:
            value = config_data["take_profit_pct"]
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append("take_profit_pct must be greater than 0")
        
        # Validate trailing_stop_pct
        if "trailing_stop_pct" in config_data:
            value = config_data["trailing_stop_pct"]
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append("trailing_stop_pct must be greater than 0")
        
        # Validate order_pct
        if "order_pct" in config_data:
            value = config_data["order_pct"]
            if not isinstance(value, (int, float)) or value <= 0 or value > 1:
                errors.append("order_pct must be between 0 and 1")
        
        # Validate min_position_size
        if "min_position_size" in config_data:
            value = config_data["min_position_size"]
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                errors.append("min_position_size must be between 0 and 1")
        
        # Validate max_position_size
        if "max_position_size" in config_data:
            value = config_data["max_position_size"]
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                errors.append("max_position_size must be between 0 and 1")
        
        # Validate position size relationship
        if "min_position_size" in config_data and "max_position_size" in config_data:
            min_size = config_data["min_position_size"]
            max_size = config_data["max_position_size"]
            if min_size > max_size:
                errors.append("min_position_size must be less than or equal to max_position_size")
        
        # Validate strategy weights (must be non-negative)
        weight_fields = [
            "strategy_ema_weight",
            "strategy_rsi_bb_weight",
            "strategy_macd_weight",
            "strategy_llm_weight"
        ]
        for field in weight_fields:
            if field in config_data:
                value = config_data[field]
                if not isinstance(value, (int, float)) or value < 0:
                    errors.append(f"{field} must be non-negative")
        
        # Validate min_signal_confidence
        if "min_signal_confidence" in config_data:
            value = config_data["min_signal_confidence"]
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                errors.append("min_signal_confidence must be between 0 and 1")
        
        # Validate strategy_aggregation_mode
        if "strategy_aggregation_mode" in config_data:
            value = config_data["strategy_aggregation_mode"]
            valid_modes = ["voting", "weighted_voting", "unanimous", "any", "best"]
            if value not in valid_modes:
                errors.append(f"strategy_aggregation_mode must be one of: {', '.join(valid_modes)}")
        
        # Validate RSI thresholds
        if "rsi_oversold" in config_data:
            value = config_data["rsi_oversold"]
            if not isinstance(value, (int, float)) or value < 0 or value > 100:
                errors.append("rsi_oversold must be between 0 and 100")
        
        if "rsi_overbought" in config_data:
            value = config_data["rsi_overbought"]
            if not isinstance(value, (int, float)) or value < 0 or value > 100:
                errors.append("rsi_overbought must be between 0 and 100")
        
        # Validate RSI relationship
        if "rsi_oversold" in config_data and "rsi_overbought" in config_data:
            oversold = config_data["rsi_oversold"]
            overbought = config_data["rsi_overbought"]
            if oversold >= overbought:
                errors.append("rsi_oversold must be less than rsi_overbought")
        
        # Validate volume_threshold
        if "volume_threshold" in config_data:
            value = config_data["volume_threshold"]
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append("volume_threshold must be greater than 0")
        
        # Validate ATR parameters
        if "atr_period" in config_data:
            value = config_data["atr_period"]
            if not isinstance(value, int) or value <= 0:
                errors.append("atr_period must be a positive integer")
        
        if "atr_stop_multiplier" in config_data:
            value = config_data["atr_stop_multiplier"]
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append("atr_stop_multiplier must be greater than 0")
        
        # Validate timeframe
        if "timeframe" in config_data:
            value = config_data["timeframe"]
            valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
            if value not in valid_timeframes:
                errors.append(f"timeframe must be one of: {', '.join(valid_timeframes)}")
        
        # Validate max_trades_per_day
        if "max_trades_per_day" in config_data:
            value = config_data["max_trades_per_day"]
            if not isinstance(value, int) or value <= 0:
                errors.append("max_trades_per_day must be a positive integer")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def get_presets(self) -> List[Dict[str, Any]]:
        """
        Get all configuration presets.
        
        Returns:
            List of preset dictionaries
            
        Validates: Requirement 19.3
        """
        if not self.db_manager:
            self.logger.warning("Database manager not available, cannot retrieve presets")
            return []
        
        try:
            presets = self.db_manager.get_all_presets()
            self.logger.debug(f"Retrieved {len(presets)} presets")
            return presets
        except Exception as e:
            self.logger.error(f"Failed to retrieve presets: {e}")
            return []
    
    def get_preset(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """
        Get specific preset by name.
        
        Args:
            preset_name: Name of the preset
            
        Returns:
            Preset dictionary or None if not found
            
        Validates: Requirement 19.4
        """
        if not self.db_manager:
            self.logger.warning("Database manager not available, cannot retrieve preset")
            return None
        
        try:
            preset = self.db_manager.get_preset(preset_name)
            if preset:
                self.logger.debug(f"Retrieved preset: {preset_name}")
            else:
                self.logger.warning(f"Preset not found: {preset_name}")
            return preset
        except Exception as e:
            self.logger.error(f"Failed to retrieve preset {preset_name}: {e}")
            return None
    
    def save_preset(self, preset_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save configuration preset.
        
        Args:
            preset_data: Dictionary with preset information:
                - name: Unique preset identifier (required)
                - display_name: Human-readable name (required)
                - description: Preset description (required)
                - config: Configuration dictionary (required)
                - category: Preset category (optional, default: "custom")
                - is_default: Whether this is the default preset (optional)
        
        Returns:
            Dictionary with success status and saved preset data
            
        Validates: Requirements 6.12, 19.1, 19.2
        """
        if not self.db_manager:
            return {
                "success": False,
                "error": "Database manager not available",
                "message": "Cannot save preset without database"
            }
        
        # Validate required fields
        required_fields = ["name", "display_name", "description", "config"]
        missing_fields = [f for f in required_fields if f not in preset_data]
        if missing_fields:
            return {
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}",
                "message": "Invalid preset data"
            }
        
        # Validate configuration
        is_valid, errors = self.validate_config(preset_data["config"])
        if not is_valid:
            return {
                "success": False,
                "errors": errors,
                "message": "Preset configuration validation failed"
            }
        
        try:
            saved_preset = self.db_manager.save_preset(
                name=preset_data["name"],
                display_name=preset_data["display_name"],
                description=preset_data["description"],
                config=preset_data["config"],
                category=preset_data.get("category", "custom"),
                is_builtin=False,  # User presets are never built-in
                is_default=preset_data.get("is_default", False)
            )
            
            self.logger.info(f"Saved preset: {preset_data['name']}")
            
            return {
                "success": True,
                "data": saved_preset,
                "message": f"Preset '{preset_data['display_name']}' saved successfully"
            }
        except Exception as e:
            self.logger.error(f"Failed to save preset: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to save preset"
            }
    
    def apply_preset(self, preset_name: str) -> Dict[str, Any]:
        """
        Apply configuration preset.
        
        Loads preset configuration and applies it as a configuration update.
        
        Args:
            preset_name: Name of the preset to apply
            
        Returns:
            Dictionary with success status and applied configuration
            
        Validates: Requirements 6.13, 19.5
        """
        # Step 1: Load preset
        preset = self.get_preset(preset_name)
        
        if not preset:
            return {
                "success": False,
                "error": f"Preset not found: {preset_name}",
                "message": "Cannot apply non-existent preset"
            }
        
        # Step 2: Apply preset configuration
        config_updates = preset["config"]
        result = self.update_strategy_config(config_updates)
        
        if result["success"]:
            self.logger.info(f"Applied preset: {preset_name}")
            return {
                "success": True,
                "data": {
                    "preset_name": preset_name,
                    "preset_display_name": preset["display_name"],
                    "applied_config": config_updates
                },
                "message": f"Preset '{preset['display_name']}' applied successfully"
            }
        else:
            self.logger.error(f"Failed to apply preset {preset_name}: {result.get('errors', [])}")
            return result
    
    def delete_preset(self, preset_name: str) -> Dict[str, bool]:
        """
        Delete configuration preset.
        
        Args:
            preset_name: Name of the preset to delete
            
        Returns:
            Dictionary with success status
            
        Validates: Requirements 6.14, 19.6, 19.7
        """
        if not self.db_manager:
            return {
                "success": False,
                "error": "Database manager not available",
                "message": "Cannot delete preset without database"
            }
        
        try:
            deleted = self.db_manager.delete_preset(preset_name)
            
            if deleted:
                self.logger.info(f"Deleted preset: {preset_name}")
                return {
                    "success": True,
                    "message": f"Preset '{preset_name}' deleted successfully"
                }
            else:
                # Check if preset exists
                preset = self.get_preset(preset_name)
                if preset and preset.get("is_builtin"):
                    return {
                        "success": False,
                        "error": "Cannot delete built-in preset",
                        "message": f"Preset '{preset_name}' is a built-in preset and cannot be deleted"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Preset not found",
                        "message": f"Preset '{preset_name}' does not exist"
                    }
        except Exception as e:
            self.logger.error(f"Failed to delete preset {preset_name}: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to delete preset"
            }
