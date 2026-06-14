"""
M2 Device Manager v1.0 - 配置备份与恢复

实现设备配置备份到本地文件(P2.3)、从备份文件恢复设备配置(P2.4)。
备份文件名格式: config_{MAC}_{yyyyMMdd_HHmmss}.json
恢复时逐项写入设备并验证结果，不支持的参数跳过并记录警告。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from device.constants import BACKUP_DIR, CONFIG_BACKUP_FILENAME
from device.core.logger import LOG
from device.core.mac_utils import normalize_mac
from device.isapi.client import ISAPIClient
from device.isapi.config_manager import ConfigManager
from device.models.schemas import ConfigBackupResponse


class ConfigBackup:
    """配置备份管理器：备份设备配置到本地JSON文件，从备份恢复设备配置。

    备份文件名格式: config_{MAC}_{yyyyMMdd_HHmmss}.json
    例如: config_AA-BB-CC-DD-EE-FF_20260505_143022.json

    Args:
        backup_dir: 备份文件存储目录，默认使用 BACKUP_DIR
    """

    def __init__(self, backup_dir: str | Path | None = None) -> None:
        self._backup_dir = Path(backup_dir) if backup_dir is not None else BACKUP_DIR
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        LOG.info(f"ConfigBackup 初始化完成: {self._backup_dir}")

    # ------------------------------------------------------------------ #
    #  P2.3 - 备份配置到本地
    # ------------------------------------------------------------------ #

    def _build_filename(self, mac: str, timestamp: datetime) -> str:
        """构建备份文件名。

        Args:
            mac: 设备MAC地址
            timestamp: 备份时间戳

        Returns:
            备份文件名
        """
        norm_mac = normalize_mac(mac)
        dash_mac = norm_mac.replace(":", "-")
        ts = timestamp.strftime("%Y%m%d_%H%M%S")
        return CONFIG_BACKUP_FILENAME.format(mac=dash_mac, timestamp=ts)

    def backup_config(self, mac: str, config_manager: ConfigManager) -> dict:
        """备份设备当前配置到本地JSON文件(P2.3)。

        通过ConfigManager读取设备当前配置，导出所有可配置参数为JSON，
        包含时间戳和MAC信息。

        Args:
            mac: 设备的MAC地址
            config_manager: ConfigManager实例（已绑定ISAPIClient）

        Returns:
            操作结果，包含success、backup_path、timestamp等字段
        """
        norm_mac = normalize_mac(mac)

        # Step 1: 读取设备当前配置
        LOG.info(f"开始备份设备配置: {norm_mac}")
        read_result = config_manager.read_config()

        if not read_result.get("success"):
            LOG.failed(f"读取设备配置失败: {norm_mac} - {read_result.get('error')}")
            return {
                "success": False,
                "error": f"读取设备配置失败: {read_result.get('error')}",
            }

        config_data = read_result.get("config", {})

        # Step 2: 构建备份文件
        timestamp = datetime.now()
        filename = self._build_filename(norm_mac, timestamp)
        backup_path = self._backup_dir / filename

        # Step 3: 写入包含元数据的备份文件
        backup_record = {
            "mac": norm_mac,
            "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "backup_filename": filename,
            "config": config_data,
        }

        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(backup_record, f, indent=2, ensure_ascii=False)
                f.write("\n")

            LOG.done(f"配置备份成功: {norm_mac} -> {backup_path}")
            return {
                "success": True,
                "backup": ConfigBackupResponse(
                    mac=norm_mac,
                    backup_path=str(backup_path),
                    timestamp=backup_record["timestamp"],
                ).model_dump(),
            }
        except Exception as e:
            LOG.error(f"写入备份文件失败: {backup_path} - {e}")
            return {
                "success": False,
                "error": f"写入备份文件失败: {e}",
            }

    # ------------------------------------------------------------------ #
    #  P2.4 - 从备份恢复配置
    # ------------------------------------------------------------------ #

    def restore_from_backup(self, mac: str, backup_path: str | Path, config_manager: ConfigManager) -> dict:
        """从备份文件恢复设备配置(P2.4)。

        读取备份文件中的配置，逐项写入设备，验证恢复结果。
        不支持的参数跳过并记录警告。

        Args:
            mac: 设备的MAC地址
            backup_path: 备份文件路径
            config_manager: ConfigManager实例（已绑定ISAPIClient）

        Returns:
            操作结果，包含success、restored、skipped、errors等字段
        """
        norm_mac = normalize_mac(mac)
        path = Path(backup_path)

        # Step 1: 验证备份文件存在
        if not path.exists():
            LOG.failed(f"备份文件不存在: {path}")
            return {
                "success": False,
                "error": f"备份文件不存在: {path}",
            }

        # Step 2: 读取备份文件
        try:
            with open(path, "r", encoding="utf-8") as f:
                backup_record = json.load(f)
        except json.JSONDecodeError as e:
            LOG.failed(f"备份文件格式错误: {path} - {e}")
            return {
                "success": False,
                "error": f"备份文件格式错误: {e}",
            }

        # 验证MAC匹配
        backup_mac = backup_record.get("mac")
        if backup_mac and normalize_mac(backup_mac) != norm_mac:
            LOG.failed(f"备份文件MAC不匹配: 期望={norm_mac}, 实际={backup_mac}")
            return {
                "success": False,
                "error": f"备份文件MAC不匹配: 期望 {norm_mac}, 实际 {backup_mac}",
            }

        config_data = backup_record.get("config", {})
        if not config_data:
            LOG.failed(f"备份文件中无配置数据: {path}")
            return {
                "success": False,
                "error": "备份文件中无配置数据",
            }

        # Step 3: 写入配置到设备
        LOG.info(f"开始恢复设备配置: {norm_mac} <- {path}")
        write_result = config_manager.write_config(config_data)

        if write_result.get("success"):
            LOG.done(f"配置恢复成功: {norm_mac} <- {path}")
            return {
                "success": True,
                "restored_count": self._count_config_params(config_data),
                "skipped": [],
                "errors": [],
            }

        # 写入失败，尝试逐项恢复
        LOG.warning(f"整体配置写入失败，尝试逐项恢复: {norm_mac}")
        return self._restore_individual_params(norm_mac, config_data, config_manager)

    def _restore_individual_params(
        self, mac: str, config_data: dict, config_manager: ConfigManager
    ) -> dict:
        """逐项恢复配置参数，跳过不支持的参数。

        Args:
            mac: 设备MAC地址
            config_data: 配置数据
            config_manager: ConfigManager实例

        Returns:
            逐项恢复的结果汇总
        """
        restored: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        for param_name, param_value in self._flatten_config(config_data):
            try:
                # 尝试写入单个参数
                single_config = self._unflatten_config(param_name, param_value)
                result = config_manager.write_config(single_config)

                if result.get("success"):
                    restored.append(param_name)
                else:
                    error_msg = result.get("error", "未知错误")
                    if "不支持" in error_msg or "not support" in error_msg.lower():
                        skipped.append(param_name)
                        LOG.warning(f"跳过不支持的参数: {mac}/{param_name}")
                    else:
                        errors.append(f"{param_name}: {error_msg}")
                        LOG.error(f"恢复参数失败: {mac}/{param_name} - {error_msg}")
            except Exception as e:
                skipped.append(param_name)
                LOG.warning(f"跳过参数(异常): {mac}/{param_name} - {e}")

        success = len(restored) > 0 and len(errors) == 0
        LOG.info(
            f"逐项恢复完成: {mac} | 成功={len(restored)}, "
            f"跳过={len(skipped)}, 失败={len(errors)}"
        )

        return {
            "success": success,
            "restored_count": len(restored),
            "restored_params": restored,
            "skipped": skipped,
            "errors": errors,
        }

    # ------------------------------------------------------------------ #
    #  备份文件管理
    # ------------------------------------------------------------------ #

    def list_backups(self, mac: str | None = None) -> list[dict]:
        """列出备份文件。

        Args:
            mac: 过滤指定MAC的备份（可选），为None时列出所有备份

        Returns:
            备份文件信息列表，按时间倒序排列
        """
        if not self._backup_dir.exists():
            return []

        backups: list[dict] = []

        for file_path in self._backup_dir.glob("config_*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    record = json.load(f)

                backup_mac = record.get("mac", "")
                # 如果指定了MAC过滤，只返回匹配的
                if mac is not None and normalize_mac(backup_mac) != normalize_mac(mac):
                    continue

                backups.append({
                    "mac": backup_mac,
                    "filename": file_path.name,
                    "path": str(file_path),
                    "timestamp": record.get("timestamp", ""),
                    "size_bytes": file_path.stat().st_size,
                })
            except (json.JSONDecodeError, OSError) as e:
                LOG.warning(f"读取备份文件失败: {file_path} - {e}")
                continue

        # 按时间倒序排列
        backups.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        LOG.info(f"备份列表查询: {len(backups)} 个备份" + (f" (MAC={mac})" if mac else ""))
        return backups

    def get_latest_backup(self, mac: str) -> dict | None:
        """获取指定设备的最新备份。

        Args:
            mac: 设备的MAC地址

        Returns:
            最新备份文件信息，不存在时返回None
        """
        backups = self.list_backups(mac=mac)
        if backups:
            latest = backups[0]  # 已按时间倒序排列
            LOG.info(f"最新备份: {mac} -> {latest['filename']}")
            return latest
        LOG.info(f"设备无备份: {mac}")
        return None

    def delete_backup(self, backup_path: str | Path) -> dict:
        """删除指定的备份文件。

        Args:
            backup_path: 备份文件路径

        Returns:
            操作结果
        """
        path = Path(backup_path)
        if not path.exists():
            return {"success": False, "error": f"备份文件不存在: {path}"}

        try:
            path.unlink()
            LOG.done(f"备份文件已删除: {path}")
            return {"success": True}
        except OSError as e:
            LOG.error(f"删除备份文件失败: {path} - {e}")
            return {"success": False, "error": f"删除备份文件失败: {e}"}

    # ------------------------------------------------------------------ #
    #  辅助方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _count_config_params(config: dict) -> int:
        """统计配置参数数量。

        Args:
            config: 配置字典

        Returns:
            参数总数（递归计数叶子节点）
        """
        count = 0
        for value in config.values():
            if isinstance(value, dict):
                count += ConfigBackup._count_config_params(value)
            elif isinstance(value, list):
                count += len(value)
            else:
                count += 1
        return count

    @staticmethod
    def _flatten_config(config: dict, prefix: str = "") -> list[tuple[str, Any]]:
        """扁平化嵌套配置为 (path, value) 对列表。

        Args:
            config: 配置字典
            prefix: 路径前缀

        Returns:
            扁平化后的 (path, value) 列表
        """
        result: list[tuple[str, Any]] = []
        for key, value in config.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.extend(ConfigBackup._flatten_config(value, path))
            else:
                result.append((path, value))
        return result

    @staticmethod
    def _unflatten_config(path: str, value: Any) -> dict:
        """将扁平路径还原为嵌套配置字典。

        Args:
            path: 点分路径 (如 "Network.interface.ip")
            value: 值

        Returns:
            嵌套配置字典
        """
        keys = path.split(".")
        result: dict = {}
        current = result
        for key in keys[:-1]:
            current[key] = {}
            current = current[key]
        current[keys[-1]] = value
        return result
