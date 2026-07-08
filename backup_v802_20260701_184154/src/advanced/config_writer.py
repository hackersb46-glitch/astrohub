"""
AstroHub v2.0 - 设备 Config 写入模块

将功能探测/限位测试/速度测试结果写入设备 config 文件。
保存到 data/devices/{mac}.json

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config_paths import DATA_DIR


DEVICES_DIR = DATA_DIR / "devices"


@dataclass
class DeviceConfig:
    """设备配置数据结构。"""
    mac: str = ""
    ip: str = ""
    port: int = 80
    username: str = "admin"
    password: str = ""
    model: str = ""
    serial_number: str = ""
    firmware_version: str = ""
    first_seen: str = ""
    last_updated: str = ""
    capabilities: dict = field(default_factory=dict)
    limits: dict = field(default_factory=dict)
    speed: dict = field(default_factory=dict)
    onboarding_complete: bool = False
    onboarding_started: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _atomic_write(path: Path, data: dict) -> None:
    """通过 tempfile + os.replace() 安全写入 JSON 文件，保证原子性。"""
    path = path.resolve()
    dir_ = path.parent
    dir_.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _normalize_mac(mac: str) -> str:
    """统一 MAC 格式：转大写，横杠置换为冒号。"""
    return mac.strip().replace("-", ":").upper()


def load_device_config(mac: str) -> DeviceConfig | None:
    """加载设备配置文件。"""
    norm_mac = _normalize_mac(mac)
    config_path = DEVICES_DIR / f"{norm_mac}.json"

    if not config_path.exists():
        return None

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return DeviceConfig.from_dict(data)


def save_device_config(config: DeviceConfig) -> None:
    """保存设备配置文件。"""
    norm_mac = _normalize_mac(config.mac)
    config_path = DEVICES_DIR / f"{norm_mac}.json"
    config.last_updated = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    _atomic_write(config_path, config.to_dict())


def write_device_config(
    mac: str,
    capabilities: dict | None = None,
    limits: dict | None = None,
    speed: dict | None = None,
    ip: str = "",
    port: int = 80,
    username: str = "admin",
    password: str = "",
    model: str = "",
    serial_number: str = "",
    firmware_version: str = "",
) -> dict:
    """将测试结果写入设备 config 文件。

    步骤:
    1. 读取或创建设备 config
    2. 更新 capabilities/limits/speed 字段
    3. 保存到 data/devices/{mac}.json
    4. 返回写入结果

    返回:
        {"success": bool, "path": str, "message": str}
    """
    norm_mac = _normalize_mac(mac)
    config_path = DEVICES_DIR / f"{norm_mac}.json"

    # 读取已有配置或创建新配置
    existing = load_device_config(norm_mac)
    if existing:
        config = existing
    else:
        config = DeviceConfig(
            mac=norm_mac,
            ip=ip,
            first_seen=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        )

    # 更新基本信息
    if ip:
        config.ip = ip
    if port:
        config.port = port
    if username:
        config.username = username
    if password:
        config.password = password
    if model:
        config.model = model
    if serial_number:
        config.serial_number = serial_number
    if firmware_version:
        config.firmware_version = firmware_version

    # 更新测试结果
    if capabilities is not None:
        config.capabilities = capabilities
    if limits is not None:
        config.limits = limits
    if speed is not None:
        config.speed = speed

    # 保存
    try:
        save_device_config(config)
        return {
            "success": True,
            "path": str(config_path),
            "message": f"设备配置已保存: {norm_mac}",
            "config": config.to_dict(),
        }
    except Exception as e:
        return {
            "success": False,
            "path": str(config_path),
            "message": f"保存失败: {e}",
        }


def list_device_configs() -> list[dict]:
    """列出所有已保存的设备配置。"""
    if not DEVICES_DIR.exists():
        return []

    configs = []
    for config_file in DEVICES_DIR.glob("*.json"):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            configs.append(data)
        except Exception:
            pass

    return configs


def delete_device_config(mac: str) -> bool:
    """删除设备配置文件。"""
    norm_mac = _normalize_mac(mac)
    config_path = DEVICES_DIR / f"{norm_mac}.json"

    if config_path.exists():
        config_path.unlink()
        return True
    return False
