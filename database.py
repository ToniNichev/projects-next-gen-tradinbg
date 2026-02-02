"""
Database module for trading bot using SQLAlchemy ORM.

Provides models for:
- Trade: Individual trade records
- Position: Historical position tracking
- Candle: Market data storage
- PerformanceMetrics: Performance snapshots
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Boolean,
    Index,
    create_engine,
    desc,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

Base = declarative_base()


class Trade(Base):
    """Trade records table"""

    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    side = Column(String(10), nullable=False, index=True)  # buy, sell
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    notional = Column(Float, nullable=False)  # Total value
    fee = Column(Float, nullable=False)
    slippage = Column(Float, nullable=False)
    usdt_balance = Column(Float, nullable=False)
    base_balance = Column(Float, nullable=False)
    exit_reason = Column(String(50), index=True)  # signal, stop_loss, take_profit, trailing_stop
    pnl = Column(Float)  # Profit/Loss for exit trades
    
    # Strategy signal data (stored as JSON-like fields)
    signal_direction = Column(String(20))  # bullish, bearish, neutral
    signal_price = Column(Float)
    short_ema = Column(Float)
    long_ema = Column(Float)
    trend_strength = Column(Float)
    rsi = Column(Float)
    atr = Column(Float)
    position_size = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    
    # Multi-strategy attribution
    strategy_name = Column(String(50), index=True)  # Which strategy generated the signal
    signal_confidence = Column(Float)  # Signal confidence (0.0 to 1.0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    # Indexes for common queries
    __table_args__ = (
        Index("idx_timestamp_side", "timestamp", "side"),
        Index("idx_exit_reason", "exit_reason"),
        Index("idx_pnl", "pnl"),
    )

    def __repr__(self):
        return f"<Trade(id={self.id}, side={self.side}, price={self.price}, timestamp={self.timestamp})>"


class Position(Base):
    """Historical position tracking"""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    side = Column(String(10), nullable=False)  # long, short
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False, index=True)
    exit_price = Column(Float)
    exit_time = Column(DateTime, index=True)
    amount = Column(Float, nullable=False)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    trailing_stop = Column(Float)
    highest_price = Column(Float)  # For trailing stop tracking
    lowest_price = Column(Float)  # For short positions
    exit_reason = Column(String(50), index=True)
    pnl = Column(Float)
    pnl_percent = Column(Float)
    is_open = Column(Boolean, default=True, index=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_entry_time", "entry_time"),
        Index("idx_is_open", "is_open"),
    )

    def __repr__(self):
        status = "OPEN" if self.is_open else "CLOSED"
        return f"<Position(id={self.id}, side={self.side}, {status}, entry={self.entry_price})>"


class Candle(Base):
    """Market data candles for historical analysis"""

    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)  # 1m, 5m, 1h, etc.
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    
    # Technical indicators (optional, can be calculated on-the-fly)
    ema_short = Column(Float)
    ema_long = Column(Float)
    rsi = Column(Float)
    atr = Column(Float)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_symbol_timeframe_timestamp", "symbol", "timeframe", "timestamp", unique=True),
    )

    def __repr__(self):
        return f"<Candle({self.symbol}, {self.timeframe}, {self.timestamp}, close={self.close})>"


class PerformanceMetrics(Base):
    """Performance metrics snapshots"""

    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    period = Column(String(20), nullable=False)  # daily, weekly, monthly
    
    # Portfolio metrics
    total_value = Column(Float, nullable=False)
    usdt_balance = Column(Float, nullable=False)
    base_balance = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)
    pnl_percent = Column(Float, nullable=False)
    
    # Trading metrics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float)
    avg_pnl = Column(Float)
    
    # Risk metrics
    max_drawdown = Column(Float)
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_timestamp_period", "timestamp", "period"),
    )

    def __repr__(self):
        return f"<PerformanceMetrics({self.period}, {self.timestamp}, pnl={self.pnl_percent:.2f}%)>"


class StrategyConfig(Base):
    """Strategy configuration storage for dynamic parameter updates"""

    __tablename__ = "strategy_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(String(500), nullable=False)
    value_type = Column(String(20), nullable=False)  # bool, int, float, str
    category = Column(String(50), nullable=False, index=True)  # multi_strategy, ema, rsi_bb, general
    description = Column(String(500))
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<StrategyConfig(key={self.key}, value={self.value}, type={self.value_type})>"
    
    def get_typed_value(self):
        """Convert string value to proper type"""
        if self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        elif self.value_type == "int":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        else:
            return self.value


class StrategyPreset(Base):
    """Strategy configuration presets for quick switching between different trading styles"""

    __tablename__ = "strategy_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    display_name = Column(String(100), nullable=False)
    description = Column(String(500))
    config_json = Column(String(10000), nullable=False)  # JSON blob of all parameters
    is_builtin = Column(Boolean, default=False, index=True)  # Built-in vs user-created
    is_default = Column(Boolean, default=False)
    category = Column(String(50))  # conservative, aggressive, scalping, swing, custom
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<StrategyPreset(name={self.name}, category={self.category})>"


class DatabaseManager:
    """Database connection and session management"""

    def __init__(self, database_url: str = "sqlite:///data/trading.db"):
        """
        Initialize database manager.
        
        Args:
            database_url: SQLAlchemy database URL
        """
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.logger = logging.getLogger(__name__)

    def create_tables(self):
        """Create all tables if they don't exist"""
        Base.metadata.create_all(bind=self.engine)
        self.logger.info("Database tables created successfully")
        
        # Initialize built-in presets
        try:
            self.initialize_builtin_presets()
        except Exception as e:
            self.logger.warning(f"Failed to initialize built-in presets: {e}")

    def drop_tables(self):
        """Drop all tables (use with caution!)"""
        Base.metadata.drop_all(bind=self.engine)
        self.logger.warning("All database tables dropped")

    @contextmanager
    def get_session(self) -> Session:
        """
        Context manager for database sessions.
        
        Usage:
            with db_manager.get_session() as session:
                session.add(trade)
                session.commit()
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def add_trade(self, trade_data: Dict) -> Trade:
        """
        Add a trade record to the database.
        
        Args:
            trade_data: Dictionary with trade information
            
        Returns:
            Trade object
        """
        with self.get_session() as session:
            trade = Trade(**trade_data)
            session.add(trade)
            session.flush()
            session.refresh(trade)
            return trade

    def get_trades(
        self,
        limit: int = 100,
        side: Optional[str] = None,
        exit_reason: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Trade]:
        """
        Query trades with filters.
        
        Args:
            limit: Maximum number of trades to return
            side: Filter by side (buy/sell)
            exit_reason: Filter by exit reason
            start_date: Filter trades after this date
            end_date: Filter trades before this date
            
        Returns:
            List of Trade objects (with all attributes loaded)
        """
        with self.get_session() as session:
            query = session.query(Trade)
            
            if side:
                query = query.filter(Trade.side == side)
            if exit_reason:
                query = query.filter(Trade.exit_reason == exit_reason)
            if start_date:
                query = query.filter(Trade.timestamp >= start_date)
            if end_date:
                query = query.filter(Trade.timestamp <= end_date)
            
            query = query.order_by(desc(Trade.timestamp)).limit(limit)
            trades = query.all()
            
            # Force load all attributes while session is still active
            # This prevents "detached instance" errors later
            for t in trades:
                _ = (t.id, t.timestamp, t.side, t.price, t.amount, 
                     t.notional, t.fee, t.pnl, t.exit_reason, 
                     t.usdt_balance, t.base_balance, t.signal_direction,
                     t.rsi, t.atr)
            
            # Expunge all objects from session to make them independent
            session.expunge_all()
            
            return trades

    def get_trade_stats(self) -> Dict:
        """
        Get aggregate trade statistics.
        
        Returns:
            Dictionary with statistics
        """
        with self.get_session() as session:
            total_trades = session.query(func.count(Trade.id)).scalar() or 0
            
            winning_trades = (
                session.query(func.count(Trade.id))
                .filter(Trade.pnl.isnot(None), Trade.pnl > 0)
                .scalar() or 0
            )
            
            losing_trades = (
                session.query(func.count(Trade.id))
                .filter(Trade.pnl.isnot(None), Trade.pnl < 0)
                .scalar() or 0
            )
            
            total_pnl = session.query(func.sum(Trade.pnl)).scalar() or 0.0
            avg_pnl = session.query(func.avg(Trade.pnl)).filter(Trade.pnl.isnot(None)).scalar() or 0.0
            
            win_rate = (winning_trades / (winning_trades + losing_trades) * 100) if (winning_trades + losing_trades) > 0 else 0.0
            
            return {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "total_pnl": float(total_pnl),
                "avg_pnl": float(avg_pnl),
            }

    def clear_all_trades(self) -> int:
        """
        Delete all trade records from the database.

        Returns:
            Number of trades deleted
        """
        with self.get_session() as session:
            deleted_count = session.query(Trade).delete()
            self.logger.warning(f"Cleared {deleted_count} trade records from database")
            return deleted_count

    def add_position(self, position_data: Dict) -> Position:
        """Add a position record"""
        with self.get_session() as session:
            position = Position(**position_data)
            session.add(position)
            session.flush()
            session.refresh(position)
            return position

    def update_position(self, position_id: int, updates: Dict) -> Optional[Position]:
        """Update an existing position"""
        with self.get_session() as session:
            position = session.query(Position).filter(Position.id == position_id).first()
            if position:
                for key, value in updates.items():
                    setattr(position, key, value)
                position.updated_at = datetime.utcnow()
                session.flush()
                session.refresh(position)
                return position
            return None

    def get_open_positions(self) -> List[Position]:
        """Get all currently open positions"""
        with self.get_session() as session:
            return session.query(Position).filter(Position.is_open == True).all()

    def add_candle(self, candle_data: Dict) -> Candle:
        """Add a candle record (with duplicate handling)"""
        with self.get_session() as session:
            # Check if candle already exists
            existing = (
                session.query(Candle)
                .filter(
                    Candle.symbol == candle_data["symbol"],
                    Candle.timeframe == candle_data["timeframe"],
                    Candle.timestamp == candle_data["timestamp"],
                )
                .first()
            )
            
            if existing:
                # Update existing candle
                for key, value in candle_data.items():
                    setattr(existing, key, value)
                session.flush()
                session.refresh(existing)
                return existing
            else:
                # Create new candle
                candle = Candle(**candle_data)
                session.add(candle)
                session.flush()
                session.refresh(candle)
                return candle

    def add_performance_snapshot(self, metrics_data: Dict) -> PerformanceMetrics:
        """Add a performance metrics snapshot"""
        with self.get_session() as session:
            metrics = PerformanceMetrics(**metrics_data)
            session.add(metrics)
            session.flush()
            session.refresh(metrics)
            return metrics
    
    def get_strategy_config(self, key: str) -> Optional[StrategyConfig]:
        """Get a specific strategy configuration by key"""
        with self.get_session() as session:
            config = session.query(StrategyConfig).filter(StrategyConfig.key == key).first()
            if config:
                session.expunge(config)
            return config
    
    def get_all_strategy_configs(self) -> Dict[str, any]:
        """Get all strategy configurations as a dictionary"""
        with self.get_session() as session:
            configs = session.query(StrategyConfig).all()
            result = {}
            for config in configs:
                result[config.key] = config.get_typed_value()
            return result
    
    def set_strategy_config(self, key: str, value: any, value_type: str, category: str = "general", description: str = "") -> StrategyConfig:
        """Set or update a strategy configuration"""
        with self.get_session() as session:
            config = session.query(StrategyConfig).filter(StrategyConfig.key == key).first()
            
            if config:
                # Update existing
                config.value = str(value)
                config.value_type = value_type
                config.category = category
                config.description = description
                config.updated_at = datetime.utcnow()
            else:
                # Create new
                config = StrategyConfig(
                    key=key,
                    value=str(value),
                    value_type=value_type,
                    category=category,
                    description=description
                )
                session.add(config)
            
            session.flush()
            session.refresh(config)
            session.expunge(config)
            return config
    
    def set_multiple_strategy_configs(self, configs: Dict[str, Dict]) -> int:
        """
        Set multiple strategy configurations at once.
        
        Args:
            configs: Dict with format {key: {"value": val, "type": type, "category": cat, "description": desc}}
            
        Returns:
            Number of configurations updated
        """
        count = 0
        with self.get_session() as session:
            for key, data in configs.items():
                config_obj = session.query(StrategyConfig).filter(StrategyConfig.key == key).first()
                
                if config_obj:
                    config_obj.value = str(data["value"])
                    config_obj.value_type = data["type"]
                    config_obj.category = data.get("category", "general")
                    config_obj.description = data.get("description", "")
                    config_obj.updated_at = datetime.utcnow()
                else:
                    config_obj = StrategyConfig(
                        key=key,
                        value=str(data["value"]),
                        value_type=data["type"],
                        category=data.get("category", "general"),
                        description=data.get("description", "")
                    )
                    session.add(config_obj)
                
                count += 1
            
            session.flush()
        
        return count
    
    def clear_strategy_configs(self) -> int:
        """Clear all strategy configurations"""
        with self.get_session() as session:
            deleted_count = session.query(StrategyConfig).delete()
            self.logger.warning(f"Cleared {deleted_count} strategy configuration records")
            return deleted_count
    
    # =====================================================================
    # STRATEGY PRESET METHODS
    # =====================================================================
    
    def get_preset(self, name: str) -> Optional[Dict]:
        """
        Get a strategy preset by name.
        
        Args:
            name: Preset name
            
        Returns:
            Dict with preset data or None if not found
        """
        with self.get_session() as session:
            preset = session.query(StrategyPreset).filter(StrategyPreset.name == name).first()
            if preset:
                import json
                return {
                    "id": preset.id,
                    "name": preset.name,
                    "display_name": preset.display_name,
                    "description": preset.description,
                    "config": json.loads(preset.config_json),
                    "is_builtin": preset.is_builtin,
                    "is_default": preset.is_default,
                    "category": preset.category,
                    "created_at": preset.created_at.isoformat() if preset.created_at else None,
                    "updated_at": preset.updated_at.isoformat() if preset.updated_at else None,
                }
            return None
    
    def get_all_presets(self) -> List[Dict]:
        """
        Get all strategy presets.
        
        Returns:
            List of preset dicts
        """
        with self.get_session() as session:
            presets = session.query(StrategyPreset).order_by(
                StrategyPreset.is_builtin.desc(),
                StrategyPreset.created_at.desc()
            ).all()
            
            import json
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "display_name": p.display_name,
                    "description": p.description,
                    "config": json.loads(p.config_json),
                    "is_builtin": p.is_builtin,
                    "is_default": p.is_default,
                    "category": p.category,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                }
                for p in presets
            ]
    
    def save_preset(self, name: str, display_name: str, description: str, 
                    config: Dict, category: str = "custom", is_builtin: bool = False,
                    is_default: bool = False) -> Dict:
        """
        Save or update a strategy preset.
        
        Args:
            name: Unique preset identifier (slug)
            display_name: Human-readable name
            description: Preset description
            config: Configuration dict
            category: Preset category
            is_builtin: Whether this is a built-in preset
            is_default: Whether this is the default preset
            
        Returns:
            Saved preset dict
        """
        import json
        with self.get_session() as session:
            preset = session.query(StrategyPreset).filter(StrategyPreset.name == name).first()
            
            if preset:
                # Update existing (but don't allow modifying built-in presets)
                if preset.is_builtin and not is_builtin:
                    raise ValueError("Cannot modify built-in presets")
                
                preset.display_name = display_name
                preset.description = description
                preset.config_json = json.dumps(config)
                preset.category = category
                preset.is_default = is_default
                preset.updated_at = datetime.utcnow()
            else:
                # Create new
                preset = StrategyPreset(
                    name=name,
                    display_name=display_name,
                    description=description,
                    config_json=json.dumps(config),
                    category=category,
                    is_builtin=is_builtin,
                    is_default=is_default,
                )
                session.add(preset)
            
            # If this is set as default, unset other defaults
            if is_default:
                session.query(StrategyPreset).filter(
                    StrategyPreset.name != name
                ).update({"is_default": False})
            
            session.flush()
            session.refresh(preset)
            
            return {
                "id": preset.id,
                "name": preset.name,
                "display_name": preset.display_name,
                "description": preset.description,
                "config": json.loads(preset.config_json),
                "is_builtin": preset.is_builtin,
                "is_default": preset.is_default,
                "category": preset.category,
            }
    
    def delete_preset(self, name: str) -> bool:
        """
        Delete a strategy preset.
        
        Args:
            name: Preset name
            
        Returns:
            True if deleted, False if not found or is built-in
        """
        with self.get_session() as session:
            preset = session.query(StrategyPreset).filter(StrategyPreset.name == name).first()
            if not preset:
                return False
            
            if preset.is_builtin:
                self.logger.warning(f"Cannot delete built-in preset: {name}")
                return False
            
            session.delete(preset)
            self.logger.info(f"Deleted preset: {name}")
            return True
    
    def initialize_builtin_presets(self):
        """Initialize built-in strategy presets if they don't exist"""
        builtin_presets = [
            {
                "name": "conservative",
                "display_name": "Conservative (Low Risk)",
                "description": "Lower risk settings with tight stops, high confidence threshold, and unanimous strategy agreement. Best for cautious traders.",
                "category": "conservative",
                "config": {
                    # Risk Management - Tight
                    "stop_loss_pct": 0.015,
                    "take_profit_pct": 0.03,
                    "trailing_stop_pct": 0.01,
                    "use_trailing_stop": True,
                    
                    # Position Sizing - Small
                    "order_pct": 0.15,
                    "min_position_size": 0.10,
                    "max_position_size": 0.20,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - Unanimous
                    "strategy_aggregation_mode": "unanimous",
                    "min_signal_confidence": 0.5,
                    
                    # Filters - Strict
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.3,
                    "require_macd_confirmation": False,
                    "max_trades_per_day": 3,
                    
                    # Strategy Weights
                    "strategy_ema_weight": 1.0,
                    "strategy_rsi_bb_weight": 1.0,
                    "strategy_macd_weight": 1.0,
                },
            },
            {
                "name": "balanced",
                "display_name": "Balanced (Default)",
                "description": "Balanced risk/reward with moderate stops and weighted voting. Good starting point for most traders.",
                "category": "balanced",
                "config": {
                    # Risk Management - Moderate
                    "stop_loss_pct": 0.025,
                    "take_profit_pct": 0.04,
                    "trailing_stop_pct": 0.015,
                    "use_trailing_stop": True,
                    
                    # Position Sizing - Medium
                    "order_pct": 0.25,
                    "min_position_size": 0.15,
                    "max_position_size": 0.35,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - Weighted Voting
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.3,
                    
                    # Filters - Balanced
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.1,
                    "require_macd_confirmation": False,
                    "max_trades_per_day": 5,
                    
                    # Strategy Weights
                    "strategy_ema_weight": 1.0,
                    "strategy_rsi_bb_weight": 1.0,
                    "strategy_macd_weight": 1.0,
                },
            },
            {
                "name": "aggressive",
                "display_name": "Aggressive (High Risk)",
                "description": "Higher risk with wider stops, lower confidence threshold, and 'any' strategy mode. For experienced traders comfortable with volatility.",
                "category": "aggressive",
                "config": {
                    # Risk Management - Wide
                    "stop_loss_pct": 0.04,
                    "take_profit_pct": 0.08,
                    "trailing_stop_pct": 0.025,
                    "use_trailing_stop": True,
                    
                    # Position Sizing - Large
                    "order_pct": 0.40,
                    "min_position_size": 0.25,
                    "max_position_size": 0.50,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - Any
                    "strategy_aggregation_mode": "any",
                    "min_signal_confidence": 0.2,
                    
                    # Filters - Relaxed
                    "require_volume_confirmation": False,
                    "volume_threshold": 1.0,
                    "require_macd_confirmation": False,
                    "max_trades_per_day": 10,
                    
                    # Strategy Weights
                    "strategy_ema_weight": 1.0,
                    "strategy_rsi_bb_weight": 1.0,
                    "strategy_macd_weight": 1.0,
                },
            },
            {
                "name": "scalping_5m",
                "display_name": "Scalping (5m timeframe)",
                "description": "Fast 5-minute scalping with tight stops and quick profits. Requires constant monitoring.",
                "category": "scalping",
                "config": {
                    # Trading Parameters
                    "timeframe": "5m",
                    
                    # Risk Management - Very Tight
                    "stop_loss_pct": 0.008,
                    "take_profit_pct": 0.015,
                    "trailing_stop_pct": 0.006,
                    "use_trailing_stop": True,
                    
                    # Position Sizing
                    "order_pct": 0.20,
                    "min_position_size": 0.15,
                    "max_position_size": 0.30,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy
                    "strategy_aggregation_mode": "best",
                    "min_signal_confidence": 0.4,
                    
                    # Filters
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.5,
                    "max_trades_per_day": 15,
                    
                    # EMA - Faster
                    "short_window": 8,
                    "long_window": 21,
                    "min_trend_strength": 0.0001,
                },
            },
            {
                "name": "swing_4h",
                "display_name": "Swing Trading (4h timeframe)",
                "description": "Longer-term swing trading on 4-hour candles with wider stops and bigger targets. Lower frequency, less monitoring needed.",
                "category": "swing",
                "config": {
                    # Trading Parameters
                    "timeframe": "4h",
                    
                    # Risk Management - Wide
                    "stop_loss_pct": 0.05,
                    "take_profit_pct": 0.12,
                    "trailing_stop_pct": 0.03,
                    "use_trailing_stop": True,
                    
                    # Position Sizing
                    "order_pct": 0.35,
                    "min_position_size": 0.20,
                    "max_position_size": 0.45,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.35,
                    
                    # Filters
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.2,
                    "max_trades_per_day": 3,
                    
                    # EMA - Slower
                    "short_window": 21,
                    "long_window": 55,
                    "min_trend_strength": 0.00003,
                },
            },
            {
                "name": "day_trading_1h",
                "display_name": "Day Trading (1h timeframe)",
                "description": "Balanced day trading on 1-hour candles. Perfect middle ground between scalping and swing trading. Check 2-3 times per day.",
                "category": "day_trading",
                "config": {
                    # Trading Parameters
                    "timeframe": "1h",
                    
                    # Risk Management
                    "stop_loss_pct": 0.02,
                    "take_profit_pct": 0.05,
                    "trailing_stop_pct": 0.015,
                    "use_trailing_stop": True,
                    
                    # Position Sizing
                    "order_pct": 0.30,
                    "min_position_size": 0.20,
                    "max_position_size": 0.40,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.35,
                    
                    # Filters
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.2,
                    "max_trades_per_day": 8,
                    
                    # EMA
                    "short_window": 12,
                    "long_window": 26,
                    "min_trend_strength": 0.00005,
                },
            },
            {
                "name": "trend_following",
                "display_name": "Trend Following (EMA Focus)",
                "description": "Prioritizes EMA crossover strategy for catching and riding strong trends. Higher EMA weight, requires clear directional moves.",
                "category": "specialized",
                "config": {
                    # Risk Management
                    "stop_loss_pct": 0.03,
                    "take_profit_pct": 0.08,
                    "trailing_stop_pct": 0.02,
                    "use_trailing_stop": True,
                    
                    # Position Sizing
                    "order_pct": 0.30,
                    "min_position_size": 0.20,
                    "max_position_size": 0.40,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - EMA focused
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.4,
                    "strategy_ema_weight": 2.0,  # Double weight for EMA
                    "strategy_rsi_bb_weight": 0.5,  # Lower weight
                    "strategy_macd_weight": 1.0,
                    
                    # Filters
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.2,
                    "max_trades_per_day": 5,
                    
                    # EMA - Longer for stronger trends
                    "short_window": 15,
                    "long_window": 35,
                    "min_trend_strength": 0.0001,  # Higher threshold
                },
            },
            {
                "name": "mean_reversion",
                "display_name": "Mean Reversion (RSI+BB Focus)",
                "description": "Focuses on RSI+Bollinger Bands for counter-trend entries. Buys oversold, sells overbought. Best in ranging markets.",
                "category": "specialized",
                "config": {
                    # Risk Management - Tight stops for mean reversion
                    "stop_loss_pct": 0.018,
                    "take_profit_pct": 0.035,
                    "trailing_stop_pct": 0.012,
                    "use_trailing_stop": True,
                    
                    # Position Sizing
                    "order_pct": 0.25,
                    "min_position_size": 0.15,
                    "max_position_size": 0.35,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - RSI+BB focused
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.4,
                    "strategy_ema_weight": 0.5,  # Lower weight
                    "strategy_rsi_bb_weight": 2.0,  # Double weight for mean reversion
                    "strategy_macd_weight": 0.8,
                    
                    # Filters
                    "require_volume_confirmation": False,  # Less important for mean reversion
                    "volume_threshold": 1.0,
                    "max_trades_per_day": 6,
                    
                    # RSI+BB - More sensitive
                    "strategy_rsi_bb_rsi_oversold": 25,
                    "strategy_rsi_bb_rsi_overbought": 75,
                    "strategy_rsi_bb_bb_period": 20,
                    "strategy_rsi_bb_bb_std_dev": 2.0,
                },
            },
            {
                "name": "breakout_hunter",
                "display_name": "Breakout Hunter (MACD+Volume Focus)",
                "description": "Optimized for catching momentum breakouts with volume confirmation. Prioritizes MACD+Volume strategy for explosive moves.",
                "category": "specialized",
                "config": {
                    # Risk Management - Wider stops for breakouts
                    "stop_loss_pct": 0.035,
                    "take_profit_pct": 0.09,
                    "trailing_stop_pct": 0.025,
                    "use_trailing_stop": True,
                    
                    # Position Sizing - Larger for confirmed breakouts
                    "order_pct": 0.35,
                    "min_position_size": 0.25,
                    "max_position_size": 0.45,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - MACD+Volume focused
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.35,
                    "strategy_ema_weight": 0.8,
                    "strategy_rsi_bb_weight": 0.5,
                    "strategy_macd_weight": 2.0,  # Double weight for breakouts
                    
                    # Filters - Strong volume required
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.5,  # 50% above average
                    "max_trades_per_day": 6,
                    
                    # MACD - More sensitive
                    "strategy_macd_fast_period": 10,
                    "strategy_macd_slow_period": 22,
                    "strategy_macd_signal_period": 8,
                    "strategy_macd_volume_multiplier": 1.5,
                    "strategy_macd_require_zero_cross": False,
                },
            },
            {
                "name": "night_mode",
                "display_name": "Night Mode (Unmonitored)",
                "description": "Ultra-conservative for overnight or when you can't monitor. Tight stops, small positions, requires all strategies to agree.",
                "category": "conservative",
                "config": {
                    # Risk Management - Very tight
                    "stop_loss_pct": 0.012,
                    "take_profit_pct": 0.025,
                    "trailing_stop_pct": 0.008,
                    "use_trailing_stop": True,
                    
                    # Position Sizing - Very small
                    "order_pct": 0.12,
                    "min_position_size": 0.08,
                    "max_position_size": 0.15,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - Unanimous only
                    "strategy_aggregation_mode": "unanimous",
                    "min_signal_confidence": 0.6,  # Very high confidence
                    
                    # Filters - Very strict
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.4,
                    "max_trades_per_day": 2,
                    
                    # Strategy Weights
                    "strategy_ema_weight": 1.0,
                    "strategy_rsi_bb_weight": 1.0,
                    "strategy_macd_weight": 1.0,
                },
            },
            {
                "name": "high_volatility",
                "display_name": "High Volatility Market",
                "description": "Adapted for volatile markets with wider stops and larger ATR multipliers. Prevents premature stop-outs during big swings.",
                "category": "market_condition",
                "config": {
                    # Risk Management - Wide for volatility
                    "stop_loss_pct": 0.045,
                    "take_profit_pct": 0.10,
                    "trailing_stop_pct": 0.03,
                    "use_trailing_stop": True,
                    
                    # ATR - Wider stops
                    "atr_stop_multiplier": 3.5,
                    "use_atr_stops": True,
                    
                    # Position Sizing - Smaller due to risk
                    "order_pct": 0.20,
                    "min_position_size": 0.12,
                    "max_position_size": 0.28,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.45,  # Higher confidence in volatile markets
                    
                    # Filters - Stricter
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.3,
                    "max_trades_per_day": 4,
                },
            },
            {
                "name": "low_volatility",
                "display_name": "Low Volatility Market",
                "description": "Optimized for stable, low-volatility conditions. Tighter stops, more frequent trades, smaller targets.",
                "category": "market_condition",
                "config": {
                    # Risk Management - Tight for low volatility
                    "stop_loss_pct": 0.015,
                    "take_profit_pct": 0.03,
                    "trailing_stop_pct": 0.01,
                    "use_trailing_stop": True,
                    
                    # ATR - Tighter stops
                    "atr_stop_multiplier": 1.8,
                    "use_atr_stops": True,
                    
                    # Position Sizing - Larger positions, lower risk
                    "order_pct": 0.35,
                    "min_position_size": 0.25,
                    "max_position_size": 0.45,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.25,  # Lower confidence ok in stable markets
                    
                    # Filters - Relaxed
                    "require_volume_confirmation": False,
                    "volume_threshold": 1.0,
                    "max_trades_per_day": 8,
                },
            },
            {
                "name": "crypto_bull",
                "display_name": "Crypto Bull Market",
                "description": "Optimized for strong uptrends. Favors long positions, wider take profits, aggressive position sizing. Ride the bull!",
                "category": "market_condition",
                "config": {
                    # Risk Management - Let profits run
                    "stop_loss_pct": 0.028,
                    "take_profit_pct": 0.15,  # Large target
                    "trailing_stop_pct": 0.035,  # Wider trailing
                    "use_trailing_stop": True,
                    
                    # Position Sizing - Aggressive in bull
                    "order_pct": 0.40,
                    "min_position_size": 0.30,
                    "max_position_size": 0.50,
                    "use_dynamic_sizing": True,
                    
                    # Multi-Strategy - Trend following bias
                    "strategy_aggregation_mode": "weighted_voting",
                    "min_signal_confidence": 0.3,
                    "strategy_ema_weight": 1.5,  # Higher weight for trends
                    "strategy_rsi_bb_weight": 0.7,  # Lower mean reversion
                    "strategy_macd_weight": 1.3,
                    
                    # Filters
                    "require_volume_confirmation": True,
                    "volume_threshold": 1.2,
                    "max_trades_per_day": 6,
                    
                    # EMA - Faster to catch uptrends
                    "short_window": 9,
                    "long_window": 21,
                },
            },
        ]
        
        for preset_data in builtin_presets:
            try:
                self.save_preset(
                    name=preset_data["name"],
                    display_name=preset_data["display_name"],
                    description=preset_data["description"],
                    config=preset_data["config"],
                    category=preset_data["category"],
                    is_builtin=True,
                    is_default=(preset_data["name"] == "balanced"),
                )
                self.logger.info(f"Initialized built-in preset: {preset_data['name']}")
            except Exception as e:
                self.logger.warning(f"Failed to initialize preset {preset_data['name']}: {e}")


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def initialize_database(database_url: str = "sqlite:///data/trading.db") -> DatabaseManager:
    """
    Initialize the global database manager.
    
    Args:
        database_url: SQLAlchemy database URL
        
    Returns:
        DatabaseManager instance
    """
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    _db_manager.create_tables()
    return _db_manager


def get_database() -> DatabaseManager:
    """
    Get the global database manager instance.
    
    Returns:
        DatabaseManager instance
        
    Raises:
        RuntimeError: If database not initialized
    """
    if _db_manager is None:
        raise RuntimeError("Database not initialized. Call initialize_database() first.")
    return _db_manager










