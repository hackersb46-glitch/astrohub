"""
M2 Device Manager v1.0 - 设备分组管理

实现设备分组增删改查(P3.1/P3.4)、设备加入/移出分组(P3.2/P3.3)、
分组批量操作(P3.5)。分组名唯一，设备不可重复加入同一分组。

Author: 雅痞张@南方天文
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from device.constants import GROUPS_FILE
from device.core.device_manager import DeviceManager
from device.core.logger import LOG
from device.core.mac_utils import normalize_mac
from device.core.storage import JsonStore
from device.models.schemas import (
    BatchGroupOperation,
    GroupCreate,
    GroupResponse,
)


class GroupManager:
    """设备分组管理器：分组CRUD、设备分组关联、批量操作。

    分组数据结构（以分组名为键）:
    {
        "name": "分组名",
        "description": "分组描述",
        "devices": ["MAC1", "MAC2", ...],  # 标准化后的MAC列表
        "created_at": "...",
        "updated_at": "..."
    }

    底层依赖 JsonStore 进行持久化存储。
    """

    def __init__(self, db_file: str | Path | None = None, device_manager: DeviceManager | None = None) -> None:
        """初始化分组管理器。

        Args:
            db_file: JSON数据库文件路径，默认使用 GROUPS_FILE
            device_manager: 设备管理器实例，用于验证设备存在性（批量操作时必需）
        """
        path = db_file if db_file is not None else GROUPS_FILE
        self._store = JsonStore(path, default={"records": {}})
        self._device_manager = device_manager
        LOG.info(f"GroupManager 初始化完成: {path}")

    # ------------------------------------------------------------------ #
    #  分组响应构建
    # ------------------------------------------------------------------ #

    def _build_response(self, name: str) -> dict:
        """从存储构建 GroupResponse 兼容的字典。

        Args:
            name: 分组名称

        Returns:
            符合 GroupResponse 模式的字典，分组不存在时返回空字典
        """
        record = self._store.get(name)
        if record is None:
            return {}
        return {
            "name": record.get("name", name),
            "description": record.get("description", ""),
            "devices": list(record.get("devices", [])),
            "created_at": record.get("created_at", ""),
            "updated_at": record.get("updated_at", ""),
        }

    # ------------------------------------------------------------------ #
    #  分组 CRUD (P3.1 / P3.4)
    # ------------------------------------------------------------------ #

    def create_group(self, data: GroupCreate) -> dict:
        """创建分组（P3.1：名称唯一性校验）。

        Args:
            data: 已验证的分组创建数据

        Returns:
            操作结果字典，包含 success 标志和分组详情
        """
        # P3.1: 名称唯一性校验
        if self._store.has(data.name):
            LOG.failed(f"分组名称已存在: {data.name}")
            return {
                "success": False,
                "error": f"分组名称 '{data.name}' 已存在",
            }

        now = datetime.now().isoformat()
        record: dict[str, Any] = {
            "name": data.name,
            "description": data.description,
            "devices": [],
            "created_at": now,
            "updated_at": now,
        }

        self._store.set(data.name, record)
        LOG.done(f"分组创建成功: {data.name}")
        return {"success": True, "group": self._build_response(data.name)}

    def list_groups(self, name: str | None = None) -> list[dict]:
        """查询分组列表，支持按名称过滤。

        Args:
            name: 精确匹配分组名称（可选）

        Returns:
            分组响应字典列表，无匹配时返回空列表
        """
        all_records = self._store.list_all()
        results: list[dict] = []

        for record in all_records:
            # 名称精确匹配
            if name is not None:
                if record.get("name") != name:
                    continue
            results.append(self._build_response(record.get("name", "")))

        LOG.info(f"分组列表查询: 匹配 {len(results)} 条记录")
        return results

    def get_group(self, name: str) -> dict | None:
        """获取单个分组信息。

        Args:
            name: 分组名称

        Returns:
            分组响应字典，不存在时返回None
        """
        record = self._store.get(name)
        if record is None:
            LOG.info(f"分组未找到: {name}")
            return None
        return self._build_response(name)

    def update_group(self, name: str, description: str) -> dict:
        """更新分组描述。

        Args:
            name: 分组名称
            description: 新的分组描述

        Returns:
            操作结果字典
        """
        if not self._store.has(name):
            LOG.failed(f"分组不存在，无法更新: {name}")
            return {"success": False, "error": f"分组 '{name}' 不存在"}

        record = self._store.get(name)
        record["description"] = description
        record["updated_at"] = datetime.now().isoformat()

        self._store.set(name, record)
        LOG.done(f"分组更新成功: {name}")
        return {"success": True, "group": self._build_response(name)}

    def delete_group(self, name: str) -> dict:
        """删除分组（P3.4：删除分组及关联关系，不影响设备本身）。

        Args:
            name: 分组名称

        Returns:
            操作结果字典
        """
        if not self._store.has(name):
            LOG.failed(f"分组不存在，无法删除: {name}")
            return {"success": False, "error": f"分组 '{name}' 不存在"}

        self._store.delete(name)
        LOG.done(f"分组删除成功: {name}（设备记录不受影响）")
        return {"success": True}

    # ------------------------------------------------------------------ #
    #  设备加入/移出分组 (P3.2 / P3.3)
    # ------------------------------------------------------------------ #

    def add_device(self, group_name: str, mac: str) -> dict:
        """将设备加入分组（P3.2：不重复加入同一分组）。

        Args:
            group_name: 分组名称
            mac: 设备的MAC地址

        Returns:
            操作结果字典
        """
        norm_mac = normalize_mac(mac)

        # 验证分组存在
        if not self._store.has(group_name):
            LOG.failed(f"分组不存在: {group_name}")
            return {"success": False, "error": f"分组 '{group_name}' 不存在"}

        group = self._store.get(group_name)
        devices = group.get("devices", [])

        # P3.2: 设备不可重复加入同一分组
        if norm_mac in devices:
            LOG.warning(f"设备已在分组中: {norm_mac} in {group_name}")
            return {
                "success": False,
                "error": f"设备 {norm_mac} 已在分组 '{group_name}' 中",
            }

        devices.append(norm_mac)
        group["devices"] = devices
        group["updated_at"] = datetime.now().isoformat()

        self._store.set(group_name, group)
        LOG.done(f"设备加入分组: {norm_mac} -> {group_name}")
        return {"success": True, "group": self._build_response(group_name)}

    def remove_device(self, group_name: str, mac: str) -> dict:
        """将设备从分组中移除（P3.3：仅移除关联，不影响设备本身）。

        Args:
            group_name: 分组名称
            mac: 设备的MAC地址

        Returns:
            操作结果字典
        """
        norm_mac = normalize_mac(mac)

        # 验证分组存在
        if not self._store.has(group_name):
            LOG.failed(f"分组不存在: {group_name}")
            return {"success": False, "error": f"分组 '{group_name}' 不存在"}

        group = self._store.get(group_name)
        devices = group.get("devices", [])

        # 设备不在分组中
        if norm_mac not in devices:
            LOG.info(f"设备不在分组中: {norm_mac} not in {group_name}")
            return {
                "success": False,
                "error": f"设备 {norm_mac} 不在分组 '{group_name}' 中",
            }

        devices.remove(norm_mac)
        group["devices"] = devices
        group["updated_at"] = datetime.now().isoformat()

        self._store.set(group_name, group)
        LOG.done(f"设备移出分组: {norm_mac} <- {group_name}")
        return {"success": True, "group": self._build_response(group_name)}

    # ------------------------------------------------------------------ #
    #  分组批量操作 (P3.5)
    # ------------------------------------------------------------------ #

    def batch_operation(
        self,
        data: BatchGroupOperation,
        operation_fn: Callable[[str], dict] | None = None,
    ) -> dict:
        """对分组内所有设备执行批量操作（P3.5）。

        Args:
            data: 批量操作请求（包含 group_name 和 operation 类型）
            operation_fn: 自定义操作函数，签名为 (mac: str) -> dict，
                         接收MAC地址，返回 {"success": bool, "error": str?}

        Returns:
            操作汇总: {success_count, failure_count, failures: [{mac, error}], total}
        """
        group = self._build_response(data.group_name)
        if not group:
            LOG.failed(f"分组不存在: {data.group_name}")
            return {
                "success_count": 0,
                "failure_count": 0,
                "failures": [],
                "total": 0,
                "error": f"分组 '{data.group_name}' 不存在",
            }

        devices = group.get("devices", [])

        # 空分组提示
        if not devices:
            LOG.warning(f"分组为空，无设备可操作: {data.group_name}")
            return {
                "success_count": 0,
                "failure_count": 0,
                "failures": [],
                "total": 0,
                "message": f"分组 '{data.group_name}' 为空",
            }

        # 内置操作映射（当未提供 operation_fn 时使用）
        if operation_fn is None:
            if data.operation == "status_check":
                operation_fn = self._op_status_check
            elif data.operation == "config_read":
                operation_fn = self._op_config_read
            elif data.operation == "config_write":
                operation_fn = self._op_config_write
            else:
                return {
                    "success_count": 0,
                    "failure_count": len(devices),
                    "failures": [
                        {"mac": mac, "error": f"不支持的操作类型: {data.operation}"}
                        for mac in devices
                    ],
                    "total": len(devices),
                }

        # 逐台执行
        success_count = 0
        failure_count = 0
        failures: list[dict] = []

        for mac in devices:
            try:
                result = operation_fn(mac)
                if result.get("success"):
                    success_count += 1
                else:
                    failure_count += 1
                    failures.append({"mac": mac, "error": result.get("error", "未知错误")})
            except Exception as exc:
                failure_count += 1
                failures.append({"mac": mac, "error": str(exc)})

        LOG.info(
            f"批量操作完成: {data.operation} on {data.group_name} | "
            f"总数={len(devices)}, 成功={success_count}, 失败={failure_count}"
        )

        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "failures": failures,
            "total": len(devices),
        }

    # ------------------------------------------------------------------ #
    #  内置批量操作实现
    # ------------------------------------------------------------------ #

    def _op_status_check(self, mac: str) -> dict:
        """状态查询操作（内置默认实现）。

        若提供了 DeviceManager，则查询设备状态；否则返回占位结果。
        """
        if self._device_manager is None:
            return {"success": False, "error": "DeviceManager 未配置，无法执行状态查询"}
        device = self._device_manager.get_device(mac)
        if device is None:
            return {"success": False, "error": f"设备不存在: {mac}"}
        return {"success": True, "status": device.get("heartbeat_status")}

    def _op_config_read(self, mac: str) -> dict:
        """配置读取操作（占位实现，实际应调用 ISAPI 接口）。"""
        return {"success": False, "error": "配置读取需实现 ISAPI 接口调用"}

    def _op_config_write(self, mac: str) -> dict:
        """配置写入操作（占位实现，实际应调用 ISAPI 接口）。"""
        return {"success": False, "error": "配置写入需实现 ISAPI 接口调用"}

    # ------------------------------------------------------------------ #
    #  便捷方法
    # ------------------------------------------------------------------ #

    def group_exists(self, name: str) -> bool:
        """检查分组名称是否存在。

        Args:
            name: 分组名称

        Returns:
            True=存在, False=不存在
        """
        return self._store.has(name)

    def group_count(self) -> int:
        """获取分组总数。

        Returns:
            分组记录数量
        """
        return self._store.count()

    def get_device_groups(self, mac: str) -> list[dict]:
        """查询设备所属的所有分组。

        Args:
            mac: 设备的MAC地址

        Returns:
            包含该设备的分组列表
        """
        norm_mac = normalize_mac(mac)
        all_groups = self._store.list_all()
        results: list[dict] = []

        for group in all_groups:
            if norm_mac in group.get("devices", []):
                results.append(self._build_response(group.get("name", "")))

        LOG.info(f"设备所属分组: {norm_mac} in {len(results)} groups")
        return results
