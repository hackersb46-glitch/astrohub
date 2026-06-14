"""
Database Service v1.0 - SQLAlchemy 异步连接/连接池/表结构

管理异步数据库引擎、会话工厂、Base Model 定义及表初始化。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncGenerator

from sqlalchemy import Column, DateTime, Integer, String, Text, Float, BigInteger, Index, ForeignKey, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.database.constants import (
    DATABASE_URL,
    POOL_SIZE,
    MAX_OVERFLOW,
    POOL_TIMEOUT,
    POOL_RECYCLE,
)


# ------------------------------------------------------------------ #
#  引擎与会话工厂
# ------------------------------------------------------------------ #

class DatabaseManager:
    """异步数据库管理器：引擎创建/连接池/会话管理。"""

    _engine: AsyncEngine | None = None
    _session_factory: async_sessionmaker[AsyncSession] | None = None

    @classmethod
    def get_engine(cls, db_url: str | None = None) -> AsyncEngine:
        """获取异步数据库引擎（单例模式）。

        Args:
            db_url: 可选的自定义数据库连接字符串，默认使用 constants.DATABASE_URL

        Returns:
            SQLAlchemy AsyncEngine 实例
        """
        if cls._engine is None:
            url = db_url if db_url else DATABASE_URL
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
        """获取异步会话工厂。

        Returns:
            AsyncSession 工厂
        """
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
        """获取异步会话（用于 FastAPI Dependency Injection）。

        Yields:
            AsyncSession 实例
        """
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

    @classmethod
    async def reset(cls) -> None:
        """重置连接池（用于测试）。"""
        await cls.close()


# ------------------------------------------------------------------ #
#  Base Model
# ------------------------------------------------------------------ #

class Base(DeclarativeBase):
    """ORM 基类。"""
    pass


# ------------------------------------------------------------------ #
#  表定义
# ------------------------------------------------------------------ #

class Device(Base):
    """设备信息表 (P1)。"""
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
        """转换为字典。"""
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


class DeviceStatusHistory(Base):
    """设备状态变更历史表 (P1.5)。"""
    __tablename__ = "device_status_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mac = Column(String(17), nullable=False, index=True)
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_status_history_mac_time", "mac", "changed_at"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mac": self.mac,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
        }


class ConfigSnapshot(Base):
    """设备配置快照表 (P1.6)。"""
    __tablename__ = "config_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mac = Column(String(17), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    config_data = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_config_snapshots_mac_version", "mac", "version", unique=True),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mac": self.mac,
            "version": self.version,
            "config_data": self.config_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Observation(Base):
    """观测记录表 (P2)。"""
    __tablename__ = "observations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    mac = Column(String(17), nullable=False, index=True)
    observation_time = Column(DateTime, nullable=False, index=True)
    ra = Column(Float, nullable=True)  # 赤经
    dec = Column(Float, nullable=True)  # 赤纬
    parameters = Column(Text, nullable=True)  # JSON 格式观测参数
    data_type = Column(String(30), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_observations_mac_time", "mac", "observation_time"),
        Index("ix_observations_type_time", "data_type", "observation_time"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mac": self.mac,
            "observation_time": self.observation_time.isoformat() if self.observation_time else None,
            "ra": self.ra,
            "dec": self.dec,
            "parameters": self.parameters,
            "data_type": self.data_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Group(Base):
    """设备分组表 (P3)。"""
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OperationLog(Base):
    """操作日志表 (P4)。"""
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


class MigrationVersion(Base):
    """数据库迁移版本表 (P0.3)。"""
    __tablename__ = "migration_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ------------------------------------------------------------------ #
#  表初始化
# ------------------------------------------------------------------ #

async def init_db(db_url: str | None = None) -> None:
    """创建所有数据表（幂等执行）。

    Args:
        db_url: 可选的数据库连接字符串
    """
    engine = DatabaseManager.get_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
