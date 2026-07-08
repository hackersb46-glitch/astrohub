"""
AstroHub v2.0 - 设备配置管理

统一管理设备配置：
- 当前设备标记: data/device_config.json (current_device 字段)
- 设备详细信息: data/devices/{MAC}.json (与 config_writer.py 共用)
- IP/MAC/型号等信息从单设备配置文件读写

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 当前设备标记文件（仅存储 current_device + 索引）
CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "device_config.json"
# 单设备配置目录（与 config_writer.py 共用）
DEVICES_DIR = Path(__file__).parent.parent.parent / "data" / "devices"


def _normalize_mac(mac: str) -> str:
    """统一 MAC 格式：转大写，横杠置换为冒号。"""
    return mac.strip().replace("-", ":").upper()


def _mac_to_config_key(mac: str) -> str:
    """MAC 转为 config索引键：无分隔符，小写。"""
    return mac.replace(":", "").lower()


def ensure_config() -> Path:
    """确保配置文件和设备目录存在。"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEVICES_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        save_config({"current_device": None, "devices": {}})
    return CONFIG_FILE


def load_config() -> dict[str, Any]:
    """加载当前设备标记配置。"""
    ensure_config()
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict[str, Any]) -> None:
    """保存当前设备标记配置。"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _load_device_file(mac: str) -> dict[str, Any] | None:
    """从 data/devices/{MAC}.json 读取单设备配置。"""
    norm_mac = _normalize_mac(mac)
    config_path = DEVICES_DIR / f"{norm_mac}.json"
    if not config_path.exists():
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_device_file(mac: str, data: dict[str, Any]) -> None:
    """写入 data/devices/{MAC}.json 单设备配置。"""
    DEVICES_DIR.mkdir(parents=True, exist_ok=True)
    norm_mac = _normalize_mac(mac)
    config_path = DEVICES_DIR / f"{norm_mac}.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_current_device() -> dict[str, Any] | None:
    """获取当前设备信息。

    从 device_config.json 读取 current_device 标记，
    再从 data/devices/{MAC}.json 读取完整设备信息。
    """
    config = load_config()
    current_mac = config.get("current_device")
    if not current_mac:
        return None

    # 优先从单设备配置文件读取
    device_data = _load_device_file(current_mac)
    if device_data is not None:
        return device_data

    # 回退到索引中的基本信息
    return config.get("devices", {}).get(current_mac)


def set_current_device(mac: str, ip: str = "", model: str = "", port: int = 80, username: str = "", password: str = "") -> None:
    """设置当前设备。

    同时更新:
    1. device_config.json 的 current_device 标记
    2. data/devices/{MAC}.json 的完整设备信息
    """
    config = load_config()
    config_key = _mac_to_config_key(mac)

    # 更新索引
    config["current_device"] = config_key
    if config_key not in config.get("devices", {}):
        config.setdefault("devices", {})[config_key] = {}
    config["devices"][config_key]["mac"] = config_key
    if ip:
        config["devices"][config_key]["ip"] = ip
    if model:
        config["devices"][config_key]["model"] = model
    config["devices"][config_key]["port"] = port
    if username:
        config["devices"][config_key]["username"] = username
    if password:
        config["devices"][config_key]["password"] = password

    # 更新单设备配置文件
    norm_mac = _normalize_mac(mac)
    device_data = _load_device_file(norm_mac) or {
        "mac": norm_mac,
        "ip": ip,
        "port": port,
        "model": model or "",
    }
    if ip:
        device_data["ip"] = ip
    if model:
        device_data["model"] = model
    if port:
        device_data["port"] = port
    if username:
        device_data["username"] = username
    if password:
        device_data["password"] = password
    _save_device_file(norm_mac, device_data)

    # 保存索引
    save_config(config)


def update_device_info(mac: str, **kwargs) -> None:
    """更新设备信息。

    同时更新 device_config.json 索引和 data/devices/{MAC}.json。
    """
    config_key = _mac_to_config_key(mac)
    config = load_config()

    # 更新索引
    if config_key not in config.get("devices", {}):
        config.setdefault("devices", {})[config_key] = {"mac": config_key}
    config["devices"][config_key].update(kwargs)
    save_config(config)

    # 更新单设备配置文件
    norm_mac = _normalize_mac(mac)
    device_data = _load_device_file(norm_mac)
    if device_data is not None:
        device_data.update(kwargs)
        _save_device_file(norm_mac, device_data)


def list_devices() -> list[dict[str, Any]]:
    """列出所有历史设备。

    合并索引和单设备配置文件的信息。
    """
    config = load_config()
    results = []
    for config_key, index_info in config.get("devices", {}).items():
        # 优先使用单设备配置文件
        norm_mac = _normalize_mac(config_key)
        device_data = _load_device_file(norm_mac)
        if device_data is not None:
            results.append(device_data)
        else:
            results.append(index_info)
    return results


def get_device_by_mac(mac: str) -> dict[str, Any] | None:
    """根据MAC获取设备信息。

    优先从 data/devices/{MAC}.json 读取。
    """
    norm_mac = _normalize_mac(mac)
    device_data = _load_device_file(norm_mac)
    if device_data is not None:
        return device_data

    # 回退到索引
    config_key = _mac_to_config_key(mac)
    config = load_config()
    return config.get("devices", {}).get(config_key)