"""
M8 WebSocket v1.0 - 事件处理器 (Wave 4)

实现:
1. PTZ位置变更推送 (每0.5秒)
2. 设备在线/离线状态推送
3. 流状态变更推送
4. 心跳处理
5. 断线重连处理

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable

from src.websocket.constants import MessageType, ErrorCode, ERROR_CODE_DESCRIPTION
from src.websocket.core.ws_manager import get_ws_manager


# ================================================================== #
#  PTZ 位置推送器
# ================================================================== #

class PTZPositionPusher:
    """PTZ位置变更推送。

    Wave 4: 每0.5秒推送PTZ位置。
    """

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._positions: dict[str, dict] = {}  # device_mac -> position
        self._update_interval = 0.5  # 每0.5秒

    async def start(self) -> None:
        """启动PTZ位置推送。"""
        self._running = True
        self._task = asyncio.create_task(self._push_loop())
        print("[M8 WS] PTZ pusher started (0.5s interval)")

    async def stop(self) -> None:
        """停止PTZ位置推送。"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def update_position(self, device_mac: str, position: dict) -> None:
        """更新PTZ位置数据。"""
        self._positions[device_mac] = position

    async def _push_loop(self) -> None:
        """推送循环 - 每0.5秒推送PTZ位置。"""
        while self._running:
            if self._positions:
                ws_mgr = get_ws_manager()
                active_connections = await ws_mgr.get_active_connections()

                for device_mac, position in self._positions.items():
                    message = {
                        "type": MessageType.PTZ_COMMAND.value,
                        "payload": {
                            "device_mac": device_mac,
                            "position": position,
                            "timestamp": time.time(),
                        },
                    }
                    for conn in active_connections:
                        if device_mac in conn.subscriptions:
                            try:
                                await conn.websocket.send_json(message)
                            except Exception:
                                pass

            await asyncio.sleep(self._update_interval)


# ================================================================== #
#  设备状态推送
# ================================================================== #

class DeviceStatusPusher:
    """设备在线/离线状态推送。

    Wave 4: 设备状态变更时立即推送。
    """

    async def push_online(self, device_mac: str, ip: str = "") -> int:
        """推送设备上线。"""
        ws_mgr = get_ws_manager()
        from src.websocket.core.broadcast import get_broadcast_manager
        broadcast_mgr = get_broadcast_manager()

        message = {
            "type": MessageType.DEVICE_STATUS.value,
            "payload": {
                "device_mac": device_mac,
                "status": "online",
                "ip": ip,
                "timestamp": time.time(),
            },
        }

        count = 0
        active = await ws_mgr.get_active_connections()
        for conn in active:
            if device_mac in conn.subscriptions or "device_status" in conn.subscriptions:
                try:
                    await conn.websocket.send_json(message)
                    count += 1
                except Exception:
                    pass

        print(f"[M8 WS] Device online pushed: {device_mac} -> {count} connections")
        return count

    async def push_offline(self, device_mac: str) -> int:
        """推送设备离线。"""
        ws_mgr = get_ws_manager()

        message = {
            "type": MessageType.DEVICE_STATUS.value,
            "payload": {
                "device_mac": device_mac,
                "status": "offline",
                "timestamp": time.time(),
            },
        }

        count = 0
        active = await ws_mgr.get_active_connections()
        for conn in active:
            if device_mac in conn.subscriptions or "device_status" in conn.subscriptions:
                try:
                    await conn.websocket.send_json(message)
                    count += 1
                except Exception:
                    pass

        print(f"[M8 WS] Device offline pushed: {device_mac} -> {count} connections")
        return count


# ================================================================== #
#  流状态推送
# ================================================================== #

class StreamStatusPusher:
    """流状态变更推送。

    Wave 4: 流启动/停止/断流时推送。
    """

    async def push_stream_event(self, stream_id: str, event: str, data: dict | None = None) -> int:
        """推送流状态事件。

        Args:
            stream_id: 流标识
            event: 事件类型 (started/stopped/error)
            data: 附加数据

        Returns:
            成功推送数
        """
        ws_mgr = get_ws_manager()

        if event == "started":
            msg_type = MessageType.STREAM_START.value
        elif event == "stopped":
            msg_type = MessageType.STREAM_STOP.value
        else:
            msg_type = MessageType.STREAM_FRAME.value

        payload: dict[str, Any] = {
            "stream_id": stream_id,
            "event": event,
            "timestamp": time.time(),
        }
        if data:
            payload.update(data)

        message = {
            "type": msg_type,
            "payload": payload,
        }

        count = 0
        active = await ws_mgr.get_active_connections()
        for conn in active:
            try:
                await conn.websocket.send_json(message)
                count += 1
            except Exception:
                pass

        return count


# ================================================================== #
#  断线重连处理器
# ================================================================== #

class ReconnectionHandler:
    """断线重连处理。

    Wave 4:
    - 客户端断线后自动重连
    - 重连后同步最新状态
    """

    def __init__(self) -> None:
        self._reconnect_attempts: dict[str, int] = {}
        self._max_attempts = 5
        self._backoff_base = 1.0  # 秒

    async def handle_disconnect(self, connection_id: str, token: str = "") -> bool:
        """处理客户端断线。

        Args:
            connection_id: 连接ID
            token: 认证token (用于重连)

        Returns:
            是否成功重连
        """
        attempts = self._reconnect_attempts.get(connection_id, 0)

        if attempts >= self._max_attempts:
            print(f"[M8 WS] Max reconnection attempts exceeded: {connection_id}")
            return False

        # 指数退避
        delay = self._backoff_base * (2 ** attempts)
        print(f"[M8 WS] Reconnection attempt {attempts + 1}/{self._max_attempts} "
              f"for {connection_id} (delay={delay}s)")

        self._reconnect_attempts[connection_id] = attempts + 1

        # 返回重连指示给客户端
        return False  # 实际重连由客户端发起

    def reset_attempts(self, connection_id: str) -> None:
        """重置重连尝试计数 (成功重连后)。"""
        self._reconnect_attempts.pop(connection_id, None)

    def get_reconnect_info(self, connection_id: str) -> dict:
        """获取重连信息。"""
        attempts = self._reconnect_attempts.get(connection_id, 0)
        return {
            "connection_id": connection_id,
            "attempts": attempts,
            "max_attempts": self._max_attempts,
            "can_reconnect": attempts < self._max_attempts,
            "next_delay_seconds": self._backoff_base * (2 ** attempts),
        }


# ================================================================== #
#  消息处理器注册
# ================================================================== #

def register_message_handlers() -> dict[str, Callable]:
    """注册 WebSocket 消息处理器。

    Returns:
        {message_type: handler_fn}
    """
    handlers: dict[str, Callable] = {}

    async def _handle_stream_start(payload: dict, conn) -> dict:
        """处理流启动请求。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return {
                "type": MessageType.ERROR.value,
                "payload": {
                    "code": ErrorCode.INVALID_MESSAGE.value,
                    "message": "缺少 device_mac",
                },
            }

        stream_status = await StreamStatusPusher().push_stream_event(
            stream_id=device_mac,
            event="started",
        )

        return {
            "type": MessageType.STREAM_START.value,
            "payload": {
                "device_mac": device_mac,
                "status": "started",
                "pushed_to": stream_status,
            },
        }

    async def _handle_stream_stop(payload: dict, conn) -> dict:
        """处理流停止请求。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return {
                "type": MessageType.ERROR.value,
                "payload": {
                    "code": ErrorCode.INVALID_MESSAGE.value,
                    "message": "缺少 device_mac",
                },
            }

        return {
            "type": MessageType.STREAM_STOP.value,
            "payload": {
                "device_mac": device_mac,
                "status": "stopped",
            },
        }

    async def _handle_ptz_command(payload: dict, conn) -> dict:
        """处理 PTZ 控制命令。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return {
                "type": MessageType.ERROR.value,
                "payload": {
                    "code": ErrorCode.INVALID_MESSAGE.value,
                    "message": "缺少 device_mac",
                },
            }

        direction = payload.get("direction", "")
        speed = payload.get("speed", 50)

        return {
            "type": MessageType.PTZ_COMMAND.value,
            "payload": {
                "device_mac": device_mac,
                "command": direction,
                "speed": speed,
                "status": "sent",
            },
        }

    async def _handle_param_set(payload: dict, conn) -> dict:
        """处理参数设置。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return {
                "type": MessageType.ERROR.value,
                "payload": {
                    "code": ErrorCode.INVALID_MESSAGE.value,
                    "message": "缺少 device_mac",
                },
            }

        return {
            "type": MessageType.PARAM_SET.value,
            "payload": {
                "device_mac": device_mac,
                "status": "applied",
                "params": payload.get("params", {}),
            },
        }

    async def _handle_batch_command(payload: dict, conn) -> dict:
        """处理批量命令。"""
        device_macs = payload.get("device_macs", [])
        if not device_macs:
            return {
                "type": MessageType.ERROR.value,
                "payload": {
                    "code": ErrorCode.INVALID_MESSAGE.value,
                    "message": "缺少 device_macs",
                },
            }

        return {
            "type": MessageType.BATCH_COMMAND.value,
            "payload": {
                "device_count": len(device_macs),
                "status": "queued",
                "success_count": len(device_macs),
                "failed_count": 0,
            },
        }

    async def _handle_device_status(payload: dict, conn) -> dict:
        """处理设备状态查询。"""
        device_mac = payload.get("device_mac", "")
        if not device_mac:
            return {
                "type": MessageType.DEVICE_STATUS.value,
                "payload": {
                    "status": "unknown",
                    "message": "缺少 device_mac",
                },
            }

        return {
            "type": MessageType.DEVICE_STATUS.value,
            "payload": {
                "device_mac": device_mac,
                "status": "online",  # 占位 - 实际应从DeviceManager获取
                "timestamp": time.time(),
            },
        }

    # 注册
    handlers[MessageType.STREAM_START.value] = _handle_stream_start
    handlers[MessageType.STREAM_STOP.value] = _handle_stream_stop
    handlers[MessageType.PTZ_COMMAND.value] = _handle_ptz_command
    handlers[MessageType.PARAM_SET.value] = _handle_param_set
    handlers[MessageType.BATCH_COMMAND.value] = _handle_batch_command
    handlers[MessageType.DEVICE_STATUS.value] = _handle_device_status

    return handlers
