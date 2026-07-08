"""
M8 WebSocket v1.0 - 消息路由与协议解析

实现:
- P0.2: 消息格式 {type, payload}，按 type 路由
- P0.2: 未知类型返回错误
- 协议解析与消息验证

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
from typing import Any, Callable, Awaitable

from src.websocket.constants import (
    MSG_ID_KEY,
    MSG_PAYLOAD_KEY,
    MSG_TYPE_KEY,
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    MessageType,
)

# ------------------------------------------------------------------ #
#  消息处理器类型
# ------------------------------------------------------------------ #

HandlerType = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


# ================================================================== #
#  消息路由器
# ================================================================== #

class MessageRouter:
    """将 WebSocket 消息路由到对应的处理器。"""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerType] = {}

    def register(self, message_type: MessageType | str, handler: HandlerType) -> None:
        """注册消息类型处理器。

        Args:
            message_type: 消息类型 (枚举或字符串)
            handler: 异步处理函数 (接收 payload, 返回响应或 None)
        """
        key = message_type.value if isinstance(message_type, MessageType) else message_type
        self._handlers[key] = handler

    def has_handler(self, message_type: str) -> bool:
        """检查是否注册了指定消息类型的处理器。

        Args:
            message_type: 消息类型字符串

        Returns:
            是否已注册
        """
        return message_type in self._handlers

    async def route(self, message_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """路由消息到对应处理器。

        Args:
            message_type: 消息类型字符串
            payload: 消息 payload

        Returns:
            处理结果, 或 None (如果处理器不返回响应)

        Raises:
            ValueError: 未知消息类型
        """
        handler = self._handlers.get(message_type)
        if handler is None:
            return _error_response(ErrorCode.UNKNOWN_MESSAGE_TYPE, f"未知消息类型: {message_type}")
        return await handler(payload)


# ================================================================== #
#  消息解析器
# ================================================================== #

class MessageParser:
    """解析和验证 WebSocket 消息格式。"""

    @staticmethod
    def parse(raw_message: str | bytes) -> tuple[str, dict[str, Any], str | None]:
        """解析原始消息。

        Args:
            raw_message: 原始 WebSocket 消息 (字符串或字节)

        Returns:
            (message_type, payload, message_id)

        Raises:
            json.JSONDecodeError: JSON 格式无效
            ValueError: 缺少 type 字段或格式错误
        """
        if isinstance(raw_message, bytes):
            raw_message = raw_message.decode("utf-8")

        # 心跳消息直接返回
        if raw_message in ("ping", "pong"):
            return (raw_message, {}, None)

        data = json.loads(raw_message)

        if not isinstance(data, dict):
            raise ValueError("消息必须是 JSON 对象")

        message_type = data.get(MSG_TYPE_KEY)
        if not message_type:
            raise ValueError(f"消息缺少 '{MSG_TYPE_KEY}' 字段")

        payload = data.get(MSG_PAYLOAD_KEY, {})
        if not isinstance(payload, dict):
            raise ValueError(f"'{MSG_PAYLOAD_KEY}' 必须是对象")

        message_id = data.get(MSG_ID_KEY)

        return (str(message_type), payload, message_id)

    @staticmethod
    def parse_json(data: dict) -> tuple[str, dict[str, Any], str | None]:
        """从已解析的 JSON 字典中提取消息信息。

        Args:
            data: JSON 字典

        Returns:
            (message_type, payload, message_id)
        """
        message_type = data.get(MSG_TYPE_KEY, "")
        payload = data.get(MSG_PAYLOAD_KEY, {})
        message_id = data.get(MSG_ID_KEY)
        return (str(message_type), payload if isinstance(payload, dict) else {}, message_id)

    @staticmethod
    def build_response(
        data: dict[str, Any],
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """构建标准响应消息。

        Args:
            data: 响应数据
            message_id: 原始消息 ID (用于关联)

        Returns:
            标准 JSON 响应结构
        """
        response: dict[str, Any] = {
            MSG_TYPE_KEY: data.get(MSG_TYPE_KEY, "response"),
            MSG_PAYLOAD_KEY: data.get(MSG_PAYLOAD_KEY, data),
        }
        if message_id:
            response[MSG_ID_KEY] = message_id
        return response


# ------------------------------------------------------------------ #
#  工具函数
# ------------------------------------------------------------------ #

def _error_response(error_code: ErrorCode, message: str = "") -> dict[str, Any]:
    """构造标准错误响应。"""
    return {
        MSG_TYPE_KEY: MessageType.ERROR.value,
        MSG_PAYLOAD_KEY: {
            "code": error_code.value,
            "message": message or ERROR_CODE_DESCRIPTION.get(error_code, "未知错误"),
        },
    }


def error_response(error_code: ErrorCode, message: str = "", message_id: str | None = None) -> dict[str, Any]:
    """公共错误响应接口。

    Args:
        error_code: 错误码枚举
        message: 错误信息
        message_id: 关联的消息 ID

    Returns:
        标准错误响应 JSON
    """
    resp = _error_response(error_code, message)
    if message_id:
        resp[MSG_ID_KEY] = message_id
    return resp
