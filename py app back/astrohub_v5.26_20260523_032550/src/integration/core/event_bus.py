"""
M10 Integration v1.0 - 事件发布订阅

跨模块事件总线，支持同步/异步事件分发，用于模块间松耦合通信。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

from integration.constants import EventType

logger = logging.getLogger("integration")


# 订阅回调类型
Handler = Callable[..., Any]
AsyncHandler = Callable[..., Coroutine[Any, Any, Any]]


class EventBus:
    """事件发布-订阅总线。

    各模块通过事件总线广播状态变更、流程进展等，
    避免直接的模块间耦合。
    """

    def __init__(self) -> None:
        self._subscribers: dict[EventType, list[Handler | AsyncHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: Handler | AsyncHandler) -> None:
        """订阅事件。

        Args:
            event_type: 事件类型
            handler: 回调函数 (同步或异步均可)
        """
        self._subscribers[event_type].append(handler)
        logger.debug("[M10 INTEGRATION] 订阅事件: %s, 当前订阅者: %d", event_type.value, len(self._subscribers[event_type]))

    def unsubscribe(self, event_type: EventType, handler: Handler | AsyncHandler) -> bool:
        """取消订阅。

        Returns:
            True 如果成功移除, False 如果未找到
        """
        handlers = self._subscribers.get(event_type, [])
        try:
            handlers.remove(handler)
            return True
        except ValueError:
            return False

    async def publish(self, event_type: EventType, **kwargs: Any) -> int:
        """异步发布事件，等待所有处理器完成。

        Args:
            event_type: 事件类型
            **kwargs: 事件数据

        Returns:
            处理的订阅者数量
        """
        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            return 0

        done = 0
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(**kwargs)
                else:
                    handler(**kwargs)
                done += 1
            except Exception as exc:
                logger.error(
                    "[M10 INTEGRATION] 事件处理器异常: %s, handler=%s, error=%s",
                    event_type.value, handler.__name__ if hasattr(handler, "__name__") else str(handler), exc,
                )

        logger.debug("[M10 INTEGRATION] 事件 %s 已分发, %d 个处理器已处理", event_type.value, done)
        return done

    def publish_sync(self, event_type: EventType, **kwargs: Any) -> int:
        """同步发布事件 (仅调用同步处理器)。"""
        handlers = self._subscribers.get(event_type, [])
        if not handlers:
            return 0

        done = 0
        for handler in handlers:
            if asyncio.iscoroutinefunction(handler):
                continue
            try:
                handler(**kwargs)
                done += 1
            except Exception as exc:
                logger.error("[M10 INTEGRATION] 同步事件处理器异常: %s, error=%s", event_type.value, exc)
        return done

    def subscriber_count(self, event_type: EventType | None = None) -> int:
        """返回订阅者数量。"""
        if event_type is not None:
            return len(self._subscribers.get(event_type, []))
        return sum(len(v) for v in self._subscribers.values())


# 全局实例
_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局事件总线。"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
