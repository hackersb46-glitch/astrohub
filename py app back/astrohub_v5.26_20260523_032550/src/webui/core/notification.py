"""
M6 Web UI Service v1.0 - 通知系统

提供操作通知、错误提示的管理功能，支持 Toast/Modal 等前端通知类型。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from webui.constants import NotificationLevel, MAX_NOTIFICATION_COUNT


@dataclass
class Notification:
    """单个通知项。"""

    id: str
    level: str
    message: str
    timestamp: str
    title: Optional[str] = None
    duration: int = 5000  # 前端自动消失时间（ms）
    read: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class NotificationManager:
    """通知管理器。

    管理通知的创建、查询、标记已读、清理。
    使用内存双端队列存储，限制最大通知数量。
    """

    def __init__(self, max_count: int = MAX_NOTIFICATION_COUNT):
        """初始化通知管理器。

        Args:
            max_count: 最大保留通知数，超出后自动清理最旧通知
        """
        self._notifications: deque[Notification] = deque(maxlen=max_count)
        self._max_count = max_count

    def add(
        self,
        level: NotificationLevel,
        message: str,
        title: Optional[str] = None,
        duration: int = 5000,
    ) -> Notification:
        """添加新通知。

        Args:
            level: 通知等级（info/warning/error/success）
            message: 通知内容
            title: 通知标题（可选）
            duration: 前端自动消失时间（ms），默认 5000

        Returns:
            创建的通知对象
        """
        notification = Notification(
            id=str(uuid.uuid4())[:8],
            level=level.value if isinstance(level, NotificationLevel) else level,
            message=message,
            timestamp=datetime.now().isoformat(),
            title=title,
            duration=duration,
        )
        self._notifications.appendleft(notification)
        return notification

    def get_all(self, limit: int = 50) -> list[dict]:
        """获取所有通知（按时间倒序）。

        Args:
            limit: 返回数量上限

        Returns:
            通知列表（字典形式）
        """
        return [n.to_dict() for n in list(self._notifications)[:limit]]

    def get_unread(self) -> list[dict]:
        """获取未读通知。

        Returns:
            未读通知列表
        """
        return [n.to_dict() for n in self._notifications if not n.read]

    def mark_read(self, notification_id: str) -> bool:
        """标记通知为已读。

        Args:
            notification_id: 通知 ID

        Returns:
            是否找到并标记成功
        """
        for n in self._notifications:
            if n.id == notification_id:
                n.read = True
                return True
        return False

    def mark_all_read(self) -> int:
        """标记所有通知为已读。

        Returns:
            标记的通知数量
        """
        count = sum(1 for n in self._notifications if not n.read)
        for n in self._notifications:
            n.read = True
        return count

    def clear(self, level: Optional[NotificationLevel] = None) -> int:
        """清理通知。

        Args:
            level: 指定清理的通知等级，None 则清理全部

        Returns:
            清理的通知数量
        """
        if level is None:
            count = len(self._notifications)
            self._notifications.clear()
            return count

        level_value = level.value if isinstance(level, NotificationLevel) else level
        to_remove = [n for n in self._notifications if n.level == level_value]
        for n in to_remove:
            self._notifications.remove(n)
        return len(to_remove)

    def count(self, level: Optional[NotificationLevel] = None) -> int:
        """统计通知数量。

        Args:
            level: 指定等级的通知数，None 则统计全部

        Returns:
            通知数量
        """
        if level is None:
            return len(self._notifications)

        level_value = level.value if isinstance(level, NotificationLevel) else level
        return sum(1 for n in self._notifications if n.level == level_value)
