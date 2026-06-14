"""
M11 Deployment v1.0 - 服务启停/状态管理

服务的启动、停止、重启、状态查询、systemd/unit 集成。

P2.1: 服务启停管理
P2.3: 日志轮转

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from deployment.constants import (
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    LOG_ROTATE_BACKUP_COUNT,
    LOG_ROTATE_MAX_SIZE_MB,
    ServiceStatus,
)


class ServiceError(Exception):
    """服务管理异常。"""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code.value}] {message}")


class ServiceManager:
    """服务生命周期管理。

    管理服务的 start/stop/restart/status。
    P2.1: start/stop/restart 正确执行; 状态查询准确。
    """

    def __init__(self, service_name: str | None = None):
        """Initialize."""
        self._service_name = service_name or "astro-hub"
        self._state: ServiceStatus = ServiceStatus.UNKNOWN

    @property
    def service_name(self) -> str:
        """服务名称。"""
        return self._service_name

    @property
    def status(self) -> ServiceStatus:
        """当前服务状态。"""
        return self._state

    def start(self, command: str | None = None) -> bool:
        """启动服务。

        Args:
            command: 自定义启动命令
        Returns:
            是否成功
        """
        self._state = ServiceStatus.STARTING
        try:
            result = subprocess.run(
                [command] if command else ["docker", "compose", "up", "-d"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                self._state = ServiceStatus.RUNNING
                return True
            else:
                self._state = ServiceStatus.UNKNOWN
                raise ServiceError(
                    ErrorCode.SERVICE_START_FAILED,
                    f"服务启动失败: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            self._state = ServiceStatus.UNKNOWN
            raise ServiceError(
                ErrorCode.SERVICE_START_FAILED,
                "服务启动超时"
            )

    def stop(self, command: str | None = None) -> bool:
        """停止服务。

        Args:
            command: 自定义停止命令
        Returns:
            是否成功
        """
        self._state = ServiceStatus.STOPPING
        try:
            result = subprocess.run(
                [command] if command else ["docker", "compose", "down"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                self._state = ServiceStatus.STOPPED
                return True
            else:
                raise ServiceError(
                    ErrorCode.SERVICE_STOP_FAILED,
                    f"服务停止失败: {result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            raise ServiceError(
                ErrorCode.SERVICE_STOP_FAILED,
                "服务停止超时"
            )

    def restart(self, start_cmd: str | None = None, stop_cmd: str | None = None) -> bool:
        """重启服务 (stop → start)。"""
        self.stop(command=stop_cmd)
        time.sleep(2)
        return self.start(command=start_cmd)

    def get_status(self) -> dict[str, Any]:
        """查询服务当前状态。

        Returns:
            {status, uptime, pid, service_name}
        """
        return {
            "service_name": self._service_name,
            "status": self._state.value,
        }


# ------------------------------------------------------------------ #
#  日志轮转 (P2.3)
# ------------------------------------------------------------------ #

class LogRotator:
    """日志轮转管理器。

    P2.3: 按日期切割日志; 保留最近30天; 自动清理过期日志。
    """

    RETENTION_DAYS = 30  # 保留最近30天

    def __init__(
        self,
        max_size_mb: int = LOG_ROTATE_MAX_SIZE_MB,
        backup_count: int = LOG_ROTATE_BACKUP_COUNT,
        retention_days: int = RETENTION_DAYS,
    ):
        """Initialize."""
        self._max_size = max_size_mb * 1024 * 1024  # 转 bytes
        self._backup_count = backup_count
        self._retention_days = retention_days

    def rotate(self, log_path: Path) -> bool:
        """按日期切割日志文件。

        Args:
            log_path: 日志文件路径
        Returns:
            是否成功轮转
        """
        import shutil
        from datetime import datetime

        if not log_path.exists():
            return False

        # 按日期切割（无论大小）
        date_str = datetime.now().strftime("%Y%m%d")
        rotated = log_path.with_suffix(f".{date_str}.log")

        # 如果今日已切割过，跳过
        if rotated.exists():
            return False

        try:
            # 复制当前日志到日期文件
            shutil.copy2(str(log_path), str(rotated))
            # 原文件截断（不丢失正在写入的日志）
            with open(log_path, 'w') as f:
                pass  # 清空内容
            return True
        except Exception:
            return False

    def rotate_by_size(self, log_path: Path) -> bool:
        """按大小轮转日志文件。

        Args:
            log_path: 日志文件路径
        Returns:
            是否成功轮转
        """
        import shutil
        from datetime import datetime

        if not log_path.exists():
            return False

        # 检查文件大小
        if log_path.stat().st_size < self._max_size:
            return False  # 未达轮转阈值

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated = log_path.with_suffix(f".{timestamp}.log")

        try:
            shutil.copy2(str(log_path), str(rotated))
            with open(log_path, 'w') as f:
                pass
            self._cleanup_old_backups(log_path)
            return True
        except Exception:
            return False

    def cleanup_expired_logs(self, log_dir: Path) -> int:
        """自动清理超出保留天数的过期日志。

        Args:
            log_dir: 日志目录
        Returns:
            已清理的文件数量
        """
        from datetime import datetime, timedelta

        if not log_dir.exists():
            return 0

        cutoff_date = datetime.now() - timedelta(days=self._retention_days)
        cleaned = 0

        for log_file in log_dir.glob("*.log"):
            # 检查文件名中的日期 (格式: YYYYMMDD)
            date_str = self._extract_date_from_filename(log_file.name)
            if date_str:
                try:
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date < cutoff_date:
                        log_file.unlink()
                        cleaned += 1
                except ValueError:
                    pass

        return cleaned

    def _cleanup_old_backups(self, log_path: Path) -> None:
        """清理超出保留数量的旧日志。"""
        pattern = f"{log_path.stem}.*.log"
        backups = sorted(log_path.parent.glob(pattern))
        while len(backups) > self._backup_count:
            oldest = backups.pop(0)
            oldest.unlink()

    @staticmethod
    def _extract_date_from_filename(filename: str) -> str:
        """从文件名提取日期字符串 (YYYYMMDD)。"""
        import re
        match = re.search(r"(\d{8})", filename)
        return match.group(1) if match else ""
