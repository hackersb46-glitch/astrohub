"""
Database Service v1.0 - 配置版本管理

设备配置版本控制、快照查询、版本对比、回滚支持。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.constants import CONFIG_VERSION_MAX_COUNT
from src.database.core.db_manager import ConfigSnapshot
from src.database.core.device_repo import normalize_mac


class ConfigStore:
    """配置版本管理：配置快照存储/版本查询/版本对比/回滚。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化配置存储。

        Args:
            session: SQLAlchemy 异步会话
        """
        self._session = session

    # === 版本查询 ===

    async def get_config_history(
        self,
        mac: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[ConfigSnapshot], int]:
        """分页获取设备配置历史。

        Args:
            mac: 设备 MAC 地址
            page: 页码(从1开始)
            page_size: 每页条数

        Returns:
            (快照列表, 总数)
        """
        mac = normalize_mac(mac)

        # 计数
        count_stmt = select(func.count(ConfigSnapshot.id)).where(
            ConfigSnapshot.mac == mac
        )
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 分页
        offset = (max(page, 1) - 1) * page_size
        stmt = (
            select(ConfigSnapshot)
            .where(ConfigSnapshot.mac == mac)
            .order_by(ConfigSnapshot.version.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        snapshots = result.scalars().all()
        return snapshots, total

    async def get_all_versions(self, mac: str) -> list[int]:
        """获取设备所有配置版本号。

        Args:
            mac: 设备 MAC 地址

        Returns:
            版本号列表(降序)
        """
        mac = normalize_mac(mac)
        stmt = (
            select(ConfigSnapshot.version)
            .where(ConfigSnapshot.mac == mac)
            .order_by(ConfigSnapshot.version.desc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # === 版本对比 ===

    async def compare_versions(
        self, mac: str, version_a: int, version_b: int | None = None
    ) -> dict[str, Any]:
        """对比两个版本之间的差异。

        Args:
            mac: 设备 MAC 地址
            version_a: 基准版本号
            version_b: 对比版本号(None 对比最新版本)

        Returns:
            差异字典: {"version_a": [...], "version_b": [...], "diff": {"added": [...], "removed": [...], "changed": [...]}}
        """
        mac = normalize_mac(mac)

        # 获取版本 A
        stmt_a = select(ConfigSnapshot).where(
            ConfigSnapshot.mac == mac,
            ConfigSnapshot.version == version_a,
        )
        result_a = await self._session.execute(stmt_a)
        snap_a = result_a.scalar_one_or_none()
        if snap_a is None:
            raise ValueError(f"版本 {version_a} 不存在")

        # 获取版本 B
        if version_b is None:
            stmt_b = (
                select(ConfigSnapshot)
                .where(ConfigSnapshot.mac == mac)
                .order_by(ConfigSnapshot.version.desc())
                .limit(1)
            )
        else:
            stmt_b = select(ConfigSnapshot).where(
                ConfigSnapshot.mac == mac,
                ConfigSnapshot.version == version_b,
            )
        result_b = await self._session.execute(stmt_b)
        snap_b = result_b.scalar_one_or_none()
        if snap_b is None:
            raise ValueError(f"版本 {'最新' if version_b is None else version_b} 不存在")

        data_a = json.loads(snap_a.config_data)
        data_b = json.loads(snap_b.config_data)

        return self._diff_config(data_a, data_b)

    def _diff_config(
        self, config_a: dict[str, Any], config_b: dict[str, Any]
    ) -> dict[str, Any]:
        """递归对比两个配置字典。

        Args:
            config_a: 基准配置
            config_b: 目标配置

        Returns:
            差异结果
        """
        added = []
        removed = []
        changed = []

        all_keys = set(config_a.keys()) | set(config_b.keys())
        for key in sorted(all_keys):
            if key not in config_a:
                added.append(key)
            elif key not in config_b:
                removed.append(key)
            elif config_a[key] != config_b[key]:
                changed.append(key)

        return {
            "version_a_keys": list(config_a.keys()),
            "version_b_keys": list(config_b.keys()),
            "diff": {
                "added": added,
                "removed": removed,
                "changed": changed,
            },
        }

    # === 删除旧版本 ===

    async def cleanup_versions(self, mac: str, max_count: int = CONFIG_VERSION_MAX_COUNT) -> int:
        """清理多余的旧版配置快照。

        Args:
            mac: 设备 MAC 地址
            max_count: 最大保留版本数

        Returns:
            删除的记录数
        """
        mac = normalize_mac(mac)
        stmt = (
            select(ConfigSnapshot)
            .where(ConfigSnapshot.mac == mac)
            .order_by(ConfigSnapshot.version.desc())
            .offset(max_count)
        )
        result = await self._session.execute(stmt)
        old_snapshots = result.scalars().all()

        if old_snapshots:
            for snap in old_snapshots:
                await self._session.delete(snap)
            await self._session.flush()

        return len(old_snapshots)

    async def delete_version(self, mac: str, version: int) -> bool:
        """删除指定配置版本。

        Args:
            mac: 设备 MAC 地址
            version: 要删除的版本号

        Returns:
            是否成功删除
        """
        mac = normalize_mac(mac)
        stmt = select(ConfigSnapshot).where(
            ConfigSnapshot.mac == mac,
            ConfigSnapshot.version == version,
        )
        result = await self._session.execute(stmt)
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return False

        await self._session.delete(snapshot)
        await self._session.flush()
        return True
