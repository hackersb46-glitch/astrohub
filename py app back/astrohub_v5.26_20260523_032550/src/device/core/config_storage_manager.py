"""
M2 Device Manager v1.0 - 设备配置存储管理器

实现以 MAC 为键的分区 JSON 配置存储。
包含 device_info/capabilities/limits/calibration/onboarding 分区。
支持多设备配置隔离、启动时自动加载、配置变更后 100ms 内持久化。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Timer
from typing import Any

from device.constants import DATA_DIR
from device.core.logger import LOG
from device.core.mac_utils import normalize_mac

# 配置存储分区定义
CONFIG_SECTIONS = [
    "device_info",
    "capabilities",
    "limits",
    "calibration",
    "onboarding",
]


class ConfigStorageManager:
    """设备配置存储管理器。

    以 MAC 地址为分区键，每台设备的配置独立存储在 JSON 文件中。
    每个配置包含 5 个标准分区：device_info、capabilities、limits、calibration、onboarding。
    支持配置变更后 100ms 内自动持久化，启动时自动加载所有设备配置。

    Args:
        config_dir: 配置存储目录，默认使用 DATA_DIR/configs
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        self._config_dir = Path(config_dir) if config_dir is not None else DATA_DIR / "configs"
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._config_cache: dict[str, dict] = {}  # MAC -> 完整配置
        self._pending_changes: dict[str, Timer] = {}  # MAC -> 延迟写入定时器
        self._change_debounce_ms = 100  # 100ms 防抖

        # 启动时自动加载
        self._load_all_configs()
        LOG.info(f"ConfigStorageManager 初始化完成: dir={self._config_dir}")

    # ------------------------------------------------------------------ #
    #  配置分区路径
    # ------------------------------------------------------------------ #

    def _get_config_path(self, mac: str) -> Path:
        """获取设备配置文件路径 (按 MAC 分区)。

        Args:
            mac: 设备 MAC 地址

        Returns:
            配置文件完整路径
        """
        norm_mac = normalize_mac(mac).replace(":", "-")
        return self._config_dir / f"config_{norm_mac}.json"

    # ------------------------------------------------------------------ #
    #  启动时自动加载
    # ------------------------------------------------------------------ #

    def _load_all_configs(self) -> int:
        """启动时自动加载所有设备配置。

        扫描配置目录下的所有 config_*.json 文件并加载到内存缓存。

        Returns:
            成功加载的配置数量
        """
        loaded_count = 0
        if not self._config_dir.exists():
            LOG.info("配置目录不存在，跳过加载")
            return 0

        for config_file in self._config_dir.glob("config_*.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)

                # 从文件名提取 MAC
                filename = config_file.stem  # config_AA-BB-CC-DD-EE-FF
                mac_part = filename.replace("config_", "")
                loaded_mac = mac_part.replace("-", ":")
                norm_mac = normalize_mac(loaded_mac)

                self._config_cache[norm_mac] = config
                loaded_count += 1
                LOG.info(f"配置已加载: {norm_mac}")
            except Exception as e:
                LOG.warning(f"配置加载失败: {config_file} - {e}")

        LOG.info(f"启动时自动加载完成: {loaded_count} 个设备配置")
        return loaded_count

    # ------------------------------------------------------------------ #
    #  配置初始化
    # ------------------------------------------------------------------ #

    def _create_default_config(self, mac: str) -> dict:
        """创建设备默认配置结构，包含所有分区。

        Args:
            mac: 设备 MAC 地址

        Returns:
            包含完整分区结构的默认配置
        """
        norm_mac = normalize_mac(mac)
        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        return {
            "meta": {
                "mac": norm_mac,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            },
            "device_info": {
                "mac": norm_mac,
                "ip": "",
                "port": 80,
                "model": "",
                "serial_number": "",
                "firmware_version": "",
                "status": "new",
                "heartbeat_status": "offline",
            },
            "capabilities": {
                "ptz": {
                    "pan_range": [-180, 180],
                    "tilt_range": [-30, 90],
                    "zoom_range": [1, 100],
                    "speed_levels": [1, 50, 100],
                },
                "video": {
                    "resolution": "1920x1080",
                    "fps": 30,
                    "codec": "H.264",
                },
                "network": {
                    "protocols": ["RTSP", "HTTP", "ONVIF"],
                    "max_connections": 10,
                },
            },
            "limits": {
                "max_preset_positions": 255,
                "max_patrol_sequences": 10,
                "max_cruise_time_minutes": 1440,
                "max_calibration_retries": 3,
            },
            "calibration": {
                "speed_mapping": {
                    "calibrated": False,
                    "curve_params": {},
                    "calibration_data": [],
                    "last_calibrated_at": "",
                },
                "white_balance": {
                    "calibrated": False,
                    "wb_params": {},
                    "last_calibrated_at": "",
                },
                "position": {
                    "calibrated": False,
                    "compensation_table": {},
                    "last_calibrated_at": "",
                },
            },
            "onboarding": {
                "discovered": False,
                "discovered_at": "",
                "activated": False,
                "activated_at": "",
                "initial_setup_completed": False,
                "setup_completed_at": "",
            },
        }

    # ------------------------------------------------------------------ #
    #  获取配置
    # ------------------------------------------------------------------ #

    def get_config(self, mac: str) -> dict | None:
        """获取设备的完整配置。

        Args:
            mac: 设备 MAC 地址

        Returns:
            完整配置字典，不存在时返回 None
        """
        norm_mac = normalize_mac(mac)

        # 优先从缓存读取
        if norm_mac in self._config_cache:
            return self._config_cache[norm_mac]

        # 回退到文件读取
        config_path = self._get_config_path(norm_mac)
        if not config_path.exists():
            return None

        with self._lock:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self._config_cache[norm_mac] = config
                return config
            except Exception as e:
                LOG.error(f"配置读取失败: {norm_mac} - {e}")
                return None

    def get_section(self, mac: str, section: str) -> dict | None:
        """获取设备配置的指定分区。

        Args:
            mac: 设备 MAC 地址
            section: 分区名称 (device_info/capabilities/limits/calibration/onboarding)

        Returns:
            分区数据字典，分区不存在时返回 None
        """
        if section not in CONFIG_SECTIONS:
            LOG.warning(f"未知配置分区: {section} (合法值: {', '.join(CONFIG_SECTIONS)})")
            return None

        config = self.get_config(mac)
        if config is None:
            return None

        return config.get(section)

    def get_device_info(self, mac: str) -> dict | None:
        """获取设备信息分区。"""
        return self.get_section(mac, "device_info")

    def get_capabilities(self, mac: str) -> dict | None:
        """获取设备能力分区。"""
        return self.get_section(mac, "capabilities")

    def get_limits(self, mac: str) -> dict | None:
        """获取设备限制分区。"""
        return self.get_section(mac, "limits")

    def get_calibration(self, mac: str) -> dict | None:
        """获取设备校准分区。"""
        return self.get_section(mac, "calibration")

    def get_onboarding(self, mac: str) -> dict | None:
        """获取设备入网分区。"""
        return self.get_section(mac, "onboarding")

    # ------------------------------------------------------------------ #
    #  设置配置 (100ms 持久化)
    # ------------------------------------------------------------------ #

    def set_config(self, mac: str, config: dict) -> bool:
        """设置设备的完整配置。

        更新缓存并触发 100ms 防抖持久化。

        Args:
            mac: 设备 MAC 地址
            config: 完整配置字典

        Returns:
            True=成功, False=失败
        """
        norm_mac = normalize_mac(mac)

        # 更新 meta 信息
        if "meta" not in config:
            config["meta"] = {}
        config["meta"]["mac"] = norm_mac
        config["meta"]["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        if "version" not in config["meta"]:
            config["meta"]["version"] = 1
        else:
            config["meta"]["version"] += 1

        with self._lock:
            self._config_cache[norm_mac] = config

        # 触发延迟持久化 (100ms 内)
        self._schedule_persist(norm_mac)
        LOG.info(f"配置已更新 (缓存): {norm_mac} (v{config['meta'].get('version', '?')})")
        return True

    def set_section(self, mac: str, section: str, data: dict) -> bool:
        """更新设备配置的指定分区。

        支持部分更新 (merge) 或完全替换。

        Args:
            mac: 设备 MAC 地址
            section: 分区名称
            data: 分区数据 (将与现有数据 merge)

        Returns:
            True=成功, False=失败
        """
        if section not in CONFIG_SECTIONS:
            LOG.warning(f"未知配置分区: {section}")
            return False

        config = self.get_config(mac)
        if config is None:
            # 如果配置不存在，创建默认配置
            config = self._create_default_config(mac)

        # Merge 更新: 递归合并子分区
        if section in config:
            config[section] = self._deep_merge(config[section], data)
        else:
            config[section] = data

        return self.set_config(mac, config)

    def update_device_info(self, mac: str, data: dict) -> bool:
        """更新设备信息分区。"""
        return self.set_section(mac, "device_info", data)

    def update_capabilities(self, mac: str, data: dict) -> bool:
        """更新设备能力分区。"""
        return self.set_section(mac, "capabilities", data)

    def update_limits(self, mac: str, data: dict) -> bool:
        """更新设备限制分区。"""
        return self.set_section(mac, "limits", data)

    def update_calibration(self, mac: str, data: dict) -> bool:
        """更新设备校准分区。"""
        return self.set_section(mac, "calibration", data)

    def update_onboarding(self, mac: str, data: dict) -> bool:
        """更新设备入网分区。"""
        return self.set_section(mac, "onboarding", data)

    # ------------------------------------------------------------------ #
    #  持久化 (100ms 防抖)
    # ------------------------------------------------------------------ #

    def _schedule_persist(self, mac: str) -> None:
        """安排配置持久化，100ms 防抖。

        Args:
            mac: 设备 MAC 地址
        """
        norm_mac = normalize_mac(mac)

        # 取消之前的定时器 (如果存在)
        if norm_mac in self._pending_changes:
            self._pending_changes[norm_mac].cancel()

        # 创建新的定时器 (100ms 后执行)
        timer = Timer(self._change_debounce_ms / 1000.0, self._persist_config, args=(norm_mac,))
        timer.daemon = True
        timer.start()
        self._pending_changes[norm_mac] = timer

    def _persist_config(self, mac: str) -> None:
        """实际执行配置持久化。

        Args:
            mac: 设备 MAC 地址
        """
        norm_mac = normalize_mac(mac)

        with self._lock:
            config = self._config_cache.get(norm_mac)
            if config is None:
                return

            try:
                config_path = self._get_config_path(norm_mac)
                self._atomic_write(config_path, config)
                LOG.info(f"配置已持久化: {norm_mac} -> {config_path.name}")
            except Exception as e:
                LOG.error(f"配置持久化失败: {norm_mac} - {e}")
            finally:
                # 清理定时器引用
                self._pending_changes.pop(norm_mac, None)

    def persist_now(self, mac: str) -> bool:
        """立即持久化指定设备的配置 (不进行防抖等待)。

        Args:
            mac: 设备 MAC 地址

        Returns:
            True=成功, False=失败
        """
        norm_mac = normalize_mac(mac)

        # 取消等待中的防抖定时器
        if norm_mac in self._pending_changes:
            self._pending_changes[norm_mac].cancel()
            self._pending_changes.pop(norm_mac, None)

        with self._lock:
            config = self._config_cache.get(norm_mac)
            if config is None:
                return False

            try:
                config_path = self._get_config_path(norm_mac)
                self._atomic_write(config_path, config)
                LOG.info(f"配置立即持久化: {norm_mac} -> {config_path.name}")
                return True
            except Exception as e:
                LOG.error(f"配置立即持久化失败: {norm_mac} - {e}")
                return False

    def persist_all(self) -> int:
        """立即持久化所有设备的配置。

        Returns:
            成功持久化的配置数量
        """
        persisted_count = 0
        with self._lock:
            for mac, config in list(self._config_cache.items()):
                try:
                    config_path = self._get_config_path(mac)
                    self._atomic_write(config_path, config)
                    persisted_count += 1
                except Exception as e:
                    LOG.error(f"配置持久化失败: {mac} - {e}")

        LOG.info(f"全部配置持久化完成: {persisted_count} 个设备")
        return persisted_count

    # ------------------------------------------------------------------ #
    #  原子写入
    # ------------------------------------------------------------------ #

    def _atomic_write(self, path: Path, data: dict) -> None:
        """原子写入 JSON 配置，确保写入过程中数据完整性。

        Args:
            path: 目标文件路径
            data: 要写入的配置数据
        """
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
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

    # ------------------------------------------------------------------ #
    #  辅助方法
    # ------------------------------------------------------------------ #

    def _deep_merge(self, base: dict, update: dict) -> dict:
        """递归合并两个字典，update 的值覆盖 base 的值。

        Args:
            base: 基础字典
            update: 更新字典

        Returns:
            合并后的字典
        """
        result = base.copy()
        for key, value in update.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def ensure_config_exists(self, mac: str) -> dict:
        """确保设备配置存在，不存在则创建默认配置。

        Args:
            mac: 设备 MAC 地址

        Returns:
            设备完整配置字典
        """
        norm_mac = normalize_mac(mac)
        config = self.get_config(norm_mac)
        if config is None:
            config = self._create_default_config(norm_mac)
            self.set_config(norm_mac, config)
            # 立即持久化新配置
            self.persist_now(norm_mac)
            LOG.info(f"设备默认配置已创建: {norm_mac}")
        return config

    def delete_config(self, mac: str) -> bool:
        """删除设备的配置 (包含缓存和文件)。

        Args:
            mac: 设备 MAC 地址

        Returns:
            True=成功, False=失败
        """
        norm_mac = normalize_mac(mac)

        # 取消防抖定时器
        if norm_mac in self._pending_changes:
            self._pending_changes[norm_mac].cancel()
            self._pending_changes.pop(norm_mac, None)

        # 清除缓存
        with self._lock:
            self._config_cache.pop(norm_mac, None)

        # 删除文件
        config_path = self._get_config_path(norm_mac)
        if config_path.exists():
            try:
                config_path.unlink()
                LOG.done(f"设备配置已删除: {norm_mac}")
                return True
            except Exception as e:
                LOG.error(f"删除配置文件失败: {norm_mac} - {e}")
                return False

        return True  # 文件本就不存在也视为成功

    def list_configs(self) -> list[str]:
        """列出所有已加载配置的设备 MAC。

        Returns:
            MAC 地址列表
        """
        with self._lock:
            return list(self._config_cache.keys())

    def config_exists(self, mac: str) -> bool:
        """检查设备的配置是否存在 (缓存或文件)。

        Args:
            mac: 设备 MAC 地址

        Returns:
            True=存在, False=不存在
        """
        norm_mac = normalize_mac(mac)
        if norm_mac in self._config_cache:
            return True
        return self._get_config_path(norm_mac).exists()