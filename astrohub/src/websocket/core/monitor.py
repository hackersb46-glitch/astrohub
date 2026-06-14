"""
M8 WebSocket v1.0 - 连接监控

实现:
- 实时监控活跃连接状态
- 连接健康度分析
- 流量统计 (发送/接收消息计数)
- 性能指标 (握手时间、延迟)
- 日志记录

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from src.websocket.core.ws_manager import WSManager, get_ws_manager
from src.websocket.constants import ConnectionStatus


# ================================================================== #
#  连接监控器
# ================================================================== #

class ConnectionMonitor:
    """实时监控 WebSocket 连接。"""

    def __init__(self, ws_manager: WSManager | None = None) -> None:
        self._ws_manager = ws_manager or get_ws_manager()
        self._connect_times: dict[str, float] = {}       # connection_id -> connect_time
        self._message_counts: dict[str, int] = defaultdict(int)  # connection_id -> msg_count
        self._error_counts: dict[str, int] = defaultdict(int)    # connection_id -> error_count
        self._last_message_time: dict[str, float] = {}           # connection_id -> last_msg_time

    def record_connect(self, connection_id: str) -> None:
        """记录连接时间。

        Args:
            connection_id: 连接 ID
        """
        self._connect_times[connection_id] = time.time()

    def record_message(self, connection_id: str) -> None:
        """记录消息活动。

        Args:
            connection_id: 连接 ID
        """
        self._message_counts[connection_id] += 1
        self._last_message_time[connection_id] = time.time()

    def record_error(self, connection_id: str) -> None:
        """记录错误。

        Args:
            connection_id: 连接 ID
        """
        self._error_counts[connection_id] += 1

    def record_disconnect(self, connection_id: str) -> None:
        """记录连接断开并清理监控数据。

        Args:
            connection_id: 连接 ID
        """
        self._connect_times.pop(connection_id, None)
        self._message_counts.pop(connection_id, None)
        self._error_counts.pop(connection_id, None)
        self._last_message_time.pop(connection_id, None)

    def get_connection_health(self, connection_id: str) -> dict[str, Any]:
        """获取指定连接的健康状态。

        Args:
            connection_id: 连接 ID

        Returns:
            健康信息: 连接时长/消息计数/错误计数/活跃度
        """
        connect_time = self._connect_times.get(connection_id, 0)
        duration = time.time() - connect_time if connect_time else 0
        msg_count = self._message_counts.get(connection_id, 0)
        error_count = self._error_counts.get(connection_id, 0)
        last_msg = self._last_message_time.get(connection_id, 0)
        seconds_since_last = time.time() - last_msg if last_msg else float("inf")

        health = "good"
        if error_count > 10:
            health = "critical"
        elif error_count > 3:
            health = "warning"
        elif seconds_since_last > 120:
            health = "idle"

        return {
            "connection_id": connection_id,
            "duration_seconds": round(duration, 2),
            "message_count": msg_count,
            "error_count": error_count,
            "last_message_seconds_ago": round(seconds_since_last, 2) if seconds_since_last != float("inf") else None,
            "health": health,
        }

    def get_overview(self) -> dict[str, Any]:
        """获取所有连接的整体健康概览。

        Returns:
            概览统计
        """
        total_messages = sum(self._message_counts.values())
        total_errors = sum(self._error_counts.values())
        active_now = len(self._connect_times)

        health_distribution: dict[str, int] = {"good": 0, "warning": 0, "critical": 0, "idle": 0}
        for conn_id in list(self._connect_times.keys()):
            health = self.get_connection_health(conn_id)["health"]
            health_distribution[health] = health_distribution.get(health, 0) + 1

        return {
            "active_connections": active_now,
            "total_messages": total_messages,
            "total_errors": total_errors,
            "error_rate": round(total_errors / total_messages * 100, 2) if total_messages > 0 else 0,
            "health_distribution": health_distribution,
        }

    def get_idle_connections(self, idle_seconds: int = 300) -> list[str]:
        """获取空闲超过指定时间的连接 ID。

        Args:
            idle_seconds: 空闲阈值 (秒)

        Returns:
            空闲连接 ID 列表
        """
        now = time.time()
        idle_connections = []
        for conn_id, last_msg_time in self._last_message_time.items():
            if now - last_msg_time > idle_seconds:
                idle_connections.append(conn_id)
        return idle_connections


# ================================================================== #
#  全局单例
# ================================================================== #

_connection_monitor: ConnectionMonitor | None = None


def get_connection_monitor() -> ConnectionMonitor:
    """获取全局 ConnectionMonitor 实例。"""
    return _connection_monitor  # type: ignore[return-value]


def init_connection_monitor(ws_manager: WSManager | None = None) -> ConnectionMonitor:
    """初始化全局 ConnectionMonitor 实例。

    Args:
        ws_manager: WSManager 实例 (可选)

    Returns:
        ConnectionMonitor 实例
    """
    global _connection_monitor
    _connection_monitor = ConnectionMonitor(ws_manager=ws_manager)
    return _connection_monitor
