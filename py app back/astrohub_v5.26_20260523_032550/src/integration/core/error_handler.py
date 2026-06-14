"""
M10 Integration v1.0 - 全局错误处理与重试

跨模块错误捕获、指数退避重试、错误聚合报告。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Coroutine, Optional, TypeVar

from integration.constants import (
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_BASE,
)

T = TypeVar("T")
logger = logging.getLogger("integration")


# ------------------------------------------------------------------ #
#  集成异常层次
# ------------------------------------------------------------------ #

class IntegrationError(Exception):
    """集成基础异常。"""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code.value,
            "error_description": ERROR_CODE_DESCRIPTION.get(self.error_code, str(self)),
            "message": str(self),
            "details": self.details,
            "timestamp": self.timestamp,
        }


class ModuleCommunicationError(IntegrationError):
    """模块间通信异常。"""

    def __init__(self, module: str, message: str, details: dict | None = None) -> None:
        super().__init__(
            message,
            error_code=ErrorCode.MODULE_COMMUNICATION_FAILED,
            details={"module": module, **(details or {})},
        )


class E2EFlowError(IntegrationError):
    """端到端流程异常。"""

    def __init__(self, stage: str, message: str, details: dict | None = None) -> None:
        super().__init__(
            message,
            error_code=ErrorCode.E2E_STAGE_FAILED,
            details={"stage": stage, **(details or {})},
        )


class RecoveryError(IntegrationError):
    """恢复操作异常。"""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(
            message,
            error_code=ErrorCode.RECOVERY_FAILED,
            details=details or {},
        )


# ------------------------------------------------------------------ #
#  重试装饰器
# ------------------------------------------------------------------ #

def with_retry(
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    backoff_base: float = RETRY_BACKOFF_BASE,
    retriable_exceptions: tuple[type[Exception], ...] = (IntegrationError,),
) -> Callable:
    """异步重试装饰器，指数退避。

    Args:
        max_attempts: 最大重试次数
        backoff_base: 退避基数 (秒)
        retriable_exceptions: 可重试的异常类型
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retriable_exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        delay = backoff_base ** (attempt + 1)
                        logger.warning(
                            "[M10 INTEGRATION] %s 第 %d 次失败, %0.1fs 后重试: %s",
                            func.__name__, attempt + 1, delay, exc,
                        )
                        await asyncio.sleep(delay)
            raise RecoveryError(
                f"{func.__name__} 重试 {max_attempts} 次后仍失败: {last_exc}",
                details={"original_error": str(last_exc)},
            )
        return wrapper
    return decorator


def with_retry_sync(
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    backoff_base: float = RETRY_BACKOFF_BASE,
    retriable_exceptions: tuple[type[Exception], ...] = (IntegrationError,),
) -> Callable:
    """同步重试装饰器，指数退避。"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            import time as _time
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except retriable_exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        delay = backoff_base ** (attempt + 1)
                        logger.warning(
                            "[M10 INTEGRATION] %s 第 %d 次失败, %0.1fs 后重试: %s",
                            func.__name__, attempt + 1, delay, exc,
                        )
                        _time.sleep(delay)
            raise RecoveryError(
                f"{func.__name__} 重试 {max_attempts} 次后仍失败: {last_exc}",
                details={"original_error": str(last_exc)},
            )
        return wrapper
    return decorator


# ------------------------------------------------------------------ #
#  错误聚合器
# ------------------------------------------------------------------ #

class ErrorAggregator:
    """聚合来自各模块的错误，用于生成集成报告 (P4)。"""

    def __init__(self) -> None:
        self._errors: list[dict] = []
        self._lock = asyncio.Lock()

    async def record(self, error: IntegrationError) -> None:
        """记录错误。"""
        async with self._lock:
            self._errors.append(error.to_dict())

    async def get_report(self) -> dict:
        """生成错误聚合报告。"""
        async with self._lock:
            by_code: dict[str, int] = {}
            for err in self._errors:
                code = err["error_code"]
                by_code[code] = by_code.get(code, 0) + 1
            return {
                "total_errors": len(self._errors),
                "by_error_code": by_code,
                "errors": self._errors[-50:],  # 最近 50 条
            }

    async def clear(self) -> None:
        """清空所有记录。"""
        async with self._lock:
            self._errors.clear()


# 全局实例
_error_aggregator: ErrorAggregator | None = None


def get_error_aggregator() -> ErrorAggregator:
    """获取全局错误聚合器。"""
    global _error_aggregator
    if _error_aggregator is None:
        _error_aggregator = ErrorAggregator()
    return _error_aggregator
