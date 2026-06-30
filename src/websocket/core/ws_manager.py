"""
M8 WebSocket v1.0 - WebSocket 连接管理器

实现:
- P0.1: 连接建立与唯一 ID
- P0.3: 心跳机制 (ping/pong)
- P0.5: 连接关闭与资源清理
- P4.1: 断线重连支持
- P4.2: 并发控制 (单token/IP 最大连接数)
- P4.3: 活跃连接池
- P4.4: 超时不活跃连接清理

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from src.websocket.constants import (
    CONNECTION_TIMEOUT_SECONDS,
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_PING_MSG,
    HEARTBEAT_PONG_MSG,
    HEARTBEAT_TIMEOUT_COUNT,
    MAX_CONNECTIONS_PER_TOKEN,
    MAX_CONNECTIONS_TOTAL,
    ConnectionStatus,
)


# ================================================================== #
#  连接数据结构
# ================================================================== #

@dataclass
class WSConnection:
    """单个 WebSocket 连接的信息。"""
    connection_id: str
    websocket: WebSocket
    token: str = ""
    user: str = ""
    ip: str = ""
    status: ConnectionStatus = ConnectionStatus.CONNECTING
    connected_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)
    missed_pongs: int = 0
    subscriptions: set[str] = field(default_factory=set)  # 订阅的设备 MAC/主题
    reconnect_attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def update_activity(self) -> None:
        """更新最后活跃时间。"""
        self.last_active = time.time()
        self.last_pong = time.time()
        self.missed_pongs = 0

    def is_timed_out(self) -> bool:
        """检查连接是否超时 (P4.4)。"""
        return (time.time() - self.last_active) > CONNECTION_TIMEOUT_SECONDS

    def should_close_heartbeat(self) -> bool:
        """检查心跳是否超时 (P0.3)。"""
        return self.missed_pongs >= HEARTBEAT_TIMEOUT_COUNT


# ================================================================== #
#  WebSocket 连接管理器
# ================================================================== #

class WSManager:
    """管理所有 WebSocket 连接。"""

    def __init__(self) -> None:
        self._connections: dict[str, WSConnection] = {}      # connection_id -> WSConnection
        self._token_connections: dict[str, list[str]] = {}   # token -> [connection_id, ...]
        self._ip_connections: dict[str, list[str]] = {}      # ip -> [connection_id, ...]
        self._lock = asyncio.Lock()

    async def add_connection(
        self,
        websocket: WebSocket,
        token: str = "",
        ip: str = "",
    ) -> WSConnection | None:
        """添加新连接 (P0.1)。

        Args:
            websocket: FastAPI WebSocket 对象
            token: 认证 token
            ip: 客户端 IP

        Returns:
            WSConnection 实例, 或 None (如果超出限制)
        """
        # 并发控制 (P4.2)
        if len(self._connections) >= MAX_CONNECTIONS_TOTAL:
            return None

        if token and len(self._token_connections.get(token, [])) >= MAX_CONNECTIONS_PER_TOKEN:
            return None  # 超该 token 的最大连接数

        connection_id = str(uuid.uuid4())
        conn = WSConnection(
            connection_id=connection_id,
            websocket=websocket,
            token=token,
            ip=ip,
            status=ConnectionStatus.AUTHENTICATED,
        )

        async with self._lock:
            self._connections[connection_id] = conn
            if token:
                self._token_connections.setdefault(token, []).append(connection_id)
            if ip:
                self._ip_connections.setdefault(ip, []).append(connection_id)

        return conn

    async def remove_connection(self, connection_id: str) -> None:
        """移除连接并清理资源 (P0.5)。

        Args:
            connection_id: 连接 ID
        """
        async with self._lock:
            conn = self._connections.pop(connection_id, None)
            if conn is None:
                return

            # 从 token 索引中移除
            if conn.token and conn.token in self._token_connections:
                token_list = self._token_connections[conn.token]
                if connection_id in token_list:
                    token_list.remove(connection_id)
                if not token_list:
                    del self._token_connections[conn.token]

            # 从 IP 索引中移除
            if conn.ip and conn.ip in self._ip_connections:
                ip_list = self._ip_connections[conn.ip]
                if connection_id in ip_list:
                    ip_list.remove(connection_id)
                if not ip_list:
                    del self._ip_connections[conn.ip]

            conn.status = ConnectionStatus.CLOSED
            conn.subscriptions.clear()

    async def get_connection(self, connection_id: str) -> WSConnection | None:
        """获取指定连接 (P4.3)。

        Args:
            connection_id: 连接 ID

        Returns:
            WSConnection 或 None
        """
        return self._connections.get(connection_id)

    async def get_connections_by_token(self, token: str) -> list[WSConnection]:
        """获取指定 token 的所有连接 (P4.3)。

        Args:
            token: 认证 token

        Returns:
            该 token 对应的连接列表
        """
        conn_ids = self._token_connections.get(token, [])
        return [
            conn for cid in conn_ids
            if (conn := self._connections.get(cid)) is not None
        ]

    async def get_active_connections(self) -> list[WSConnection]:
        """获取所有活跃连接 (P4.3)。

        Returns:
            活跃连接列表
        """
        return [
            conn for conn in self._connections.values()
            if conn.status == ConnectionStatus.ACTIVE
        ]

    async def mark_active(self, connection_id: str) -> None:
        """标记连接为活跃状态。

        Args:
            connection_id: 连接 ID
        """
        conn = self._connections.get(connection_id)
        if conn:
            conn.status = ConnectionStatus.ACTIVE
            conn.update_activity()

    async def send_to_connection(self, connection_id: str, message: Any) -> bool:
        """向指定连接发送消息。

        Args:
            connection_id: 连接 ID
            message: 要发送的消息 (将被 JSON 序列化)

        Returns:
            是否发送成功
        """
        conn = self._connections.get(connection_id)
        if conn is None or conn.status == ConnectionStatus.CLOSED:
            return False

        try:
            await conn.websocket.send_json(message)
            conn.update_activity()
            return True
        except Exception:
            return False

    async def send_heartbeat(self, connection_id: str) -> bool:
        """发送心跳 ping (P0.3)。

        Args:
            connection_id: 连接 ID

        Returns:
            是否发送成功
        """
        conn = self._connections.get(connection_id)
        if conn is None or conn.status == ConnectionStatus.CLOSED:
            return False

        try:
            await conn.websocket.send_text(HEARTBEAT_PING_MSG)
            return True
        except Exception:
            return False

    async def handle_pong(self, connection_id: str) -> None:
        """处理心跳 pong 响应 (P0.3)。

        Args:
            connection_id: 连接 ID
        """
        conn = self._connections.get(connection_id)
        if conn:
            conn.update_activity()

    async def increment_missed_pongs(self, connection_id: str) -> int:
        """增加未响应心跳计数 (P0.3)。

        Args:
            connection_id: 连接 ID

        Returns:
            当前未响应计数
        """
        conn = self._connections.get(connection_id)
        if conn:
            conn.missed_pongs += 1
            return conn.missed_pongs
        return 0

    async def get_timeout_connections(self) -> list[str]:
        """获取所有超时的连接 ID (P4.4)。

        Returns:
            超时连接 ID 列表
        """
        return [
            conn.connection_id for conn in self._connections.values()
            if conn.is_timed_out() and conn.status == ConnectionStatus.ACTIVE
        ]

    async def get_heartbeat_violations(self) -> list[str]:
        """获取心跳超时的连接 ID (P0.3)。

        Returns:
            需要关闭的连接 ID 列表
        """
        return [
            conn.connection_id for conn in self._connections.values()
            if conn.should_close_heartbeat() and conn.status == ConnectionStatus.ACTIVE
        ]

    def get_stats(self) -> dict:
        """获取连接池统计信息 (P4.3)。

        Returns:
            统计字典: 总数/按状态/按token 等
        """
        status_counts: dict[str, int] = {}
        for conn in self._connections.values():
            status_counts[conn.status.value] = status_counts.get(conn.status.value, 0) + 1

        return {
            "total_connections": len(self._connections),
            "max_connections": MAX_CONNECTIONS_TOTAL,
            "active_connections": status_counts.get("active", 0),
            "authenticated_connections": status_counts.get("authenticated", 0),
            "closing_connections": status_counts.get("closing", 0),
            "unique_tokens": len(self._token_connections),
            "unique_ips": len(self._ip_connections),
            "by_status": status_counts,
        }

    def get_connection_count(self) -> int:
        """获取当前总连接数 (P4.3)。

        Returns:
            当前连接数
        """
        return len(self._connections)

    def list_all_connections(self) -> list[dict]:
        """获取所有连接详细列表。

        Returns:
            连接详情列表
        """
        return [
            {
                "connection_id": conn.connection_id,
                "token": conn.token,
                "user": conn.user,
                "ip": conn.ip,
                "status": conn.status.value,
                "connected_at": conn.connected_at,
                "last_active": conn.last_active,
                "subscriptions": list(conn.subscriptions),
                "reconnect_attempts": conn.reconnect_attempts,
            }
            for conn in self._connections.values()
        ]


# ================================================================== #
#  全局单例
# ================================================================== #

_ws_manager: WSManager | None = None


def get_ws_manager() -> WSManager:
    """获取全局 WSManager 实例。"""
    return _ws_manager  # type: ignore[return-value]


def init_ws_manager() -> WSManager:
    """初始化全局 WSManager 实例。

    Returns:
        WSManager 实例
    """
    global _ws_manager
    _ws_manager = WSManager()
    return _ws_manager
