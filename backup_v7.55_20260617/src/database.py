"""
AstroHub v2.0 - 统一数据库层

复用 M5 的 SQLAlchemy async engine，统一 Base，表模型。
"""

from __future__ import annotations

import warnings
warnings.warn(
    "src/database.py is deprecated. Use 'src/database/core/db_manager.py' instead. "
    "Will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

from datetime import datetime
from typing import Any, AsyncGenerator

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import (
    DATABASE_URL,
    MAX_OVERFLOW,
    POOL_RECYCLE,
    POOL_SIZE,
    POOL_TIMEOUT,
)


# ------------------------------------------------------------------ #
#  引擎与会话工厂
# ------------------------------------------------------------------ #


class DatabaseManager:
    """异步数据库管理器（单例）。"""

    _engine: AsyncEngine | None = None
    _session_factory: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def get_engine(cls, db_url: str | None = None) -> AsyncEngine:
        """获取异步数据库引擎（单例模式）。"""
        if cls._engine is None:
            url = db_url or DATABASE_URL
            cls._engine = create_async_engine(
                url,
                echo=False,
                pool_size=POOL_SIZE,
                max_overflow=MAX_OVERFLOW,
                pool_timeout=POOL_TIMEOUT,
                pool_recycle=POOL_RECYCLE,
                pool_pre_ping=True,
            )
        return cls._engine

    @classmethod
    def get_session_factory(cls, db_url: str | None = None) -> async_sessionmaker[AsyncSession]:
        """获取异步会话工厂。"""
        if cls._session_factory is None:
            engine = cls.get_engine(db_url)
            cls._session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return cls._session_factory

    @classmethod
    async def get_session(cls, db_url: str | None = None) -> AsyncGenerator[AsyncSession, None]:
        """获取异步会话（FastAPI Dependency Injection）。"""
        factory = cls.get_session_factory(db_url)
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @classmethod
    async def close(cls) -> None:
        """关闭数据库引擎。"""
        if cls._engine is not None:
            await cls._engine.dispose()
            cls._engine = None
            cls._session_factory = None


# ------------------------------------------------------------------ #
#  Base Model
# ------------------------------------------------------------------ #


class Base(DeclarativeBase):
    """ORM 基类。"""
    pass


# ------------------------------------------------------------------ #
#  表模型
# ------------------------------------------------------------------ #


class Device(Base):
    """设备信息表。"""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mac = Column(String(17), unique=True, nullable=False, index=True)
    ip = Column(String(45), nullable=False)
    model = Column(String(100), nullable=True)
    username = Column(String(100), nullable=True)
    port = Column(Integer, default=80)
    status = Column(String(20), default="new", index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_devices_mac_status", "mac", "status"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mac": self.mac,
            "ip": self.ip,
            "model": self.model,
            "username": self.username,
            "port": self.port,
            "status": self.status,
            "group_id": self.group_id,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class CalibrationRecord(Base):
    """校准记录表。"""
    __tablename__ = "calibration_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    mac = Column(String(17), nullable=False, index=True)
    calibration_type = Column(String(50), nullable=False, index=True)  # focus/color/speed/position
    parameters = Column(Text, nullable=True)  # JSON 格式校准参数
    result = Column(String(20), nullable=False, default="pending")  # pending/success/failed
    operator = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_calibration_mac_type", "mac", "calibration_type"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mac": self.mac,
            "calibration_type": self.calibration_type,
            "parameters": self.parameters,
            "result": self.result,
            "operator": self.operator,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OperationLog(Base):
    """操作日志表。"""
    __tablename__ = "operation_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    operation = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, index=True)
    details = Column(Text, nullable=True)
    operator = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_operation_logs_type_time", "target_type", "created_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "operation": self.operation,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "status": self.status,
            "details": self.details,
            "operator": self.operator,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ConfigEntry(Base):
    """配置项表（键值对存储）。"""
    __tablename__ = "config_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(200), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    section = Column(String(100), nullable=True, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "section": self.section,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ------------------------------------------------------------------ #
#  表初始化
# ------------------------------------------------------------------ #


async def init_db(db_url: str | None = None) -> None:
    """创建所有数据表（幂等执行）。"""
    engine = DatabaseManager.get_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
