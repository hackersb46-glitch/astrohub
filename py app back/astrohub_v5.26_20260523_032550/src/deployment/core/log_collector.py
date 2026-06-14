"""
M11 Deployment v1.0 - 日志聚合

多服务日志采集、日志级别过滤、实时日志流、日志导出。

P2.3: 日志聚合服务
P4.3: 告警通知

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import subprocess
import time
from collections import deque
from typing import Any

from deployment.constants import LOG_DIR


class LogEntry:
    """单条日志条目。"""

    def __init__(self, service: str, level: str, message: str, timestamp: float | None = None):
        self.service = service
        self.level = level.upper()
        self.message = message
        self.timestamp = timestamp or time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "level": self.level,
            "message": self.message,
            "timestamp": self.timestamp,
        }


class LogCollector:
    """日志聚合器。

    采集各服务日志，支持级别过滤与分页查询。
    """

    _instance: "LogCollector | None" = None

    def __init__(self, max_entries: int = 10000):
        """Initialize."""
        self._entries: deque[LogEntry] = deque(maxlen=max_entries)
        self._log_dir = LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def instance(cls) -> "LogCollector":
        """获取/创建单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add(self, service: str, level: str, message: str) -> LogEntry:
        """添加日志条目。

        Args:
            service: 服务名
            level: 级别 (info, warning, error, done, failed)
            message: 日志内容
        Returns:
            添加的日志条目
        """
        entry = LogEntry(service=service, level=level, message=message)
        self._entries.append(entry)
        return entry

    def query(
        self,
        service: str | None = None,
        level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LogEntry]:
        """查询日志。

        Args:
            service: 服务名过滤
            level: 级别过滤
            limit: 返回数量
            offset: 偏移
        Returns:
            匹配的日志条目列表
        """
        results = list(self._entries)

        if service:
            results = [e for e in results if e.service == service]
        if level:
            level_upper = level.upper()
            results = [e for e in results if e.level == level_upper]

        # 按时间倒序
        results.sort(key=lambda e: e.timestamp, reverse=True)

        return results[offset:offset + limit]

    def count(self, service: str | None = None, level: str | None = None) -> int:
        """统计日志条数。"""
        results = list(self._entries)
        if service:
            results = [e for e in results if e.service == service]
        if level:
            results = [e for e in results if e.level == level.upper()]
        return len(results)

    def collect_from_docker(self, service_name: str, lines: int = 100) -> list[LogEntry]:
        """从 Docker 容器采集日志。

        Args:
            service_name: 服务/容器名
        Returns:
            采集到的日志条目
        """
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(lines), service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            entries = []
            for line in result.stdout.splitlines() + result.stderr.splitlines():
                if line.strip():
                    entries.append(LogEntry(
                        service=service_name,
                        level="INFO",
                        message=line.strip(),
                    ))

            for entry in entries:
                self._entries.append(entry)

            return entries

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    def get_stats(self) -> dict[str, Any]:
        """获取日志统计摘要。

        Returns:
            {"total": N, "by_level": {"INFO": ..., "ERROR": ...}, "by_service": {...}}
        """
        by_level: dict[str, int] = {}
        by_service: dict[str, int] = {}

        for entry in self._entries:
            by_level[entry.level] = by_level.get(entry.level, 0) + 1
            by_service[entry.service] = by_service.get(entry.service, 0) + 1

        return {
            "total": len(self._entries),
            "by_level": by_level,
            "by_service": by_service,
        }
