"""
M2 Device Manager v1.0 - 配置差异比较与版本管理

提供配置差异比较(ConfigDiffer)和配置版本管理(ConfigVersionManager)功能。
支持递归嵌套dict/list比较、版本快照保存/回滚、自动版本裁剪。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from device.constants import BACKUP_DIR, CONFIG_VERSION_FILENAME, CONFIG_VERSION_MAX_COUNT
from device.core.logger import LOG
from device.core.storage import _atomic_write


# ------------------------------------------------------------------ #
#  P2.5 - ConfigDiffer
# ------------------------------------------------------------------ #

class ConfigDiffer:
    """配置差异比较器，递归比较两个嵌套配置字典并返回差异列表。

    路径格式:
        - 嵌套字典使用点号分隔: "network.dns.primary"
        - 列表索引使用方括号: "channels[0].name"

    差异类型:
        - added:    old_value 为 None (标记 {"type": "added"})
        - removed:  new_value 为 None (标记 {"type": "removed"})
        - modified: 旧值和新值均存在 (标记 {"type": "modified"})
    """

    @staticmethod
    def compare(old_config: dict, new_config: dict) -> list[dict]:
        """递归比较两个配置字典，返回所有差异。

        Args:
            old_config: 原始配置字典
            new_config: 新配置字典

        Returns:
            差异列表，每个元素为 {"path": ..., "old_value": ..., "new_value": ...}
            空列表表示两个配置完全相同。
        """
        diffs: list[dict] = []
        ConfigDiffer._compare_recursive(old_config, new_config, "", diffs)
        return diffs

    @staticmethod
    def _compare_recursive(old: Any, new: Any, path: str, diffs: list[dict]) -> None:
        """递归比较两个值(可以是dict, list, 或primitive)。

        Args:
            old: 旧值
            new: 新值
            path: 当前路径(点号/方括号分隔)
            diffs: 差异结果收集列表(就地修改)
        """
        # --- 类型不同或同为叶子 ---
        if type(old) is not type(new):
            # 特殊处理: 同为 None 视为相等
            if old is None and new is None:
                return
            diffs.append({
                "path": path,
                "old_value": old,
                "new_value": new,
                "type": "modified",
            })
            return

        # --- 嵌套字典 ---
        if isinstance(old, dict):
            all_keys = set(old.keys()) | set(new.keys())
            for key in sorted(all_keys):
                child_path = f"{path}.{key}" if path else key
                if key not in old:
                    diffs.append({
                        "path": child_path,
                        "old_value": None,
                        "new_value": new[key],
                        "type": "added",
                    })
                elif key not in new:
                    diffs.append({
                        "path": child_path,
                        "old_value": old[key],
                        "new_value": None,
                        "type": "removed",
                    })
                else:
                    ConfigDiffer._compare_recursive(old[key], new[key], child_path, diffs)
            return

        # --- 列表 ---
        if isinstance(old, list):
            max_len = max(len(old), len(new))
            for i in range(max_len):
                child_path = f"{path}[{i}]" if path else f"[{i}]"
                if i >= len(old):
                    diffs.append({
                        "path": child_path,
                        "old_value": None,
                        "new_value": new[i],
                        "type": "added",
                    })
                elif i >= len(new):
                    diffs.append({
                        "path": child_path,
                        "old_value": old[i],
                        "new_value": None,
                        "type": "removed",
                    })
                else:
                    ConfigDiffer._compare_recursive(old[i], new[i], child_path, diffs)
            return

        # --- 叶子值 ---
        if old != new:
            diffs.append({
                "path": path,
                "old_value": old,
                "new_value": new,
                "type": "modified",
            })


# ------------------------------------------------------------------ #
#  P2.6 - ConfigVersionManager
# ------------------------------------------------------------------ #

class ConfigVersionManager:
    """配置版本管理器，支持快照保存、版本查询、回滚和自动裁剪。

    快照文件命名: config_{mac}_{version}_{timestamp}.json
    版本号格式: v{N} (v1, v2, ...)
    自动裁剪: 超过 CONFIG_VERSION_MAX_COUNT 时删除最旧版本。

    Args:
        mac: 设备MAC地址
        backup_dir: 备份目录，默认使用 constants.BACKUP_DIR
    """

    def __init__(self, mac: str, backup_dir: Path | str = None) -> None:
        self.mac = mac
        self.backup_dir = Path(backup_dir) if backup_dir else BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._next_version = self._compute_next_version()
        LOG.info(f"配置版本管理器已初始化: mac={mac}, dir={self.backup_dir}")

    # ------------------------------------------------------------------ #
    #  内部辅助
    # ------------------------------------------------------------------ #
    def _compute_next_version(self) -> int:
        """扫描现有快照文件，计算下一个版本号。

        Returns:
            下一个整数版本号(从1开始)
        """
        existing = self._list_snapshot_files()
        if not existing:
            return 1
        max_v = 0
        for info in existing:
            match = re.match(r"v(\d+)$", info["version"])
            if match:
                max_v = max(max_v, int(match.group(1)))
        return max_v + 1

    def _list_snapshot_files(self) -> list[dict]:
        """列出当前备份目录中属于此MAC的快照文件。

        Returns:
            排序后的版本信息列表
        """
        pattern = re.compile(
            r"^config_"
            + re.escape(self._sanitize_mac())
            + r"_(v\d+)_(\d{8}_\d{6})\.json$"
        )
        results: list[dict] = []
        if not self.backup_dir.exists():
            return results
        for entry in self.backup_dir.iterdir():
            if entry.is_file():
                m = pattern.match(entry.name)
                if m:
                    results.append({
                        "version": m.group(1),
                        "timestamp": m.group(2),
                        "filename": entry.name,
                        "num": int(m.group(1)[1:]),
                    })
        results.sort(key=lambda x: x["num"])
        return results

    def _sanitize_mac(self) -> str:
        """将MAC地址中的特殊字符替换为连字符，确保文件名合法。

        Returns:
            安全的MAC地址字符串(如 "AA-BB-CC-DD-EE-FF")
        """
        return self.mac.replace(":", "-").replace(".", "-")

    def _format_filename(self, version: str, timestamp: str) -> str:
        """生成快照文件名。

        Args:
            version: 版本号(如 "v1")
            timestamp: 时间戳(如 "20260505_143022")

        Returns:
            格式化的文件名
        """
        return CONFIG_VERSION_FILENAME.format(
            mac=self._sanitize_mac(), version=version, timestamp=timestamp
        )

    def _prune_versions(self) -> None:
        """裁剪超出最大保留数的最旧版本。"""
        existing = self._list_snapshot_files()
        if len(existing) <= CONFIG_VERSION_MAX_COUNT:
            return
        to_remove = existing[: len(existing) - CONFIG_VERSION_MAX_COUNT]
        for info in to_remove:
            filepath = self.backup_dir / info["filename"]
            try:
                filepath.unlink()
                LOG.info(f"配置版本裁剪: 删除 {info['filename']}")
            except OSError as e:
                LOG.warning(f"配置版本裁剪失败: {info['filename']} - {e}")

    # ------------------------------------------------------------------ #
    #  公共方法
    # ------------------------------------------------------------------ #
    def save_snapshot(self, config: dict) -> str:
        """将当前配置保存为版本快照。

        Args:
            config: 要保存的配置字典

        Returns:
            版本号字符串(如 "v1")
        """
        with self._lock:
            version = f"v{self._next_version}"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self._format_filename(version, timestamp)
            filepath = self.backup_dir / filename

            _atomic_write(filepath, config)
            LOG.done(f"配置快照已保存: {filename}")

            # 裁剪旧版本
            self._prune_versions()

            self._next_version += 1
            return version

    def get_version(self, version: str) -> dict | None:
        """加载指定版本的配置快照。

        Args:
            version: 版本号字符串(如 "v1")

        Returns:
            配置字典，如果版本不存在则返回 None
        """
        with self._lock:
            existing = self._list_snapshot_files()
            match = next((e for e in existing if e["version"] == version), None)
            if match is None:
                LOG.warning(f"配置版本未找到: {version}")
                return None
            filepath = self.backup_dir / match["filename"]
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    config = json.load(f)
                LOG.info(f"配置版本已加载: {version}")
                return config
            except (OSError, json.JSONDecodeError) as e:
                LOG.error(f"配置版本加载失败: {version} - {e}")
                return None

    def list_versions(self) -> list[dict]:
        """列出所有可用的配置版本。

        Returns:
            版本信息列表，按版本号升序排列。
            每个元素: {"version": "v1", "timestamp": "...", "filename": "..."}
        """
        with self._lock:
            existing = self._list_snapshot_files()
            return [
                {"version": e["version"], "timestamp": e["timestamp"], "filename": e["filename"]}
                for e in existing
            ]

    def rollback(self, version: str, storage_path: str | Path = None) -> dict:
        """回滚到指定版本的配置。

        仅返回/可选地本地保存配置，不通过ISAPI写入设备。

        Args:
            version: 目标版本号(如 "v1")
            storage_path: 可选，将配置原子写入此路径

        Returns:
            目标版本的配置字典

        Raises:
            ValueError: 如果指定版本不存在
        """
        with self._lock:
            config = self.get_version(version)
            if config is None:
                raise ValueError(f"配置版本不存在，无法回滚: {version}")

            if storage_path is not None:
                target = Path(storage_path) if isinstance(storage_path, str) else storage_path
                _atomic_write(target, config)
                LOG.done(f"配置已原子写入: {target}")

            return config
