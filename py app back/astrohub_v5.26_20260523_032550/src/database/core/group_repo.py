"""
Database Service v1.0 - 分组管理

设备分组 CRUD、分组设备关联。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.core.db_manager import Group, Device
from src.database.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


class GroupRepository:
    """分组数据仓库：分组 CRUD、分组设备管理。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化分组仓库。

        Args:
            session: SQLAlchemy 异步会话
        """
        self._session = session

    # === 分组 CRUD ===

    async def create_group(self, name: str, description: str | None = None) -> Group:
        """创建分组。

        Args:
            name: 分组名称
            description: 分组描述

        Returns:
            创建的 Group 实例

        Raises:
            ValueError: 分组名称已存在
        """
        existing = await self.get_group_by_name(name)
        if existing:
            raise ValueError(f"分组已存在: {name}")

        group = Group(name=name, description=description)
        self._session.add(group)
        await self._session.flush()
        return group

    async def get_group_by_name(self, name: str) -> Group | None:
        """按名称查询分组。

        Args:
            name: 分组名称

        Returns:
            Group 实例或 None
        """
        stmt = select(Group).where(Group.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_group_by_id(self, group_id: int) -> Group | None:
        """按 ID 查询分组。

        Args:
            group_id: 分组 ID

        Returns:
            Group 实例或 None
        """
        return await self._session.get(Group, group_id)

    async def list_groups(
        self, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE
    ) -> tuple[Sequence[Group], int]:
        """分页查询分组列表。

        Args:
            page: 页码(从1开始)
            page_size: 每页条数

        Returns:
            (分组列表, 总数)
        """
        # 计数
        count_stmt = select(func.count(Group.id))
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 分页
        size = min(max(page_size, 1), MAX_PAGE_SIZE)
        offset = (max(page, 1) - 1) * size
        stmt = select(Group).order_by(Group.created_at.desc()).offset(offset).limit(size)
        result = await self._session.execute(stmt)
        groups = result.scalars().all()
        return groups, total

    async def update_group(
        self, group_id: int, name: str | None = None, description: str | None = None
    ) -> Group:
        """更新分组信息。

        Args:
            group_id: 分组 ID
            name: 新分组名称
            description: 新描述

        Returns:
            更新后的 Group 实例

        Raises:
            RuntimeError: 分组不存在
            ValueError: 分组名称已存在
        """
        group = await self.get_group_by_id(group_id)
        if group is None:
            raise RuntimeError(f"分组不存在: {group_id}")

        if name is not None and name != group.name:
            existing = await self.get_group_by_name(name)
            if existing:
                raise ValueError(f"分组名称已存在: {name}")
            group.name = name

        if description is not None:
            group.description = description

        await self._session.flush()
        return group

    async def delete_group(self, group_id: int) -> bool:
        """删除分组(不删除关联设备)。

        Args:
            group_id: 分组 ID

        Returns:
            是否删除成功
        """
        group = await self.get_group_by_id(group_id)
        if group is None:
            return False

        # 将关联设备的 group_id 设为 NULL
        stmt = select(Device).where(Device.group_id == group_id)
        result = await self._session.execute(stmt)
        devices = result.scalars().all()
        for device in devices:
            device.group_id = None

        await self._session.delete(group)
        await self._session.flush()
        return True

    # === 分组设备管理 ===

    async def get_group_devices(self, group_id: int) -> Sequence[Device]:
        """获取分组下的所有设备。

        Args:
            group_id: 分组 ID

        Returns:
            设备列表
        """
        stmt = select(Device).where(Device.group_id == group_id).order_by(Device.mac)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add_device_to_group(self, mac: str, group_id: int) -> Device:
        """将设备添加到分组。

        Args:
            mac: 设备 MAC 地址
            group_id: 分组 ID

        Returns:
            更新后的 Device 实例
        """
        stmt = select(Device).where(Device.mac == mac)
        result = await self._session.execute(stmt)
        device = result.scalar_one_or_none()
        if device is None:
            raise RuntimeError(f"设备不存在: {mac}")

        device.group_id = group_id
        await self._session.flush()
        return device

    async def remove_device_from_group(self, mac: str) -> Device:
        """将设备从分组中移除。

        Args:
            mac: 设备 MAC 地址

        Returns:
            更新后的 Device 实例
        """
        stmt = select(Device).where(Device.mac == mac)
        result = await self._session.execute(stmt)
        device = result.scalar_one_or_none()
        if device is None:
            raise RuntimeError(f"设备不存在: {mac}")

        device.group_id = None
        await self._session.flush()
        return device
