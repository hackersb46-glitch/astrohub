"""
M8 WebSocket v1.0 - FastAPI WebSocket 路由

实现:
- P0.1: WS 连接建立 (/ws 端点，握手完成)
- P0.2: 消息路由 (接收消息 -> 分发到处理器)
- P0.3: 心跳机制 (定期ping，超时断开)
- P0.4: 连接认证 (URL参数携带token)
- P0.5: 连接关闭 (主动/被动断开的资源清理)
- P4.4: 超时连接主动清理

心跳循环与消息接收在同一 websocket 端点内并发执行。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from src.websocket.constants import (
    HEARTBEAT_INTERVAL_SECONDS,
    WS_AUTH_PARAM,
    MAX_CONNECTIONS_TOTAL,
    MAX_CONNECTIONS_PER_TOKEN,
    WS_PATH,
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    MessageType,
)
from src.websocket.core.message_handler import MessageParser, MessageRouter
from src.websocket.core.ws_manager import WSManager, get_ws_manager, WSConnection
from src.websocket.core.broadcast import BroadcastManager, get_broadcast_manager
from src.websocket.core.auth import WSAuthenticator, get_ws_auth
from src.websocket.core.monitor import ConnectionMonitor, get_connection_monitor

# ------------------------------------------------------------------ #
#  WebSocket 路由器
# ------------------------------------------------------------------ #

ws_router = APIRouter(tags=["M8 WebSocket"])


# ================================================================== #
#  心跳与清理后台任务
# ================================================================== #

async def _heartbeat_loop(ws_mgr: WSManager, connection_id: str, interval: int) -> None:
    """心跳发送循环 (P0.3)。

    定期向连接发送 ping, 超时未收到 pong 则关闭。

    Args:
        ws_mgr: WSManager 实例
        connection_id: 连接 ID
        interval: 心跳间隔 (秒)
    """
    while True:
        await asyncio.sleep(interval)
        conn = await ws_mgr.get_connection(connection_id)
        if conn is None or conn.status.value == "closed":
            break

        if not await ws_mgr.send_heartbeat(connection_id):
            break

        missed = await ws_mgr.increment_missed_pongs(connection_id)
        if await ws_mgr.get_connection(connection_id) and \
               (await ws_mgr.get_connection(connection_id)).should_close_heartbeat():
            await ws_mgr.remove_connection(connection_id)
            break


async def _timeout_cleanup_loop(ws_mgr: WSManager) -> None:
    """超时连接清理循环 (P4.4)。

    定期检查并关闭超时不活跃连接。

    Args:
        ws_mgr: WSManager 实例
    """
    from src.websocket.constants import CONNECTION_TIMEOUT_SECONDS
    while True:
        await asyncio.sleep(CONNECTION_TIMEOUT_SECONDS / 2)  # 每半个超时周期检查一次
        timed_out = await ws_mgr.get_timeout_connections()
        for conn_id in timed_out:
            await ws_mgr.remove_connection(conn_id)


# ================================================================== #
#  WS 端点 (P0.1-P0.5)
# ================================================================== #

@ws_router.websocket(WS_PATH)
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None, alias=WS_AUTH_PARAM),  # P0.4
) -> None:
    """WebSocket 主端点 (P0.1)。

    处理: 认证 -> 心跳 -> 消息接收 -> 消息路由 -> 关闭清理。
    """
    ws_mgr = get_ws_manager()
    broadcast_mgr = get_broadcast_manager()
    auth = get_ws_auth()
    monitor = get_connection_monitor()
    router = _get_message_router()
    parser = MessageParser()

    client_ip = websocket.client.host if websocket.client else "unknown"

    # --- 并发控制 (P4.2) ---
    if ws_mgr.get_connection_count() >= MAX_CONNECTIONS_TOTAL:
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "payload": {
                "code": ErrorCode.CONNECTION_LIMIT_REACHED.value,
                "message": ERROR_CODE_DESCRIPTION[ErrorCode.CONNECTION_LIMIT_REACHED],
            },
        })
        await websocket.close()
        return

    # --- Token 并发控制 (P4.2) ---
    if token and auth:
        token_info = auth.validate_token(token)
        if token_info is None:
            await websocket.accept()
            await websocket.send_json({
                "type": "error",
                "payload": {
                    "code": ErrorCode.AUTH_FAILED.value,
                    "message": ERROR_CODE_DESCRIPTION[ErrorCode.TOKEN_INVALID],
                },
            })
            await websocket.close()
            return

    # --- 接受连接 ---
    await websocket.accept()
    conn = await ws_mgr.add_connection(websocket, token=token or "", ip=client_ip)
    if conn is None:
        await websocket.close()
        return

    monitor.record_connect(conn.connection_id)

    # Token 用户关联
    if token and auth:
        token_info = auth.validate_token(token)
        if token_info:
            conn.user = token_info.get("user", "")

    # --- 标记连接为 active ---
    await ws_mgr.mark_active(conn.connection_id)

    # --- 启动心跳 (P0.3) ---
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(ws_mgr, conn.connection_id, HEARTBEAT_INTERVAL_SECONDS)
    )

    try:
        # --- 消息接收循环 (P0.2) ---
        while True:
            raw_message = await websocket.receive_text()

            # 心跳 pong 响应
            if raw_message == "pong":
                await ws_mgr.handle_pong(conn.connection_id)
                continue

            monitor.record_message(conn.connection_id)

            try:
                message_type, payload, message_id = parser.parse(raw_message)
            except (ValueError, KeyError, Exception) as e:
                response = {
                    "type": MessageType.ERROR.value,
                    "payload": {
                        "code": ErrorCode.INVALID_MESSAGE.value,
                        "message": str(e),
                    },
                }
                if message_id:
                    response["id"] = message_id
                await websocket.send_json(response)
                continue

            # --- 订阅/取消订阅 (内部处理) ---
            if message_type == MessageType.SUBSCRIBE.value:
                topic = payload.get("topic", "")
                if topic:
                    success = await broadcast_mgr.subscribe(conn.connection_id, topic)
                    await websocket.send_json({
                        "type": MessageType.SUBSCRIBE.value,
                        "payload": {"topic": topic, "success": success},
                    })
                continue

            if message_type == MessageType.UNSUBSCRIBE.value:
                topic = payload.get("topic", "")
                if topic:
                    await broadcast_mgr.unsubscribe(conn.connection_id, topic)
                    await websocket.send_json({
                        "type": MessageType.UNSUBSCRIBE.value,
                        "payload": {"topic": topic, "success": True},
                    })
                continue

            # --- 路由到处理器 ---
            response = await router.route(message_type, payload)
            if response and response.get("payload"):
                if message_id:
                    response["id"] = message_id
                await websocket.send_json(response)

    except WebSocketDisconnect:  # P0.5: 客户端主动断开
        pass
    except Exception:  # P0.5: 网络断开等异常
        pass
    finally:
        # --- 关闭清理 (P0.5) ---
        conn.status.value = "closing"
        heartbeat_task.cancel()

        await broadcast_mgr.unsubscribe_all(conn.connection_id)
        monitor.record_disconnect(conn.connection_id)
        await ws_mgr.remove_connection(conn.connection_id)


# ------------------------------------------------------------------ #
#  工具函数
# ------------------------------------------------------------------ #

def _error_response(error_code: ErrorCode, message: str = "") -> dict[str, Any]:
    """构造错误响应。"""
    return {
        "type": MessageType.ERROR.value,
        "payload": {
            "code": error_code.value,
            "message": message or ERROR_CODE_DESCRIPTION.get(error_code, "未知错误"),
        },
    }


# ================================================================== #
#  消息注册 (P0.2) - 各业务类型注册到路由器
# ================================================================== #

def _get_message_router() -> MessageRouter:
    """获取/创建消息路由器。

    Returns:
        已注册各消息类型处理器的 MessageRouter
    """
    router = MessageRouter()

    # 流控制
    async def _handle_stream_start(payload: dict) -> dict[str, Any]:
        """处理流启动请求 (P2.3)。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return _error_response(ErrorCode.INVALID_MESSAGE, "缺少 device_mac")
        return {
            "type": MessageType.STREAM_START.value,
            "payload": {"device_mac": device_mac, "status": "started"},
        }

    async def _handle_stream_stop(payload: dict) -> dict[str, Any]:
        """处理流停止请求 (P2.3)。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return _error_response(ErrorCode.INVALID_MESSAGE, "缺少 device_mac")
        return {
            "type": MessageType.STREAM_STOP.value,
            "payload": {"device_mac": device_mac, "status": "stopped"},
        }

    # PTZ 命令
    async def _handle_ptz_command(payload: dict) -> dict[str, Any]:
        """处理 PTZ 控制命令 (P3.1)。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return _error_response(ErrorCode.INVALID_MESSAGE, "缺少 device_mac")
        return {
            "type": MessageType.PTZ_COMMAND.value,
            "payload": {"device_mac": device_mac, "status": "sent", "command": payload.get("command")},
        }

    router.register(MessageType.STREAM_START, _handle_stream_start)
    router.register(MessageType.STREAM_STOP, _handle_stream_stop)
    router.register(MessageType.PTZ_COMMAND, _handle_ptz_command)

    # 参数设置
    async def _handle_param_set(payload: dict) -> dict[str, Any]:
        """处理参数设置 (P3.2)。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return _error_response(ErrorCode.INVALID_MESSAGE, "缺少 device_mac")
        return {
            "type": MessageType.PARAM_SET.value,
            "payload": {"device_mac": device_mac, "status": "applied"},
        }

    # 批量命令
    async def _handle_batch_command(payload: dict) -> dict[str, Any]:
        """处理批量命令 (P3.3)。"""
        device_macs = payload.get("device_macs", [])
        if not device_macs:
            return _error_response(ErrorCode.INVALID_MESSAGE, "缺少 device_macs")
        return {
            "type": MessageType.BATCH_COMMAND.value,
            "payload": {
                "device_count": len(device_macs),
                "status": "queued",
                "success_count": len(device_macs),
                "failed_count": 0,
            },
        }

    router.register(MessageType.PARAM_SET, _handle_param_set)
    router.register(MessageType.BATCH_COMMAND, _handle_batch_command)

    return router


# ------------------------------------------------------------------ #
#  工具函数
# ------------------------------------------------------------------ #

def _error_response(error_code: ErrorCode, message: str = "") -> dict[str, Any]:
    """构造错误响应。"""
    return {
        "type": MessageType.ERROR.value,
        "payload": {
            "code": error_code.value,
            "message": message or ERROR_CODE_DESCRIPTION.get(error_code, "未知错误"),
        },
    }
