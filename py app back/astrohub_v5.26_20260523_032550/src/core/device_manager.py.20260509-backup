"""
AstroHub v2.0 - 设备管理器

设备注册、状态追踪、分组管理、配置备份/恢复。
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from src.config import CONFIG_DIR
from src.logger import get_logger

log = get_logger("device_manager")

# Time constants
HEARTBEAT_TIMEOUT = 60  # 秒，超过此时间无心跳则认为离线
CONFIG_BACKUP_DIR = CONFIG_DIR / "device_backups"


# ============================================================
# Data Models
# ============================================================


class Device(BaseModel):
    """设备信息模型。"""

    mac: str
    ip: str = ""
    name: str = ""
    model: str = ""
    status: str = "offline"  # online | offline | error
    registered_at: str = Field(default_factory=lambda: _now_iso())
    last_heartbeat: str = Field(default_factory=lambda: _now_iso())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_online(self) -> None:
        """标记为在线，更新心跳时间。"""
        self.status = "online"
        self.last_heartbeat = _now_iso()

    def mark_offline(self) -> None:
        """标记为离线。"""
        self.status = "offline"

    def mark_error(self) -> None:
        """标记为异常。"""
        self.status = "error"


class DeviceGroup(BaseModel):
    """设备分组模型。"""

    name: str
    description: str = ""
    mac_addresses: set[str] = Field(default_factory=set)
    created_at: str = Field(default_factory=lambda: _now_iso())


# ============================================================
# Helpers
# ============================================================


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 字符串。"""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _normalize_mac(mac: str) -> str:
    """统一 MAC 格式：转大写，横杠置换为冒号。"""
    return mac.strip().replace("-", ":").upper()


# ============================================================
# DeviceManager
# ============================================================


class DeviceManager:
    """设备管理器。

    提供设备注册、注销、查询、心跳、分组管理、配置备份等功能。
    所有数据存储在内存中，支持持久化到 JSON。
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        """初始化设备管理器。

        Args:
            storage_path: 设备数据持久化 JSON 路径，默认使用 CONFIG_DIR/devices.json。
        """
        self._devices: dict[str, Device] = {}
        self._groups: dict[str, DeviceGroup] = {}
        self._backups: dict[str, Any] = {}  # mac -> config backup data
        self._lock = threading.RLock()

        if storage_path is None:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            storage_path = CONFIG_DIR / "devices.json"
        self._storage_path = storage_path.resolve()

        CONFIG_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        self._load()
        log.info(f"DeviceManager 初始化完成, storage={self._storage_path}")

    # ============================================================
    # Registration
    # ============================================================

    def register_device(
        self,
        mac: str,
        ip: str = "",
        name: str = "",
        model: str = "",
        **extra: Any,
    ) -> Device:
        """注册新设备，已存在则更新。

        Args:
            mac: 设备 MAC 地址。
            ip: IP 地址。
            name: 设备名称。
            model: 设备型号。
            **extra: 额外的 metadata 字段。

        Returns:
            注册后的 Device 对象。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            if norm_mac in self._devices:
                dev = self._devices[norm_mac]
                dev.ip = ip or dev.ip
                dev.name = name or dev.name
                dev.model = model or dev.model
                if extra:
                    dev.metadata.update(extra)
                log.info(f"更新设备: {norm_mac}")
            else:
                dev = Device(mac=norm_mac, ip=ip, name=name, model=model, metadata=extra)
                self._devices[norm_mac] = dev
                log.info(f"注册设备: {norm_mac} ({name})")

            self._save()
            return dev

    def unregister_device(self, mac: str) -> bool:
        """注销设备，同时移除其分组关联和配置备份。

        Args:
            mac: 设备 MAC 地址。

        Returns:
            True 成功，False 设备不存在。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            if norm_mac not in self._devices:
                log.warning(f"注销失败，设备不存在: {norm_mac}")
                return False

            # 从分组中移除
            for group in self._groups.values():
                group.mac_addresses.discard(norm_mac)

            # 移除备份
            self._backups.pop(norm_mac, None)

            del self._devices[norm_mac]
            self._save()
            log.info(f"注销设备: {norm_mac}")
            return True

    # ============================================================
    # Query
    # ============================================================

    def get_device(self, mac: str) -> Device | None:
        """根据 MAC 获取设备信息。

        Args:
            mac: 设备 MAC 地址。

        Returns:
            Device 对象或 None。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            return self._devices.get(norm_mac)

    def list_devices(self, status: str | None = None) -> list[Device]:
        """列出所有设备，可按状态筛选。

        Args:
            status: 可选，仅返回指定状态的设备 (online/offline/error)。

        Returns:
            Device 列表。
        """
        with self._lock:
            if status is None:
                return list(self._devices.values())
            return [d for d in self._devices.values() if d.status == status]

    # ============================================================
    # Status & Heartbeat
    # ============================================================

    def update_status(self, mac: str, status: str) -> bool:
        """更新设备状态。

        Args:
            mac: 设备 MAC 地址。
            status: 新状态 (online/offline/error)。

        Returns:
            True 成功，False 设备不存在。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            dev = self._devices.get(norm_mac)
            if dev is None:
                log.warning(f"状态更新失败，设备不存在: {norm_mac}")
                return False
            dev.status = status
            if status == "online":
                dev.last_heartbeat = _now_iso()
            self._save()
            log.info(f"设备状态更新: {norm_mac} -> {status}")
            return True

    def process_heartbeat(self, mac: str) -> bool:
        """处理心跳，更新最后心跳时间并标记为在线。

        Args:
            mac: 设备 MAC 地址。

        Returns:
            True 成功，False 设备不存在。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            dev = self._devices.get(norm_mac)
            if dev is None:
                log.warning(f"心跳处理失败，设备不存在: {norm_mac}")
                return False
            dev.mark_online()
            self._save()
            return True

    def check_timeout_devices(self) -> list[str]:
        """检查超时无心跳的设备，自动标记为离线。

        Returns:
            超时的设备 MAC 列表。
        """
        timed_out: list[str] = []
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff_ts = cutoff.timestamp() - HEARTBEAT_TIMEOUT

        with self._lock:
            for mac, dev in self._devices.items():
                if dev.status != "online":
                    continue
                try:
                    hb = datetime.fromisoformat(dev.last_heartbeat)
                    if hb.timestamp() < cutoff_ts:
                        dev.mark_offline()
                        timed_out.append(mac)
                        log.warning(f"设备心跳超时，标记离线: {mac}")
                except (ValueError, TypeError):
                    dev.mark_offline()
                    timed_out.append(mac)

            if timed_out:
                self._save()
        return timed_out

    # ============================================================
    # Group Management
    # ============================================================

    def add_group(self, name: str, description: str = "") -> DeviceGroup:
        """新增设备分组。

        Args:
            name: 分组名称。
            description: 分组描述。

        Returns:
            新创建的 DeviceGroup。
        """
        with self._lock:
            if name in self._groups:
                log.warning(f"分组已存在: {name}")
                return self._groups[name]
            group = DeviceGroup(name=name, description=description)
            self._groups[name] = group
            self._save()
            log.info(f"新增分组: {name}")
            return group

    def remove_group(self, name: str) -> bool:
        """移除分组（不清除分组内设备的关联）。

        Args:
            name: 分组名称。

        Returns:
            True 成功，False 分组不存在。
        """
        with self._lock:
            if name not in self._groups:
                log.warning(f"移除分组失败，分组不存在: {name}")
                return False
            del self._groups[name]
            self._save()
            log.info(f"移除分组: {name}")
            return True

    def add_device_to_group(self, mac: str, group: str) -> bool:
        """将设备加入分组，分组不存在则自动创建。

        Args:
            mac: 设备 MAC 地址。
            group: 分组名称。

        Returns:
            True 成功，False 设备不存在。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            if norm_mac not in self._devices:
                log.warning(f"设备加入分组失败，设备不存在: {norm_mac}")
                return False

            if group not in self._groups:
                self._groups[group] = DeviceGroup(name=group)
                log.info(f"自动创建分组: {group}")

            self._groups[group].mac_addresses.add(norm_mac)
            self._save()
            log.info(f"设备加入分组: {norm_mac} -> {group}")
            return True

    def remove_device_from_group(self, mac: str, group: str) -> bool:
        """将设备从分组移除。

        Args:
            mac: 设备 MAC 地址。
            group: 分组名称。

        Returns:
            True 成功，False 分组不存在。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            grp = self._groups.get(group)
            if grp is None:
                log.warning(f"移除设备分组失败，分组不存在: {group}")
                return False
            grp.mac_addresses.discard(norm_mac)
            self._save()
            log.info(f"设备移出分组: {norm_mac} <- {group}")
            return True

    def get_group(self, name: str) -> DeviceGroup | None:
        """获取分组信息。

        Args:
            name: 分组名称。

        Returns:
            DeviceGroup 或 None。
        """
        with self._lock:
            return self._groups.get(name)

    def list_groups(self) -> list[DeviceGroup]:
        """列出所有分组。

        Returns:
            DeviceGroup 列表。
        """
        with self._lock:
            return list(self._groups.values())

    def get_devices_in_group(self, name: str) -> list[Device]:
        """获取分组内所有设备。

        Args:
            name: 分组名称。

        Returns:
            分组中有效 Device 列表（已被注销的设备自动忽略）。
        """
        with self._lock:
            grp = self._groups.get(name)
            if grp is None:
                return []
            return [self._devices[m] for m in grp.mac_addresses if m in self._devices]

    def get_groups_for_device(self, mac: str) -> list[str]:
        """获取设备所属的所有分组。

        Args:
            mac: 设备 MAC 地址。

        Returns:
            分组名称列表。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            return [name for name, grp in self._groups.items() if norm_mac in grp.mac_addresses]

    # ============================================================
    # Configuration Backup
    # ============================================================

    def diff_config(
        self, mac: str, old_cfg: dict, new_cfg: dict, prefix: str = ""
    ) -> list[dict]:
        """递归比较两段配置，输出差异列表。

        Args:
            mac: 设备 MAC（用于日志上下文）。
            old_cfg: 原始配置。
            new_cfg: 新配置。
            prefix: 当前路径前缀（递归用，外部调用无需设置）。

        Returns:
            差异列表，每项包含 path, old_value, new_value, action。
        """
        diffs: list[dict] = []

        all_keys = set(old_cfg.keys()) | set(new_cfg.keys())
        for key in sorted(all_keys):
            path = f"{prefix}.{key}" if prefix else key
            in_old = key in old_cfg
            in_new = key in new_cfg

            if in_old and not in_new:
                diffs.append({"path": path, "old_value": old_cfg[key], "new_value": None, "action": "removed"})
            elif not in_old and in_new:
                diffs.append({"path": path, "old_value": None, "new_value": new_cfg[key], "action": "added"})
            else:
                old_val = old_cfg[key]
                new_val = new_cfg[key]
                if isinstance(old_val, dict) and isinstance(new_val, dict):
                    diffs.extend(self.diff_config(mac, old_val, new_val, prefix=path))
                elif isinstance(old_val, list) and isinstance(new_val, list):
                    if old_val != new_val:
                        diffs.append({"path": path, "old_value": old_val, "new_value": new_val, "action": "modified"})
                elif old_val != new_val:
                    diffs.append({"path": path, "old_value": old_val, "new_value": new_val, "action": "modified"})

        if prefix == "":
            norm_mac = _normalize_mac(mac)
            log.info(f"配置差异 [{norm_mac}]: 共 {len(diffs)} 处变更")
        return diffs

    def backup_config(self, mac: str, config_data: Any) -> str:
        """备份设备配置。

        Args:
            mac: 设备 MAC 地址。
            config_data: 配置数据（任意可 JSON 序列化类型）。

        Returns:
            备份文件路径字符串。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            # 内存备份
            self._backups[norm_mac] = {
                "data": config_data,
                "timestamp": _now_iso(),
            }

            # 文件备份
            backup_file = CONFIG_BACKUP_DIR / f"{norm_mac.replace(':', '')}_backup.json"
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump({"mac": norm_mac, "timestamp": _now_iso(), "config": config_data}, f, indent=2, ensure_ascii=False)

            self._save()
            log.info(f"配置备份完成: {norm_mac} -> {backup_file}")
            return str(backup_file)

    def restore_backup(self, mac: str) -> Any | None:
        """恢复设备配置备份。

        Args:
            mac: 设备 MAC 地址。

        Returns:
            配置数据，若不存在则返回 None。
        """
        norm_mac = _normalize_mac(mac)
        with self._lock:
            # 尝试内存
            if norm_mac in self._backups:
                log.info(f"从内存恢复配置: {norm_mac}")
                return self._backups[norm_mac]["data"]

            # 尝试文件
            backup_file = CONFIG_BACKUP_DIR / f"{norm_mac.replace(':', '')}_backup.json"
            if backup_file.exists():
                with open(backup_file, "r", encoding="utf-8") as f:
                    backup = json.load(f)
                self._backups[norm_mac] = {
                    "data": backup["config"],
                    "timestamp": backup.get("timestamp", _now_iso()),
                }
                log.info(f"从文件恢复配置: {norm_mac} -> {backup_file}")
                return backup["config"]

            log.warning(f"配置恢复失败，无备份: {norm_mac}")
            return None

    # ============================================================
    # Persistence
    # ============================================================

    def _save(self) -> None:
        """持久化数据到 JSON 文件。"""
        with self._lock:
            devices_data = [d.model_dump() for d in self._devices.values()]
            groups_data = []
            for g in self._groups.values():
                gd = g.model_dump()
                gd["mac_addresses"] = list(gd["mac_addresses"])
                groups_data.append(gd)

            data = {
                "version": "1.0",
                "updated_at": _now_iso(),
                "devices": devices_data,
                "groups": groups_data,
            }

            tmp_path = self._storage_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(self._storage_path)

    def _load(self) -> None:
        """从 JSON 文件加载设备数据。"""
        if not self._storage_path.exists():
            log.info(f"设备存储文件不存在，初始化空状态: {self._storage_path}")
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for d in data.get("devices", []):
                mac = _normalize_mac(d.get("mac", ""))
                if mac:
                    self._devices[mac] = Device(**d)

            for g in data.get("groups", []):
                grp = DeviceGroup(**g)
                grp.mac_addresses = {str(m) for m in g.get("mac_addresses", [])}
                self._groups[g["name"]] = grp

            log.info(f"加载设备数据: {len(self._devices)} 台设备, {len(self._groups)} 个分组")
        except Exception as e:
            log.warning(f"加载设备数据失败，使用空状态: {e}")
