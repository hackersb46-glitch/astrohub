"""
Database Service v1.0 - 数据库迁移

数据库 schema 版本管理、正向迁移、回滚、迁移记录。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core.db_manager import MigrationVersion


# ------------------------------------------------------------------ #
#  迁移脚本定义
# ------------------------------------------------------------------ #

MIGRATIONS: list[dict[str, Any]] = [
    {
        "version": "001",
        "description": "初始化核心表：devices, device_status_history, config_snapshots, observations, groups, operation_logs, migration_versions",
    },
]


class MigrationManager:
    """数据库迁移管理器：版本追踪/正向迁移/回滚。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化迁移管理器。

        Args:
            session: SQLAlchemy 异步会话
        """
        self._session = session

    async def get_current_version(self) -> str | None:
        """获取当前数据库版本。

        Returns:
            当前版本号，无记录返回 None
        """
        stmt = (
            select(MigrationVersion.version)
            .order_by(MigrationVersion.applied_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_versions(self) -> list[MigrationVersion]:
        """获取所有已应用的迁移版本。

        Returns:
            迁移版本列表
        """
        stmt = select(MigrationVersion).order_by(MigrationVersion.applied_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def migrate(self) -> list[str]:
        """执行正向迁移。

        Returns:
            已应用的版本列表
        """
        current = await self.get_current_version()
        applied = []

        for migration in MIGRATIONS:
            version = migration["version"]
            # 如果当前版本 >= 此迁移版本，跳过
            if current and version <= current:
                continue

            # 记录版本
            record = MigrationVersion(
                version=version,
                description=migration["description"],
                applied_at=datetime.utcnow(),
            )
            self._session.add(record)
            applied.append(version)

        if applied:
            await self._session.flush()
        return applied

    async def rollback(self) -> bool:
        """回滚到上一个版本。

        Returns:
            是否成功回滚
        """
        current = await self.get_current_version()
        if current is None:
            return False

        # 删除当前版本记录
        stmt = select(MigrationVersion).where(
            MigrationVersion.version == current
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        if record:
            await self._session.delete(record)
            await self._session.flush()
            return True
        return False

    async def mark_version(self, version: str, description: str = "") -> bool:
        """手动标记版本(用于外部迁移工具如 Alembic)。

        Args:
            version: 版本号
            description: 版本描述

        Returns:
            是否标记成功
        """
        existing = await self._find_version(version)
        if existing:
            return False  # 版本已存在

        record = MigrationVersion(
            version=version,
            description=description,
            applied_at=datetime.utcnow(),
        )
        self._session.add(record)
        await self._session.flush()
        return True

    async def _find_version(self, version: str) -> MigrationVersion | None:
        """查找指定版本记录。"""
        stmt = select(MigrationVersion).where(
            MigrationVersion.version == version
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
