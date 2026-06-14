"""
M8 WebSocket v1.0 - WS 服务器 (Wave 4)

实现:
1. WebSocket 连接管理 - ws://host:port/ws, 多客户端并发, 连接状态跟踪
2. WebSocket 端点集成到 FastAPI
3. 心跳机制集成
4. 断线重连支持

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from src.websocket.constants import (
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_PONG_MSG,
    HEARTBEAT_TIMEOUT_COUNT,
    MAX_CONNECTIONS_TOTAL,
    MAX_CONNECTIONS_PER_TOKEN,
    WS_PATH,
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    MessageType,
)
from src.websocket.core.ws_manager import WSManager, get_ws_manager, init_ws_manager
from src.websocket.core.broadcast import BroadcastManager, get_broadcast_manager, init_broadcast_manager
from src.websocket.core.message_handler import MessageParser, MessageRouter
from src.websocket.core.auth import WSAuthenticator, get_ws_auth, init_ws_auth
from src.websocket.core.monitor import ConnectionMonitor, get_connection_monitor, init_connection_monitor


# ================================================================== #
#  WebSocket 服务器配置
# ================================================================== #

class WebSocketServerConfig:
    """WS 服务器配置 (Wave 4)."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        path: str = WS_PATH,
        max_connections: int = MAX_CONNECTIONS_TOTAL,
        max_per_token: int = MAX_CONNECTIONS_PER_TOKEN,
        heartbeat_interval: int = HEARTBEAT_INTERVAL_SECONDS,
        heartbeat_timeout_count: int = HEARTBEAT_TIMEOUT_COUNT,
    ) -> None:
        self.host = host
        self.port = port
        self.path = path
        self.max_connections = max_connections
        self.max_per_token = max_per_token
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout_count = heartbeat_timeout_count


# ================================================================== #
#  WebSocket 服务器
# ================================================================== #

class WebSocketServer:
    """WebSocket 服务器 - 管理所有 WS 连接。

    Wave 4 实现:
    - 连接管理/状态跟踪
    - 心跳机制 (30s ping / 60s 超时断开)
    - 断线重连支持
    - 实时状态推送
    """

    def __init__(self, config: WebSocketServerConfig | None = None) -> None:
        self.config = config or WebSocketServerConfig()
        self._app: FastAPI | None = None
        self._initialized = False
        self._cleanup_task: asyncio.Task | None = None

    @property
    def ws_manager(self) -> WSManager:
        mgr = get_ws_manager()
        if mgr is None:
            raise RuntimeError("WSManager not initialized. Call mount_to() first.")
        return mgr

    @property
    def broadcast_manager(self) -> BroadcastManager:
        mgr = get_broadcast_manager()
        if mgr is None:
            raise RuntimeError("BroadcastManager not initialized. Call mount_to() first.")
        return mgr

    def mount_to(self, app: FastAPI) -> None:
        """将 WebSocket 服务器挂载到 FastAPI 应用。

        Args:
            app: FastAPI 应用实例
        """
        self._app = app
        self._initialize_managers()
        self._register_endpoint(app)
        self._start_cleanup_task(app)
        self._initialized = True

    def _initialize_managers(self) -> None:
        """初始化管理器实例。"""
        init_ws_manager()
        init_broadcast_manager()
        init_ws_auth()
        init_connection_monitor()

    def _register_endpoint(self, app: FastAPI) -> None:
        """注册 WebSocket 端点。"""

        @app.websocket(self.config.path)
        async def ws_endpoint(
            websocket: WebSocket,
        ) -> None:
            """WebSocket 主端点。

            处理: 认证 -> 心跳 -> 消息接收 -> 路由 -> 关闭清理。
            """
            await self._handle_connection(websocket)

    def _start_cleanup_task(self, app: FastAPI) -> None:
        """启动定时清理任务。"""
        async def cleanup_loop() -> None:
            """定期检查并清理超时连接。"""
            while True:
                await asyncio.sleep(30)
                try:
                    await self._cleanup_expired_connections()
                except Exception as e:
                    print(f"[M8 WS] cleanup error: {e}")

        @app.on_event("startup")
        async def on_startup() -> None:
            self._cleanup_task = asyncio.create_task(cleanup_loop())
            print(f"[M8 WS] Server started on {self.config.path}")
            print(f"[M8 WS] Max connections: {self.config.max_connections}")
            print(f"[M8 WS] Heartbeat: {self.config.heartbeat_interval}s interval, "
                  f"{self.config.heartbeat_timeout_count} misses timeout")

        @app.on_event("shutdown")
        async def on_shutdown() -> None:
            if self._cleanup_task:
                self._cleanup_task.cancel()
            await self._cleanup_all_connections()

    async def _handle_connection(self, websocket: WebSocket) -> None:
        """处理单个 WebSocket 连接。"""
        client_ip = websocket.client.host if websocket.client else "unknown"

        # 并发控制
        if self.ws_manager.get_connection_count() >= self.config.max_connections:
            await websocket.accept()
            await websocket.close(
                code=1008,
                reason=ERROR_CODE_DESCRIPTION[ErrorCode.CONNECTION_LIMIT_REACHED],
            )
            return

        # 接受连接
        await websocket.accept()

        conn = await self.ws_manager.add_connection(
            websocket=websocket,
            ip=client_ip,
        )
        if conn is None:
            await websocket.close()
            return

        monitor = get_connection_monitor()
        monitor.record_connect(conn.connection_id)

        await self.ws_manager.mark_active(conn.connection_id)

        # 推送连接成功消息
        await websocket.send_json({
            "type": MessageType.AUTH_ACK.value,
            "payload": {
                "connection_id": conn.connection_id,
                "message": "WebSocket connected",
                "timestamp": time.time(),
            },
        })

        # 同步最新状态 (断线重连后)
        await self._sync_latest_state(conn.connection_id)

        # --- 心跳 (P0.3) & 消息接收 ---
        heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(conn.connection_id)
        )

        try:
            await self._message_loop(conn, monitor)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            conn.status.value = "closing"
            await self.broadcast_manager.unsubscribe_all(conn.connection_id)
            monitor.record_disconnect(conn.connection_id)
            await self.ws_manager.remove_connection(conn.connection_id)

    async def _heartbeat_loop(self, connection_id: str) -> None:
        """心跳循环 - 每30秒发送ping，60秒无pong断开。

        Wave 4:
        - 客户端每30秒发送ping
        - 服务器60秒无心跳则断开
        """
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)

            conn = await self.ws_manager.get_connection(connection_id)
            if conn is None or conn.status.value == "closed":
                break

            # 检查是否超时 (60秒无响应)
            now = time.time()
            if (now - conn.last_active) > (self.config.heartbeat_interval * self.config.heartbeat_timeout_count):
                print(f"[M8 WS] Heartbeat timeout: {connection_id}")
                await self.ws_manager.remove_connection(connection_id)
                break

            # 发送 ping
            try:
                conn_ws = (await self.ws_manager.get_connection(connection_id))
                if conn_ws:
                    await conn_ws.websocket.send_text("ping")
            except Exception:
                break

    async def _message_loop(self, conn, monitor) -> None:
        """消息接收循环。"""
        parser = MessageParser()

        while True:
            raw_message = await conn.websocket.receive_text()

            # 心跳 pong 响应
            if raw_message == HEARTBEAT_PONG_MSG:
                await self.ws_manager.handle_pong(conn.connection_id)
                continue

            monitor.record_message(conn.connection_id)

            try:
                message_type, payload, message_id = parser.parse(raw_message)
            except Exception as e:
                response = {
                    "type": MessageType.ERROR.value,
                    "payload": {
                        "code": ErrorCode.INVALID_MESSAGE.value,
                        "message": str(e),
                    },
                }
                if message_id:
                    response["id"] = message_id
                await conn.websocket.send_json(response)
                continue

            # 处理路由
            response = await self._route_message(message_type, payload, conn)
            if response:
                if message_id:
                    response["id"] = message_id
                await conn.websocket.send_json(response)

    async def _route_message(
        self, message_type: str, payload: dict, conn
    ) -> dict | None:
        """路由消息到处理器。"""
        # 订阅
        if message_type == MessageType.SUBSCRIBE.value:
            topic = payload.get("topic", "")
            if topic:
                success = await self.broadcast_manager.subscribe(conn.connection_id, topic)
                return {
                    "type": MessageType.SUBSCRIBE.value,
                    "payload": {"topic": topic, "success": success},
                }

        # 取消订阅
        if message_type == MessageType.UNSUBSCRIBE.value:
            topic = payload.get("topic", "")
            if topic:
                await self.broadcast_manager.unsubscribe(conn.connection_id, topic)
                return {
                    "type": MessageType.UNSUBSCRIBE.value,
                    "payload": {"topic": topic, "success": True},
                }

        # 心跳 ping (服务端处理客户端 ping)
        if message_type == MessageType.PING.value:
            await self.ws_manager.handle_pong(conn.connection_id)
            return {
                "type": MessageType.PONG.value,
                "payload": {"timestamp": time.time()},
            }

        # 委托到 handlers
        handlers = _get_message_handlers()
        handler = handlers.get(message_type)
        if handler:
            return await handler(payload, conn)

        return {
            "type": MessageType.ERROR.value,
            "payload": {
                "code": ErrorCode.UNKNOWN_MESSAGE_TYPE.value,
                "message": f"未知消息类型: {message_type}",
            },
        }

    async def _sync_latest_state(self, connection_id: str) -> None:
        """断线重连后同步最新状态。

        Wave 4: 重连后推送设备在线状态、流状态等。
        """
        conn = await self.ws_manager.get_connection(connection_id)
        if conn is None:
            return

        # 推送设备状态
        device_status = await self._get_device_status_snapshot()
        if device_status:
            await self.ws_manager.send_to_connection(
                connection_id,
                {
                    "type": MessageType.DEVICE_ONLINE_BROADCAST.value,
                    "payload": {
                        "devices": device_status,
                        "timestamp": time.time(),
                    },
                },
            )

    async def _get_device_status_snapshot(self) -> list[dict]:
        """获取设备状态快照 (用于重连同步)。

        实际部署中应从 DeviceManager 获取。
        """
        # 占位 - 实际实现需接入 DeviceManager
        return []

    async def _cleanup_expired_connections(self) -> None:
        """定期清理超时连接。"""
        timed_out = await self.ws_manager.get_timeout_connections()
        for conn_id in timed_out:
            print(f"[M8 WS] Cleanup expired connection: {conn_id}")
            await self.ws_manager.remove_connection(conn_id)

    async def _cleanup_all_connections(self) -> None:
        """清理所有连接 (服务器关闭时)。"""
        stats = self.ws_manager.get_stats()
        print(f"[M8 WS] Closing {stats['total_connections']} connections...")

    def get_connection_stats(self) -> dict:
        """获取连接统计。"""
        if not self._initialized:
            return {"error": "Server not initialized"}
        return self.ws_manager.get_stats()

    async def push_device_status(
        self, device_mac: str, status: str
    ) -> int:
        """推送设备状态变更到所有订阅者。

        Returns:
            成功推送数
        """
        return await self.broadcast_manager.publish_device_status(
            device_mac=device_mac,
            status=status,
            timestamp=str(time.time()),
        )

    async def push_stream_status(self, stream_id: str, status: str) -> int:
        """推送流状态变更到所有连接。"""
        return await self.broadcast_manager.publish_to_all(
            message_type=MessageType.STREAM_START if status == "started" else MessageType.STREAM_STOP,
            data={"stream_id": stream_id, "status": status, "timestamp": time.time()},
        )


# ================================================================== #
#  消息处理器注册
# ================================================================== #

from src.websocket.handlers import register_message_handlers


def _get_message_handlers() -> dict:
    """获取消息处理器。"""
    return getattr(_get_message_handlers, "_handlers", {})


# 初始化时注册
_get_message_handlers._handlers = register_message_handlers()  # type: ignore[attr-defined]
