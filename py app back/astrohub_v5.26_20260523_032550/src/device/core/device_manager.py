"""
M2 Device Manager v1.0 - 设备CRUD管理

实现设备增删改查核心功能(P0)、MAC唯一标识校验(P0.7)。
以MAC为唯一主键，支持精确查询/模糊匹配/状态过滤。

Author: 雅痞张@南方天文
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from device.constants import DEVICES_FILE
from device.core.logger import LOG
from device.core.mac_utils import normalize_mac
from device.core.storage import JsonStore
from device.models.schemas import DeviceCreate, DeviceResponse, DeviceUpdate


class DeviceManager:
    """设备管理器：以MAC为唯一主键的设备CRUD操作。

    支持设备创建/查询/更新/删除、MAC唯一性校验、状态过滤。
    底层依赖 JsonStore 进行持久化存储。
    """

    def __init__(self, db_file: str | Path | None = None) -> None:
        """初始化设备管理器。

        Args:
            db_file: JSON数据库文件路径，默认使用 DEVICES_FILE
        """
        path = db_file if db_file is not None else DEVICES_FILE
        self._store = JsonStore(path, default={"records": {}})
        LOG.info(f"DeviceManager 初始化完成: {path}")

    # ------------------------------------------------------------------ #
    #  设备查询辅助
    # ------------------------------------------------------------------ #

    def _build_response(self, mac: str) -> dict:
        """从存储构建 DeviceResponse 兼容的字典。

        Args:
            mac: 设备的MAC地址

        Returns:
            符合 DeviceResponse 模式的字典
        """
        record = self._store.get(mac)
        if record is None:
            return {}
        return {
            "mac": record.get("mac", mac),
            "ip": record.get("ip", ""),
            "model": record.get("model", ""),
            "username": record.get("username", ""),
            "port": record.get("port", 80),
            "notes": record.get("notes", ""),
            "status": record.get("status", "new"),
            "heartbeat_status": record.get("heartbeat_status", "offline"),
            "created_at": record.get("created_at", ""),
            "updated_at": record.get("updated_at", ""),
        }

    # ------------------------------------------------------------------ #
    #  设备 CRUD
    # ------------------------------------------------------------------ #

    def create_device(self, data: DeviceCreate) -> dict:
        """创建设备（P0.1 + P0.7 MAC唯一性校验）。

        Args:
            data: 已验证的设备创建数据

        Returns:
            操作结果字典，包含 success 标志
        """
        # P0.7: MAC唯一性校验
        if self._store.has(data.mac):
            existing_record = self._store.get(data.mac)
            LOG.failed(f"MAC地址已存在: {data.mac}")
            return {
                "success": False,
                "error": f"MAC {data.mac} 已存在",
                "existing": DeviceResponse(**existing_record).model_dump(),
            }

        record: dict[str, Any] = {
            "mac": data.mac,
            "ip": data.ip,
            "model": data.model,
            "username": data.username,
            "password": data.password,
            "port": data.port,
            "notes": data.notes,
            "status": "new",
            "heartbeat_status": "offline",
        }

        self._store.set(data.mac, record)
        LOG.done(f"设备创建成功: {data.mac}")
        return {"success": True, "device": self._build_response(data.mac)}

    def list_devices(
        self,
        mac: str | None = None,
        model: str | None = None,
        status_filter: str | None = None,
    ) -> list[dict]:
        """查询设备列表，支持过滤（P0.2）。

        Args:
            mac: 精确匹配MAC地址
            model: 模糊匹配设备型号（大小写不敏感）
            status_filter: 精确匹配设备状态

        Returns:
            设备响应字典列表，无匹配时返回空列表
        """
        all_records = self._store.list_all()
        results: list[dict] = []

        for record in all_records:
            # MAC精确匹配（已标准化）
            if mac is not None:
                norm_mac = normalize_mac(mac)
                if record.get("mac") != norm_mac:
                    continue

            # 型号模糊匹配（大小写不敏感）
            if model is not None:
                record_model = record.get("model", "")
                if model.lower() not in record_model.lower():
                    continue

            # 状态精确匹配
            if status_filter is not None:
                if record.get("status") != status_filter:
                    continue

            results.append(self._build_response(record.get("mac", "")))

        LOG.info(f"设备列表查询: 匹配 {len(results)} 条记录")
        return results

    def get_device(self, mac: str) -> dict | None:
        """获取单个设备信息。

        Args:
            mac: 设备的MAC地址

        Returns:
            设备响应字典，不存在时返回None
        """
        norm_mac = normalize_mac(mac)
        record = self._store.get(norm_mac)
        if record is None:
            LOG.info(f"设备未找到: {norm_mac}")
            return None
        return self._build_response(norm_mac)

    def update_device(self, mac: str, data: DeviceUpdate) -> dict:
        """更新设备信息（P0.3）。

        只更新非None的字段，禁止更新MAC/status/heartbeat_status/created_at。

        Args:
            mac: 设备的MAC地址
            data: 设备更新数据

        Returns:
            操作结果字典
        """
        norm_mac = normalize_mac(mac)

        if not self._store.has(norm_mac):
            LOG.failed(f"设备不存在，无法更新: {norm_mac}")
            return {"success": False, "error": f"设备 {norm_mac} 不存在"}

        record = self._store.get(norm_mac)

        # 仅更新非None的字段
        updatable_fields = ["ip", "model", "username", "password", "port", "notes"]
        update_data = data.model_dump(exclude_none=True)
        for field in updatable_fields:
            if field in update_data:
                record[field] = update_data[field]

        # 手动触碰 updated_at（JsonStore.set 也会做，但显式赋值更安全）
        record["updated_at"] = datetime.now().isoformat()

        self._store.set(norm_mac, record)
        LOG.done(f"设备更新成功: {norm_mac}")
        return {"success": True, "device": self._build_response(norm_mac)}

    def delete_device(self, mac: str) -> dict:
        """删除设备（P0.4）。

        在线设备禁止删除。

        Args:
            mac: 设备的MAC地址

        Returns:
            操作结果字典
        """
        norm_mac = normalize_mac(mac)

        if not self._store.has(norm_mac):
            LOG.failed(f"设备不存在，无法删除: {norm_mac}")
            return {"success": False, "error": f"设备 {norm_mac} 不存在"}

        # 在线设备禁止删除
        record = self._store.get(norm_mac)
        if record.get("heartbeat_status") == "online":
            LOG.failed(f"在线设备禁止删除: {norm_mac}")
            return {"success": False, "error": f"在线设备不允许删除: {norm_mac}"}

        self._store.delete(norm_mac)
        LOG.done(f"设备删除成功: {norm_mac}")
        return {"success": True}

    # ------------------------------------------------------------------ #
    #  便捷查询
    # ------------------------------------------------------------------ #

    def mac_exists(self, mac: str) -> bool:
        """检查MAC地址是否存在。

        Args:
            mac: 设备的MAC地址

        Returns:
            True=存在, False=不存在
        """
        return self._store.has(mac)

    def device_count(self) -> int:
        """获取设备总数。

        Returns:
            设备记录数量
        """
        return self._store.count()
