"""
PTZ_ASTRO v1.1 - 配置管理模块
管理 local.json（本机信息）和 PTZ_config.json（设备信息列表），
支持原子写入、MAC地址查找、安全的 upsert 操作。

Author: 雅痞张@南方天文
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .logger import LOG


def _default_local() -> dict:
    """本地机器配置空模式。"""
    return {
        "hostname": "",
        "cpu_model": "",
        "ram_gb": 0,
        "gpu_count": 0,
        "vram_gb": 0,
        "gpu_names": [],
        "selected_nic": {
            "name": "",
            "ip": "",
            "netmask": "",
            "gateway": "",
        },
    }


def _default_ptz() -> dict:
    """设备配置空模式。"""
    return {"devices": {}}


def _normalize_mac(mac: str) -> str:
    """统一 MAC 格式：转大写，横杠置换为冒号。

    示例: aa-bb-cc-dd-ee-ff → AA:BB:CC:DD:EE:FF
    """
    return mac.strip().replace("-", ":").upper()


def _atomic_write(path: Path, data: dict) -> None:
    """通过 tempfile + os.replace() 安全写入 JSON 文件，保证原子性。"""
    path = path.resolve()
    dir_ = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        # 写入失败时清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class ConfigManager:
    """本地配置 + 设备配置管理器，支持原子写入与 MAC 查找。"""

    def __init__(self, local_path: Path, ptz_path: Path) -> None:
        self.local_path = local_path.resolve()
        self.ptz_path = ptz_path.resolve()
        LOG.log("info", f"初始化 ConfigManager: local={self.local_path}, ptz={self.ptz_path}")
        self.create_defaults()

    # ------------------------------------------------------------------ #
    #  创建默认配置文件
    # ------------------------------------------------------------------ #
    def create_defaults(self) -> None:
        """如果配置文件不存在，则创建带空模式的 JSON 文件。"""
        if not self.local_path.exists():
            _atomic_write(self.local_path, _default_local())
            LOG.log("done", f"创建本地配置文件: {self.local_path}")
        else:
            LOG.log("info", f"本地配置文件已存在: {self.local_path}")

        if not self.ptz_path.exists():
            _atomic_write(self.ptz_path, _default_ptz())
            LOG.log("done", f"创建设备配置文件: {self.ptz_path}")
        else:
            LOG.log("info", f"设备配置文件已存在: {self.ptz_path}")

    # ------------------------------------------------------------------ #
    #  local.json 读写
    # ------------------------------------------------------------------ #
    def load_local(self) -> dict:
        """读取 local.json 并返回字典。"""
        LOG.log("info", f"加载本地配置: {self.local_path}")
        with open(self.local_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        LOG.log("done", f"本地配置加载成功")
        return data

    def save_local(self, data: dict) -> None:
        """原子方式写入 local.json。"""
        LOG.log("info", f"保存本地配置: {self.local_path}")
        _atomic_write(self.local_path, data)
        LOG.log("done", f"本地配置保存成功")

    # ------------------------------------------------------------------ #
    #  PTZ_config.json 读写
    # ------------------------------------------------------------------ #
    def load_ptz_config(self) -> dict:
        """读取 PTZ_config.json 并返回字典。"""
        LOG.log("info", f"加载设备配置: {self.ptz_path}")
        with open(self.ptz_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        LOG.log("done", f"设备配置加载成功")
        return data

    def save_ptz_config(self, data: dict) -> None:
        """原子方式写入 PTZ_config.json。"""
        LOG.log("info", f"保存设备配置: {self.ptz_path}")
        _atomic_write(self.ptz_path, data)
        LOG.log("done", f"设备配置保存成功")

    # ------------------------------------------------------------------ #
    #  设备 CRUD（MAC 查找 / 插入更新 / 删除）
    # ------------------------------------------------------------------ #
    def get_device_by_mac(self, mac: str) -> dict | None:
        """通过 MAC 地址查找设备（大小写无关，格式标准化后查找）。"""
        norm_mac = _normalize_mac(mac)
        LOG.log("info", f"查找设备 MAC: {mac} → {norm_mac}")
        config = self.load_ptz_config()
        device = config.get("devices", {}).get(norm_mac)
        if device is None:
            LOG.log("info", f"未找到 MAC: {norm_mac}")
        else:
            LOG.log("done", f"找到设备 MAC: {norm_mac}")
        return device

    def upsert_device(self, mac: str, info: dict) -> None:
        """插入或更新设备信息，自动设置 last_updated 时间戳。

        参数:
            mac: MAC 地址，支持横杠或冒号分隔格式
            info: 设备信息字典（不含 mac 字段时将自动注入）
        """
        norm_mac = _normalize_mac(mac)
        LOG.log("info", f"upsert 设备 MAC: {mac} → {norm_mac}")

        config = self.load_ptz_config()
        devices = config.setdefault("devices", {})

        # 注入 MAC 地址（规范化格式）
        info["mac"] = norm_mac

        # 设置更新时间
        info["last_updated"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        is_update = norm_mac in devices
        devices[norm_mac] = info

        self.save_ptz_config(config)

        action = "更新" if is_update else "新增"
        LOG.log("done", f"{action}设备成功: {norm_mac}")

    def remove_device(self, mac: str) -> bool:
        """通过 MAC 地址移除设备，成功返回 True，未找到返回 False。"""
        norm_mac = _normalize_mac(mac)
        LOG.log("info", f"移除设备 MAC: {mac} → {norm_mac}")

        config = self.load_ptz_config()
        devices = config.get("devices", {})

        if norm_mac not in devices:
            LOG.log("info", f"设备不存在，移除跳过: {norm_mac}")
            return False

        del devices[norm_mac]
        config["devices"] = devices
        self.save_ptz_config(config)

        LOG.log("done", f"移除设备成功: {norm_mac}")
        return True
