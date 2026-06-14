"""
M7 REST API v1.0 - 限流器

实现:
- 滑动窗口限流 (P5.3)
- 按 IP / Token 区分限流
- 自定义限流层级 (free/standard/premium)

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from rest_api.constants import (
    RateLimitTier,
    RATE_LIMIT_DEFAULT_REQUESTS,
    RATE_LIMIT_DEFAULT_WINDOW,
    RATE_LIMIT_MAX_REQUESTS,
    RATE_LIMIT_CLEANUP_INTERVAL,
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
)


# ------------------------------------------------------------------ #
#  滑动窗口限流器
# ------------------------------------------------------------------ #

class RateLimiter:
    """基于滑动窗口的请求限流器。

    使用单调递增时间戳记录每个客户端的请求时间，
    在窗口内检查请求数量是否超过阈值。
    """

    # 各层级的请求限制映射
    TIER_LIMITS = {
        RateLimitTier.FREE: RATE_LIMIT_DEFAULT_REQUESTS,
        RateLimitTier.STANDARD: 500,
        RateLimitTier.PREMIUM: RATE_LIMIT_MAX_REQUESTS,
    }

    def __init__(
        self,
        default_requests: int = RATE_LIMIT_DEFAULT_REQUESTS,
        window_seconds: int = RATE_LIMIT_DEFAULT_WINDOW,
        cleanup_interval: int = RATE_LIMIT_CLEANUP_INTERVAL,
    ):
        self._default_limit = default_requests
        self._window = window_seconds
        self._cleanup_interval = cleanup_interval

        # client_key -> [timestamp1, timestamp2, ...]
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
        self._last_cleanup = time.monotonic()

        # tier 覆盖: client_key -> override_limit
        self._tier_overrides: dict[str, int] = {}

    def set_tier(self, client_key: str, tier: RateLimitTier) -> None:
        """设置客户端的限流层级。

        Args:
            client_key: 客户端标识 (IP 或 token)
            tier: 限流层级
        """
        self._tier_overrides[client_key] = self.TIER_LIMITS[tier]

    def remove_tier(self, client_key: str) -> bool:
        """移除客户端的限流层级覆盖, 恢复默认。"""
        if client_key in self._tier_overrides:
            del self._tier_overrides[client_key]
            return True
        return False

    def is_allowed(self, client_key: str) -> bool:
        """检查客户端的请求是否被允许。

        Args:
            client_key: 客户端标识

        Returns:
            True = 允许请求, False = 已超限
        """
        with self._lock:
            now = time.monotonic()

            # 定期清理过期记录
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup()
                self._last_cleanup = now

            limit = self._get_limit(client_key)
            timestamps = self._requests[client_key]

            # 移除超出窗口的旧时间戳
            cutoff = now - self._window
            timestamps[:] = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= limit:
                return False

            # 记录本次请求
            timestamps.append(now)
            return True

    def get_remaining(self, client_key: str) -> int:
        """获取客户端剩余可用请求数。

        Args:
            client_key: 客户端标识

        Returns:
            剩余请求数 (>=0)
        """
        with self._lock:
            now = time.monotonic()
            limit = self._get_limit(client_key)
            timestamps = self._requests[client_key]

            cutoff = now - self._window
            active_count = sum(1 for t in timestamps if t > cutoff)
            return max(0, limit - active_count)

    def reset(self, client_key: str) -> None:
        """重置特定客户端的限流计数。"""
        with self._lock:
            if client_key in self._requests:
                del self._requests[client_key]

    def _get_limit(self, client_key: str) -> int:
        """获取客户端的限流阈值。"""
        return self._tier_overrides.get(client_key, self._default_limit)

    def _cleanup(self) -> None:
        """清理所有过期的时间戳记录。"""
        now = time.monotonic()
        cutoff = now - self._window

        expired_keys = []
        for key, timestamps in self._requests.items():
            timestamps[:] = [t for t in timestamps if t > cutoff]
            if not timestamps:
                expired_keys.append(key)

        for key in expired_keys:
            del self._requests[key]


# ------------------------------------------------------------------ #
#  限流响应
# ------------------------------------------------------------------ #

def rate_limit_exceeded_response() -> dict:
    """构造限流超限的标准错误响应 (P5.3)。"""
    return {
        "error": {
            "code": ErrorCode.RATE_LIMITED.value,
            "message": ERROR_CODE_DESCRIPTION[ErrorCode.RATE_LIMITED],
            "details": "请求频率超出限制, 请稍后重试",
        }
    }


# ------------------------------------------------------------------ #
#  全局单例
# ------------------------------------------------------------------ #

_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """获取全局限流器实例。"""
    return _rate_limiter  # type: ignore[return-value]


def init_rate_limiter(
    default_requests: int = RATE_LIMIT_DEFAULT_REQUESTS,
    window_seconds: int = RATE_LIMIT_DEFAULT_WINDOW,
) -> RateLimiter:
    """初始化全局限流器。

    Args:
        default_requests: 默认每分钟请求数
        window_seconds: 限流窗口(秒)

    Returns:
        初始化完成的限流器实例
    """
    global _rate_limiter
    _rate_limiter = RateLimiter(
        default_requests=default_requests,
        window_seconds=window_seconds,
    )
    return _rate_limiter
