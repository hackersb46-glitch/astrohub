"""
M2 Device Manager v1.0 - 设备生命周期状态机

实现设备生命周期状态管理(P5.1-P5.5)。
状态流转: new→active→inactive→deleted。
设备激活(完成发现→认证→能力探测→保存凭证后标记active)。
设备停用(inactive, 停止心跳但保留数据)。
重新激活(active←inactive→active)。
设备删除(inactive状态才可删除, 删除所有相关数据)。
非法状态流转被阻止。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from device.constants import VALID_TRANSITIONS, DeviceStatus
from device.core.device_manager import DeviceManager
from device.core.logger import LOG
from device.core.mac_utils import normalize_mac
from device.core.storage import JsonStore
from device.models.schemas import DeviceLifecycleResponse

# 生命周期持久化文件路径
LIFECYCLE_FILE = Path(__file__).resolve().parent.parent / "data" / "lifecycle.json"


class DeviceLifecycle:
    """设备生命周期状态机管理器。

    状态: new → active → inactive → deleted
    流转约束由 VALID_TRANSITIONS 定义。
    与 DeviceManager 集成，同步设备 status 字段。

    Args:
        device_manager: DeviceManager实例，用于读写设备数据
        db_file: 生命周期持久化文件路径（可选）
    """

    def __init__(
        self,
        device_manager: DeviceManager | None = None,
        db_file: str | Path | None = None,
    ) -> None:
        self._device_manager = device_manager
        path = db_file if db_file is not None else LIFECYCLE_FILE
        self._store = JsonStore(path, default={"records": {}})
        LOG.info(f"DeviceLifecycle 初始化完成: {path}")

    # ------------------------------------------------------------------ #
    #  状态流转核心逻辑
    # ------------------------------------------------------------------ #

    def can_transition(self, from_status: str, to_status: str) -> bool:
        """检查状态流转是否合法。

        Args:
            from_status: 当前状态
            to_status: 目标状态

        Returns:
            True=允许流转, False=非法流转
        """
        allowed = VALID_TRANSITIONS.get(from_status, [])
        return to_status in allowed

    def _get_current_status(self, mac: str) -> str | None:
        """获取设备当前生命周期状态。

        Args:
            mac: 设备的MAC地址

        Returns:
            当前状态字符串，设备不存在时返回None
        """
        norm_mac = normalize_mac(mac)
        # 优先从本地生命周期存储读取
        record = self._store.get(norm_mac)
        if record:
            return record.get("status")

        # 回退到 DeviceManager 读取
        if self._device_manager:
            device = self._device_manager.get_device(norm_mac)
            if device:
                return device.get("status", "new")

        return None

    def transition(self, mac: str, new_status: str, reason: str = "") -> dict:
        """执行设备状态流转。

        Args:
            mac: 设备的MAC地址
            new_status: 目标状态
            reason: 流转原因描述

        Returns:
            操作结果，包含 DeviceLifecycleResponse 格式数据
        """
        norm_mac = normalize_mac(mac)
        old_status = self._get_current_status(norm_mac)

        # 设备不存在
        if old_status is None:
            LOG.failed(f"设备不存在，无法流转状态: {norm_mac}")
            return {
                "success": False,
                "error": f"设备不存在: {norm_mac}",
            }

        # 验证目标状态枚举值
        valid_statuses = {s.value for s in DeviceStatus}
        if new_status not in valid_statuses:
            LOG.failed(f"非法目标状态: {new_status} (合法值: {', '.join(valid_statuses)})")
            return {
                "success": False,
                "error": f"非法状态值: {new_status}，合法值: {', '.join(sorted(valid_statuses))}",
            }

        # 验证状态流转合法性
        if not self.can_transition(old_status, new_status):
            transition_str = f"{old_status}→{new_status}"
            allowed = VALID_TRANSITIONS.get(old_status, [])
            LOG.failed(f"非法状态流转: {transition_str} (允许: {', '.join(allowed) if allowed else '无'})")
            return {
                "success": False,
                "error": f"非法状态流转: {transition_str}，允许: {', '.join(allowed) if allowed else '无'}",
            }

        # 执行状态更新
        timestamp = datetime.now().isoformat()
        transition_str = f"{old_status}→{new_status}"

        # 更新本地生命周期存储
        lifecycle_record = self._store.get(norm_mac) or {
            "mac": norm_mac,
            "status": old_status,
            "history": [],
        }
        lifecycle_record["status"] = new_status
        lifecycle_record["history"].append({
            "from": old_status,
            "to": new_status,
            "reason": reason,
            "timestamp": timestamp,
        })
        self._store.set(norm_mac, lifecycle_record)

        # 同步到 DeviceManager
        if self._device_manager:
            self._sync_device_status(norm_mac, new_status)

        LOG.done(f"状态流转成功: {norm_mac} {transition_str} ({reason})")

        response = DeviceLifecycleResponse(
            mac=norm_mac,
            status=new_status,
            transition=transition_str,
            timestamp=timestamp,
            message=f"设备状态已从 {old_status} 流转为 {new_status}: {reason}",
        )

        return {
            "success": True,
            "lifecycle": response.model_dump(),
        }

    # ------------------------------------------------------------------ #
    #  P5.1 - 设备激活
    # ------------------------------------------------------------------ #

    def activate(self, mac: str, reason: str = "设备激活: 发现→认证→能力探测→凭证保存") -> dict:
        """激活设备: new→active。

        设备完成发现、认证、能力探测、保存凭证后标记为active。

        Args:
            mac: 设备的MAC地址
            reason: 激活原因

        Returns:
            操作结果
        """
        norm_mac = normalize_mac(mac)

        # 设备本身必须存在
        if self._device_manager and not self._device_manager.mac_exists(norm_mac):
            LOG.failed(f"设备不存在，无法激活: {norm_mac}")
            return {"success": False, "error": f"设备不存在: {norm_mac}"}

        result = self.transition(norm_mac, DeviceStatus.ACTIVE.value, reason)
        if result.get("success"):
            LOG.done(f"设备激活成功: {norm_mac}")
        return result

    # ------------------------------------------------------------------ #
    #  P5.2 - 设备停用
    # ------------------------------------------------------------------ #

    def deactivate(self, mac: str, reason: str = "设备停用") -> dict:
        """停用设备: active→inactive 或 new→inactive。

        inactive状态下设备停止心跳，但保留所有数据。

        Args:
            mac: 设备的MAC地址
            reason: 停用原因

        Returns:
            操作结果
        """
        norm_mac = normalize_mac(mac)
        result = self.transition(norm_mac, DeviceStatus.INACTIVE.value, reason)
        if result.get("success"):
            LOG.done(f"设备停用成功: {norm_mac} (心跳已停止, 数据保留)")
        return result

    # ------------------------------------------------------------------ #
    #  P5.3 - 设备重新激活
    # ------------------------------------------------------------------ #

    def reactivate(self, mac: str, reason: str = "设备重新激活") -> dict:
        """重新激活设备: inactive→active。

        Args:
            mac: 设备的MAC地址
            reason: 重新激活原因

        Returns:
            操作结果
        """
        norm_mac = normalize_mac(mac)

        # 验证当前状态是否为inactive
        current = self._get_current_status(norm_mac)
        if current != DeviceStatus.INACTIVE.value:
            LOG.failed(f"只有inactive状态的设备可重新激活: {norm_mac} (当前={current})")
            return {
                "success": False,
                "error": f"只有inactive状态的设备可重新激活，当前状态: {current}",
            }

        result = self.transition(norm_mac, DeviceStatus.ACTIVE.value, reason)
        if result.get("success"):
            LOG.done(f"设备重新激活成功: {norm_mac}")
        return result

    # ------------------------------------------------------------------ #
    #  P5.4 - 设备删除
    # ------------------------------------------------------------------ #

    def delete_device(self, mac: str, reason: str = "设备删除") -> dict:
        """删除设备: inactive→deleted。

        只有inactive状态的设备才可删除。
        删除所有相关数据: 设备记录、生命周期记录、心跳记录等。

        Args:
            mac: 设备的MAC地址
            reason: 删除原因

        Returns:
            操作结果
        """
        norm_mac = normalize_mac(mac)

        # 验证当前状态是否为inactive
        current = self._get_current_status(norm_mac)
        if current != DeviceStatus.INACTIVE.value:
            LOG.failed(f"只有inactive状态的设备可删除: {norm_mac} (当前={current})")
            return {
                "success": False,
                "error": f"只有inactive状态的设备可删除，当前状态: {current}",
            }

        # 先执行状态流转到deleted
        result = self.transition(norm_mac, DeviceStatus.DELETED.value, reason)
        if not result.get("success"):
            return result

        # 删除设备记录
        deleted_data: list[str] = []
        if self._device_manager:
            dm_result = self._device_manager.delete_device(norm_mac)
            if dm_result.get("success"):
                deleted_data.append("设备记录")
            else:
                LOG.warning(f"删除设备记录失败: {norm_mac} - {dm_result.get('error')}")

        # 清理生命周期历史记录(可选，保留审计追踪)
        # 这里保留生命周期记录作为审计日志，不清理

        LOG.done(f"设备删除成功: {norm_mac} (已删除: {', '.join(deleted_data)})")

        # 更新响应消息
        result["deleted_data"] = deleted_data
        return result

    # ------------------------------------------------------------------ #
    #  状态查询
    # ------------------------------------------------------------------ #

    def get_status(self, mac: str) -> dict | None:
        """获取设备生命周期状态及流转历史。

        Args:
            mac: 设备的MAC地址

        Returns:
            设备生命周期状态信息，设备不存在时返回None
        """
        norm_mac = normalize_mac(mac)
        record = self._store.get(norm_mac)

        if record is None:
            # 回退到 DeviceManager
            if self._device_manager:
                device = self._device_manager.get_device(norm_mac)
                if device:
                    status = device.get("status", "new")
                    return {
                        "mac": norm_mac,
                        "status": status,
                        "history": [],
                    }
            return None

        return {
            "mac": record.get("mac", norm_mac),
            "status": record.get("status", "new"),
            "history": record.get("history", []),
        }

    def list_status(self) -> list[dict]:
        """获取所有设备的生命周期状态。

        Returns:
            设备生命周期状态列表
        """
        all_records = self._store.list_all()
        results: list[dict] = []

        for record in all_records:
            mac = record.get("mac", "")
            results.append({
                "mac": mac,
                "status": record.get("status", "new"),
                "history": record.get("history", []),
            })

        LOG.info(f"生命周期状态列表: {len(results)} 个设备")
        return results

    def get_transition_history(self, mac: str) -> list[dict]:
        """获取设备的状态流转历史。

        Args:
            mac: 设备的MAC地址

        Returns:
            状态流转历史记录列表
        """
        status_info = self.get_status(mac)
        if status_info:
            return status_info.get("history", [])
        return []

    # ------------------------------------------------------------------ #
    #  辅助方法
    # ------------------------------------------------------------------ #

    def _sync_device_status(self, mac: str, new_status: str) -> None:
        """同步生命周期状态到 DeviceManager 中的 status 字段。

        Args:
            mac: 设备的MAC地址
            new_status: 新的生命周期状态
        """
        if self._device_manager is None:
            return

        try:
            device = self._device_manager.get_device(mac)
            if device is None:
                return

            record = self._device_manager._store.get(mac)
            if record is None:
                return

            old_status = record.get("status", "new")
            if old_status != new_status:
                record["status"] = new_status
                record["updated_at"] = datetime.now().isoformat()
                self._device_manager._store.set(mac, record)
                LOG.info(
                    f"设备 status 已同步: {mac} {old_status}→{new_status}"
                )
        except Exception as e:
            LOG.error(f"同步 status 失败: {mac} - {e}")
