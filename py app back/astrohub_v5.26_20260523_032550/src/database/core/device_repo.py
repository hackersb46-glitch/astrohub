"""
Database Service v1.0 - 设备 CRUD 操作

实现设备信息写入/读取/更新/删除(P1)、状态记录(P1.5)、配置快照(P1.6)。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.database.constants import (
    DeviceStatus,
    MAC_PATTERN,
    CONFIG_VERSION_MAX_COUNT,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from src.database.core.db_manager import (
    Device,
    ConfigSnapshot,
    DeviceStatusHistory,
)


# ------------------------------------------------------------------ #
#  MAC 工具
# ------------------------------------------------------------------ #

def normalize_mac(mac: str) -> str:
    """标准化 MAC 地址格式为 XX:XX:XX:XX:XX:XX。

    Args:
        mac: 原始 MAC 地址字符串

    Returns:
        标准化后的 MAC 地址

    Raises:
        ValueError: MAC 格式无效
    """
    mac = mac.strip().upper()
    if not re.match(MAC_PATTERN, mac):
        raise ValueError(f"无效的 MAC 地址格式: {mac}")
    if "-" in mac:
        return mac.replace("-", ":")
    if len(mac) == 12:
        return ":".join(mac[i:i+2] for i in range(0, 12, 2))
    return mac


# ------------------------------------------------------------------ #
#  Device Repository
# ------------------------------------------------------------------ #

class DeviceRepository:
    """设备数据仓库：设备 CRUD、状态历史、配置快照。"""

    def __init__(self, session: AsyncSession) -> None:
        """初始化数据仓库。

        Args:
            session: SQLAlchemy 异步会话
        """
        self._session = session

    # === 写入 (P1.1) ===

    async def create_device(self, data: dict[str, Any]) -> Device:
        """创建设备记录。

        Args:
            data: 设备数据字典，必须包含 mac, ip

        Returns:
            创建的 Device 实例

        Raises:
            ValueError: 缺少必填字段或 MAC 格式无效
            RuntimeError: 设备已存在
        """
        mac = data.get("mac", "").strip()
        ip = data.get("ip", "").strip()
        if not mac or not ip:
            raise ValueError("mac 和 ip 为必填字段")

        mac = normalize_mac(mac)
        existing = await self._session.get(Device, None)
        stmt = select(Device).where(Device.mac == mac)
        result = await self._session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise RuntimeError(f"设备已存在: {mac}")

        device = Device(
            mac=mac,
            ip=ip,
            model=data.get("model"),
            username=data.get("username"),
            port=data.get("port", 80),
            status=data.get("status", DeviceStatus.NEW.value),
            group_id=data.get("group_id"),
            notes=data.get("notes"),
        )
        self._session.add(device)
        await self._session.flush()
        await self._record_status_change(mac, None, device.status)
        return device

    # === 读取 (P1.2) ===

    async def get_device_by_mac(self, mac: str) -> Device | None:
        """按 MAC 精确查询设备。

        Args:
            mac: 设备 MAC 地址

        Returns:
            Device 实例或 None
        """
        mac = normalize_mac(mac)
        stmt = select(Device).where(Device.mac == mac)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_devices(
        self,
        status: str | None = None,
        group_id: int | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[Sequence[Device], int]:
        """分页查询设备列表。

        Args:
            status: 按状态筛选
            group_id: 按分组筛选
            search: 模糊搜索 (MAC/IP/Model)
            page: 页码(从1开始)
            page_size: 每页条数

        Returns:
            (设备列表, 总数)
        """
        stmt_filter: list = []
        if status:
            stmt_filter.append(Device.status == status)
        if group_id is not None:
            stmt_filter.append(Device.group_id == group_id)
        if search:
            from sqlalchemy import or_
            pattern = f"%{search}%"
            stmt_filter.append(
                or_(
                    Device.mac.ilike(pattern),
                    Device.ip.ilike(pattern),
                    Device.model.ilike(pattern),
                )
            )

        # 计数
        count_stmt = select(func.count(Device.id))
        if stmt_filter:
            count_stmt = count_stmt.where(*stmt_filter)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 分页
        size = min(max(page_size, 1), MAX_PAGE_SIZE)
        offset = (max(page, 1) - 1) * size
        stmt = select(Device)
        if stmt_filter:
            stmt = stmt.where(*stmt_filter)
        stmt = stmt.order_by(Device.created_at.desc()).offset(offset).limit(size)
        result = await self._session.execute(stmt)
        devices = result.scalars().all()
        return devices, total

    # === 更新 (P1.3) ===

    async def update_device(self, mac: str, data: dict[str, Any]) -> Device:
        """更新设备信息(以 MAC 为键)。

        Args:
            mac: 设备 MAC 地址
            data: 要更新的字段

        Returns:
            更新后的 Device 实例

        Raises:
            RuntimeError: 设备不存在
        """
        mac = normalize_mac(mac)
        stmt = select(Device).where(Device.mac == mac)
        result = await self._session.execute(stmt)
        device = result.scalar_one_or_none()
        if device is None:
            raise RuntimeError(f"设备不存在: {mac}")

        old_status = device.status
        old_values = device.to_dict()

        updatable = {"ip", "model", "username", "port", "status",
                     "group_id", "notes"}
        for key, value in data.items():
            if key in updatable:
                setattr(device, key, value)

        await self._session.flush()

        # 记录状态变更
        if old_status != device.status:
            await self._record_status_change(mac, old_status, device.status)

        return device

    # === 删除 (P1.4) ===

    async def delete_device(self, mac: str) -> bool:
        """删除设备记录(级联删除关联数据)。

        Args:
            mac: 设备 MAC 地址

        Returns:
            是否成功删除

        Raises:
            RuntimeError: 设备不存在
        """
        mac = normalize_mac(mac)
        device = await self.get_device_by_mac(mac)
        if device is None:
            raise RuntimeError(f"设备不存在: {mac}")

        # 删除关联数据
        await self._session.execute(
            delete(DeviceStatusHistory).where(DeviceStatusHistory.mac == mac)
        )
        await self._session.execute(
            delete(ConfigSnapshot).where(ConfigSnapshot.mac == mac)
        )

        await self._session.delete(device)
        await self._session.flush()
        return True

    # === 状态记录 (P1.5) ===

    async def _record_status_change(
        self, mac: str, old_status: str | None, new_status: str
    ) -> DeviceStatusHistory:
        """记录设备状态变更历史。"""
        history = DeviceStatusHistory(
            mac=mac,
            old_status=old_status,
            new_status=new_status,
        )
        self._session.add(history)
        await self._session.flush()
        return history

    async def get_status_history(
        self,
        mac: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> Sequence[DeviceStatusHistory]:
        """查询设备状态变更历史。

        Args:
            mac: 设备 MAC 地址
            start_time: 起始时间
            end_time: 结束时间
            limit: 返回条数上限

        Returns:
            状态历史记录列表
        """
        mac = normalize_mac(mac)
        stmt = select(DeviceStatusHistory).where(
            DeviceStatusHistory.mac == mac
        )
        if start_time:
            stmt = stmt.where(DeviceStatusHistory.changed_at >= start_time)
        if end_time:
            stmt = stmt.where(DeviceStatusHistory.changed_at <= end_time)
        stmt = stmt.order_by(DeviceStatusHistory.changed_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # === 配置快照 (P1.6) ===

    async def save_config_snapshot(self, mac: str, config_data: dict[str, Any]) -> ConfigSnapshot:
        """保存设备配置快照。

        Args:
            mac: 设备 MAC 地址
            config_data: 完整配置数据

        Returns:
            创建的 ConfigSnapshot 实例
        """
        mac = normalize_mac(mac)
        # 获取下一个版本号
        stmt = select(func.max(ConfigSnapshot.version)).where(
            ConfigSnapshot.mac == mac
        )
        result = await self._session.execute(stmt)
        next_version = (result.scalar() or 0) + 1

        snapshot = ConfigSnapshot(
            mac=mac,
            version=next_version,
            config_data=json.dumps(config_data, ensure_ascii=False),
        )
        self._session.add(snapshot)
        await self._session.flush()

        # 清理过期版本 (P2.6)
        await self._cleanup_old_snapshots(mac, CONFIG_VERSION_MAX_COUNT)

        return snapshot

    async def get_config_snapshot(
        self, mac: str, version: int | None = None
    ) -> ConfigSnapshot | None:
        """获取配置快照。

        Args:
            mac: 设备 MAC 地址
            version: 版本号(None 获取最新版本)

        Returns:
            配置快照实例或 None
        """
        mac = normalize_mac(mac)
        stmt = select(ConfigSnapshot).where(ConfigSnapshot.mac == mac)
        if version is not None:
            stmt = stmt.where(ConfigSnapshot.version == version)
        else:
            stmt = stmt.order_by(ConfigSnapshot.version.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _cleanup_old_snapshots(self, mac: str, max_count: int) -> None:
        """清理多余的旧版配置快照。"""
        stmt = (
            select(ConfigSnapshot.id)
            .where(ConfigSnapshot.mac == mac)
            .order_by(ConfigSnapshot.version.desc())
            .offset(max_count)
        )
        result = await self._session.execute(stmt)
        old_ids = result.scalars().all()
        if old_ids:
            await self._session.execute(
                delete(ConfigSnapshot).where(ConfigSnapshot.id.in_(old_ids))
            )
            await self._session.flush()
