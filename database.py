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
            List of Trade objects
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
            return query.all()

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





