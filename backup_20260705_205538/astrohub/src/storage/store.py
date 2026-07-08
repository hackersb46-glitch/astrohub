"""
AstroHub v2.0 - 数据存储模块

提供统一的数据存储接口，支持多设备管理。
路径基于项目根目录动态计算，不硬编码。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


class DataStore:
    """数据存储管理器。

    目录结构:
        data/
        ├── config.json          # 全局配置
        ├── registry.json        # 设备注册表
        └── devices/
            └── {device_id}/     # 设备目录
                ├── info.json
                ├── status.json
                ├── function.json
                ├── limit.json
                ├── speed.json
                ├── calibration.json
                └── presets.json
    """

    def __init__(self, base_dir: Path | str | None = None):
        """初始化数据存储。

        Args:
            base_dir: 项目根目录。默认自动检测（src/storage 的上级上级）。
        """
        if base_dir is None:
            # 自动定位：src/storage -> src -> astrohub
            base_dir = Path(__file__).parent.parent.parent
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.devices_dir = self.data_dir / "devices"

        # 确保目录存在
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """确保必要目录存在。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.devices_dir.mkdir(parents=True, exist_ok=True)

    # ==================== 全局配置 ====================

    def get_config(self) -> dict:
        """获取全局配置。"""
        config_path = self.data_dir / "config.json"
        if not config_path.exists():
            return self._default_config()
        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._default_config()

    def update_config(self, key: str, value: Any) -> None:
        """更新全局配置项。"""
        config = self.get_config()
        config[key] = value
        config["updated"] = datetime.now().isoformat()
        self._write_json(self.data_dir / "config.json", config)

    def _default_config(self) -> dict:
        """默认配置。"""
        return {
            "version": "5.29",
            "server": {"port": 10280, "host": "0.0.0.0"},
            "network": {"selected_interface": "", "local_ip": ""},
            "defaults": {"username": "admin", "password": "", "port": 80},
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
        }

    # ==================== 设备注册表 ====================

    def get_registry(self) -> dict:
        """获取设备注册表。"""
        registry_path = self.data_dir / "registry.json"
        if not registry_path.exists():
            return {"devices": {}, "last_connected": None}
        try:
            with open(registry_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"devices": {}, "last_connected": None}

    def _save_registry(self, registry: dict) -> None:
        """保存设备注册表。"""
        self._write_json(self.data_dir / "registry.json", registry)

    def register_device(
        self,
        mac: str,
        ip: str,
        model: str,
        credentials: dict | None = None,
        name: str = "",
    ) -> str:
        """注册新设备。

        Args:
            mac: MAC地址（唯一标识）
            ip: IP地址
            model: 设备型号
            credentials: 凭证 {"username": "", "password": ""}
            name: 设备名称

        Returns:
            设备ID
        """
        mac = mac.upper().replace(":", "-")
        registry = self.get_registry()

        # 已存在则更新
        if mac in registry["devices"]:
            device_id = registry["devices"][mac]["id"]
            registry["devices"][mac].update({
                "ip": ip,
                "model": model,
                "last_seen": datetime.now().isoformat(),
            })
            self._save_registry(registry)
            self._update_device_info(device_id, ip, model, credentials)
            return device_id

        # 新设备：生成ID
        device_id = self._generate_device_id(registry)

        registry["devices"][mac] = {
            "id": device_id,
            "name": name or f"设备{device_id[-3:]}",
            "model": model,
            "ip": ip,
            "last_seen": datetime.now().isoformat(),
        }

        # 首个设备自动设为活跃
        if len(registry["devices"]) == 1:
            registry["last_connected"] = device_id

        self._save_registry(registry)
        self._create_device_dir(device_id, mac, ip, model, credentials)

        return device_id

    def _generate_device_id(self, registry: dict) -> str:
        """生成设备ID。"""
        existing_ids = [d["id"] for d in registry["devices"].values()]
        num = 1
        while f"dev_{num:03d}" in existing_ids:
            num += 1
        return f"dev_{num:03d}"

    def _create_device_dir(
        self,
        device_id: str,
        mac: str,
        ip: str,
        model: str,
        credentials: dict | None,
    ) -> None:
        """创建设备目录和初始文件。"""
        mac_clean = mac.replace(':', '').lower()
        device_dir = self.devices_dir / mac_clean
        device_dir.mkdir(parents=True, exist_ok=True)

        info = {
            "id": device_id,
            "mac": mac,
            "ip": ip,
            "port": credentials.get("port", 80) if credentials else 80,
            "model": model,
            "serial": "",
            "firmware": "",
            "credentials": {
                "username": credentials.get("username", "admin") if credentials else "admin",
                "password": credentials.get("password", "") if credentials else "",
            },
            "channels": 1,
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
        }
        self._write_json(device_dir / "info.json", info)

        # 初始化空文件
        self._write_json(device_dir / "function.json", {
            "device_id": device_id,
            "detected_at": None,
            "summary": {"total": 0, "supported": 0, "modifiable": 0},
            "results": {},
        })
        self._write_json(device_dir / "limit.json", {
            "device_id": device_id,
            "tested_at": None,
            "results": {},
        })
        self._write_json(device_dir / "speed.json", {
            "device_id": device_id,
            "tested_at": None,
            "results": {},
        })

    def _update_device_info(
        self,
        device_id: str,
        ip: str,
        model: str,
        credentials: dict | None,
    ) -> None:
        """更新设备信息。"""
        info = self.get_device_info(device_id)
        if info:
            info["ip"] = ip
            info["model"] = model
            info["updated"] = datetime.now().isoformat()
            if credentials:
                info["credentials"] = {
                    "username": credentials.get("username", "admin"),
                    "password": credentials.get("password", ""),
                }
            self._write_json(self.devices_dir / device_id / "info.json", info)

    def get_device(self, mac: str) -> dict | None:
        """通过MAC获取设备信息。"""
        mac = mac.upper().replace(":", "-")
        registry = self.get_registry()
        if mac not in registry["devices"]:
            return None
        device_id = registry["devices"][mac]["id"]
        return self.get_device_info(device_id)

    def get_device_info(self, device_id: str) -> dict | None:
        """获取设备详细信息。"""
        info_path = self.devices_dir / device_id / "info.json"
        if not info_path.exists():
            return None
        try:
            with open(info_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def list_devices(self) -> list[dict]:
        """列出所有设备。"""
        registry = self.get_registry()
        devices = []
        for mac, info in registry["devices"].items():
            device_info = self.get_device_info(info["id"])
            if device_info:
                device_info["mac"] = mac
                devices.append(device_info)
        return devices

    def set_active_device(self, mac: str) -> None:
        """设置活跃设备。"""
        mac = mac.upper().replace(":", "-")
        registry = self.get_registry()
        if mac in registry["devices"]:
            registry["last_connected"] = registry["devices"][mac]["id"]
            self._save_registry(registry)

    def get_active_device(self) -> dict | None:
        """获取当前活跃设备。"""
        registry = self.get_registry()
        device_id = registry.get("last_connected")
        if device_id:
            return self.get_device_info(device_id)
        return None

    # ==================== 功能探测 ====================

    def save_function_results(self, device_id: str, results: dict) -> None:
        """保存功能探测结果。"""
        function_path = self.devices_dir / device_id / "function.json"

        # 计算摘要
        supported = sum(1 for r in results.values() if r.get("supported"))
        modifiable = sum(
            1 for r in results.values()
            if r.get("supported") and any(
                t.get("success", False) for t in r.get("test_results", [])
            )
        )

        data = {
            "device_id": device_id,
            "detected_at": datetime.now().isoformat(),
            "summary": {
                "total": len(results),
                "supported": supported,
                "modifiable": modifiable,
            },
            "results": results,
        }
        self._write_json(function_path, data)

    def get_function_results(self, device_id: str) -> dict | None:
        """获取功能探测结果。"""
        function_path = self.devices_dir / device_id / "function.json"
        if not function_path.exists():
            return None
        try:
            with open(function_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    # ==================== 限位测试 ====================

    def save_limit_results(self, device_id: str, results: dict) -> None:
        """保存限位测试结果。"""
        limit_path = self.devices_dir / device_id / "limit.json"
        data = {
            "device_id": device_id,
            "tested_at": datetime.now().isoformat(),
            "results": results,
        }
        self._write_json(limit_path, data)

    def get_limit_results(self, device_id: str) -> dict | None:
        """获取限位测试结果。"""
        limit_path = self.devices_dir / device_id / "limit.json"
        if not limit_path.exists():
            return None
        try:
            with open(limit_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    # ==================== 速度测试 ====================

    def save_speed_results(self, device_id: str, results: dict) -> None:
        """保存速度测试结果。"""
        speed_path = self.devices_dir / device_id / "speed.json"
        data = {
            "device_id": device_id,
            "tested_at": datetime.now().isoformat(),
            "results": results,
        }
        self._write_json(speed_path, data)

    def get_speed_results(self, device_id: str) -> dict | None:
        """获取速度测试结果。"""
        speed_path = self.devices_dir / device_id / "speed.json"
        if not speed_path.exists():
            return None
        try:
            with open(speed_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    # ==================== 工具方法 ====================

    def _write_json(self, path: Path, data: dict) -> None:
        """写入JSON文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def migrate_from_old_config(self) -> None:
        """从旧的 device_config.json 迁移数据。"""
        old_path = self.base_dir / "src" / "advanced" / "device_config.json"
        if not old_path.exists():
            return

        try:
            with open(old_path, encoding="utf-8") as f:
                old_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        # 迁移 function_detection
        function_detection = old_data.get("function_detection", {})
        if function_detection:
            # 尝试从注册表获取设备ID
            registry = self.get_registry()
            active_id = registry.get("last_connected")
            if active_id:
                self.save_function_results(active_id, function_detection)

        # 备份旧文件
        backup_path = old_path.with_suffix(".json.bak")
        old_path.rename(backup_path)


# 单例
_store: DataStore | None = None


def get_store() -> DataStore:
    """获取数据存储单例。"""
    global _store
    if _store is None:
        _store = DataStore()
    return _store
