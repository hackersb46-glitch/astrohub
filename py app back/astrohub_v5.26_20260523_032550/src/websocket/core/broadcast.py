"""
M8 WebSocket v1.0 - 广播与订阅系统

实现:
- P1.1: 设备状态变更推送 (向订阅者推送)
- P1.2: 在线状态广播 (向所有连接广播)
- P1.3: 异常通知 (向订阅者推送)
- P2: 流数据推送
- 发布/订阅模式

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.websocket.core.ws_manager import WSConnection, WSManager, get_ws_manager
from src.websocket.constants import (
    MSG_PAYLOAD_KEY,
    MSG_TYPE_KEY,
    MessageType,
)


# ================================================================== #
#  发布/订阅广播系统
# ================================================================== #

class BroadcastManager:
    """管理订阅关系与消息广播。"""

    def __init__(self, ws_manager: WSManager | None = None) -> None:
        self._ws_manager = ws_manager or get_ws_manager()
        # 主题 (设备MAC等) -> connection_id 集合
        self._subscriptions: dict[str, set[str]] = {}

    async def subscribe(self, connection_id: str, topic: str) -> bool:
        """订阅指定主题 (设备/事件)。

        Args:
            connection_id: 连接 ID
            topic: 订阅主题 (如设备 MAC 地址)

        Returns:
            是否订阅成功
        """
        conn = await self._ws_manager.get_connection(connection_id)
        if conn is None or conn.status in (None, "closed", "closing"):
            return False

        # 添加到连接的订阅列表
        conn.subscriptions.add(topic)
        # 添加到主题的连接列表
        self._subscriptions.setdefault(topic, set()).add(connection_id)

        return True

    async def unsubscribe(self, connection_id: str, topic: str) -> bool:
        """取消订阅指定主题。

        Args:
            connection_id: 连接 ID
            topic: 订阅主题

        Returns:
            是否取消成功
        """
        conn = await self._ws_manager.get_connection(connection_id)
        if conn is None:
            return False

        conn.subscriptions.discard(topic)

        topic_connections = self._subscriptions.get(topic)
        if topic_connections:
            topic_connections.discard(connection_id)
            if not topic_connections:
                del self._subscriptions[topic]

        return True

    async def unsubscribe_all(self, connection_id: str) -> None:
        """取消指定连接的所有订阅。

        Args:
            connection_id: 连接 ID
        """
        conn = await self._ws_manager.get_connection(connection_id)
        if conn is None:
            return

        for topic in list(conn.subscriptions):
            topic_connections = self._subscriptions.get(topic)
            if topic_connections:
                topic_connections.discard(connection_id)
                if not topic_connections:
                    del self._subscriptions[topic]

        conn.subscriptions.clear()

    async def publish_to_topic(self, topic: str, message_type: MessageType | str, data: dict[str, Any]) -> int:
        """向指定主题的所有订阅者推送消息 (P1.1)。

        Args:
            topic: 订阅主题
            message_type: 消息类型
            data: 消息数据

        Returns:
            成功推送的连接数
        """
        topic_connections = self._subscriptions.get(topic, set())
        count = 0

        payload_msg = {
            MSG_TYPE_KEY: message_type.value if isinstance(message_type, MessageType) else message_type,
            MSG_PAYLOAD_KEY: data,
        }

        for conn_id in topic_connections:
            if await self._ws_manager.send_to_connection(conn_id, payload_msg):
                count += 1

        return count

    async def publish_to_all(self, message_type: MessageType | str, data: dict[str, Any]) -> int:
        """向所有活跃连接广播消息 (P1.2)。

        Args:
            message_type: 消息类型
            data: 消息数据

        Returns:
            成功推送的连接数
        """
        active_connections = await self._ws_manager.get_active_connections()
        count = 0

        payload_msg = {
            MSG_TYPE_KEY: message_type.value if isinstance(message_type, MessageType) else message_type,
            MSG_PAYLOAD_KEY: data,
        }

        for conn in active_connections:
            if await self._ws_manager.send_to_connection(conn.connection_id, payload_msg):
                count += 1

        return count

    async def publish_device_status(self, device_mac: str, status: str, timestamp: str) -> int:
        """推送设备状态变更 (P1.1)。

        Args:
            device_mac: 设备 MAC 地址
            status: 新状态 (online/offline/error 等)
            timestamp: 状态变更时间戳

        Returns:
            成功推送数
        """
        data = {
            "device_mac": device_mac,
            "status": status,
            "timestamp": timestamp,
        }
        return await self.publish_to_topic(device_mac, MessageType.DEVICE_STATUS, data)

    async def broadcast_device_online(self, devices: list[dict[str, Any]], timestamp: str) -> int:
        """广播所有设备在线状态 (P1.2)。

        Args:
            devices: 设备在线状态列表 [{"mac": "", "ip": "", "status": ""}, ...]
            timestamp: 广播时间戳

        Returns:
            成功推送数
        """
        data = {
            "devices": devices,
            "total": len(devices),
            "timestamp": timestamp,
        }
        return await self.publish_to_all(MessageType.DEVICE_ONLINE_BROADCAST, data)

    async def push_device_alert(self, device_mac: str, alert_type: str, message: str,
                                timestamp: str, suggestion: str = "") -> int:
        """推送设备异常通知 (P1.3)。

        Args:
            device_mac: 设备 MAC 地址
            alert_type: 异常类型 (断流/认证失败/离线)
            message: 异常描述
            timestamp: 异常时间戳
            suggestion: 建议操作

        Returns:
            成功推送数
        """
        data = {
            "device_mac": device_mac,
            "alert_type": alert_type,
            "message": message,
            "timestamp": timestamp,
            "suggestion": suggestion,
        }
        return await self.publish_to_topic(device_mac, MessageType.DEVICE_ALERT, data)

    async def push_stream_frame(self, connection_id: str, device_mac: str, frame_data: bytes | str) -> bool:
        """推送视频帧到指定连接 (P2.1)。

        Args:
            connection_id: 目标连接 ID
            device_mac: 设备 MAC
            frame_data: 视频帧数据 (base64 字符串或二进制)

        Returns:
            是否推送成功
        """
        msg = {
            MSG_TYPE_KEY: MessageType.STREAM_FRAME.value,
            MSG_PAYLOAD_KEY: {
                "device_mac": device_mac,
                "data": frame_data,
            },
        }
        return await self._ws_manager.send_to_connection(connection_id, msg)

    async def push_stream_audio(self, connection_id: str, device_mac: str, audio_data: bytes | str) -> bool:
        """推送音频数据到指定连接 (P2.2)。

        Args:
            connection_id: 目标连接 ID
            device_mac: 设备 MAC
            audio_data: 音频数据

        Returns:
            是否推送成功
        """
        msg = {
            MSG_TYPE_KEY: MessageType.STREAM_AUDIO.value,
            MSG_PAYLOAD_KEY: {
                "device_mac": device_mac,
                "data": audio_data,
            },
        }
        return await self._ws_manager.send_to_connection(connection_id, msg)

    def get_subscription_stats(self) -> dict[str, Any]:
        """获取订阅统计信息。

        Returns:
            订阅统计字典
        """
        return {
            "total_topics": len(self._subscriptions),
            "total_subscriptions": sum(len(subs) for subs in self._subscriptions.values()),
            "topics": {
                topic: len(subs) for topic, subs in self._subscriptions.items()
            },
        }


# ================================================================== #
#  全局单例
# ================================================================== #

_broadcast_manager: BroadcastManager | None = None


def get_broadcast_manager() -> BroadcastManager:
    """获取全局 BroadcastManager 实例。"""
    return _broadcast_manager  # type: ignore[return-value]


def init_broadcast_manager(ws_manager: WSManager | None = None) -> BroadcastManager:
    """初始化全局 BroadcastManager 实例。

    Args:
        ws_manager: WSManager 实例 (可选)

    Returns:
        BroadcastManager 实例
    """
    global _broadcast_manager
    _broadcast_manager = BroadcastManager(ws_manager=ws_manager)
    return _broadcast_manager
