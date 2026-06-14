"""
M10 Integration v1.0 - 任务调度器

任务队列、优先级调度、定时任务。用于编排跨模块集成任务执行。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from integration.constants import (
    ErrorCode,
    MAX_RETRY_ATTEMPTS,
    RETRY_BACKOFF_BASE,
    TASK_PRIORITY_CRITICAL,
    TASK_PRIORITY_HIGH,
    TASK_PRIORITY_LOW,
    TASK_PRIORITY_NORMAL,
)

logger = logging.getLogger("integration")


# ================================================================== #
#  任务状态
# ================================================================== #

class TaskStatus(Enum):
    """任务执行状态。"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ================================================================== #
#  任务定义
# ================================================================== #

@dataclass
class Task:
    """集成任务。"""
    task_id: str
    name: str
    fn: Callable[..., Coroutine[Any, Any, dict]]
    priority: int = TASK_PRIORITY_NORMAL
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    timeout: float | None = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "priority": self.priority,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


# ================================================================== #
#  任务调度器
# ================================================================== #

class TaskScheduler:
    """优先级任务队列调度器。

    维护一个按优先级排序的任务队列，支持:
    - 任务提交与优先级排序
    - 顺序/并发执行
    - 超时控制
    - 定时任务 (周期性调度)
    """

    def __init__(self, max_concurrent: int = 5) -> None:
        self._queue: list[Task] = []
        self._tasks: dict[str, Task] = {}
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._running = False
        self._worker: asyncio.Task | None = None
        # 定时任务
        self._scheduled_tasks: dict[str, dict] = {}

    async def submit(
        self,
        task_id: str,
        name: str,
        fn: Callable[..., Coroutine[Any, Any, dict]],
        priority: int = TASK_PRIORITY_NORMAL,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> Task:
        """提交任务到队列。

        Args:
            task_id: 唯一任务 ID
            name: 任务名称
            fn: 异步可调用函数
            priority: 优先级 (数字越小优先级越高)
            timeout: 超时时间 (秒)
            **kwargs: 传递给 fn 的参数
        """
        task = Task(
            task_id=task_id,
            name=name,
            fn=fn,
            priority=priority,
            kwargs=kwargs,
            timeout=timeout,
        )
        async with self._lock:
            self._tasks[task_id] = task
            self._queue.append(task)
        logger.info("[M10 INTEGRATION] 任务已提交: %s (优先级=%d)", name, priority)
        return task

    async def start(self) -> None:
        """启动调度器 worker。"""
        self._running = True
        self._worker = asyncio.create_task(self._process_queue())
        logger.info("[M10 INTEGRATION] 任务调度器已启动 (并发=%d)", self._max_concurrent)

    async def stop(self) -> None:
        """停止调度器，取消所有 pending 任务。"""
        self._running = False
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        async with self._lock:
            for task in self._queue:
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
        logger.info("[M10 INTEGRATION] 任务调度器已停止")

    async def schedule_periodic(
        self,
        task_id: str,
        name: str,
        fn: Callable[..., Coroutine[Any, Any, dict]],
        interval: float,
        **kwargs: Any,
    ) -> None:
        """注册定时任务。

        Args:
            task_id: 任务 ID
            name: 任务名称
            fn: 异步可调用函数
            interval: 执行间隔 (秒)
            **kwargs: 传递给 fn 的参数
        """
        self._scheduled_tasks[task_id] = {
            "name": name,
            "fn": fn,
            "interval": interval,
            "kwargs": kwargs,
            "handle": None,
        }
        logger.info("[M10 INTEGRATION] 定时任务已注册: %s (间隔=%ds)", name, interval)

    async def cancel_periodic(self, task_id: str) -> bool:
        """取消定时任务。"""
        entry = self._scheduled_tasks.pop(task_id, None)
        if entry and entry.get("handle"):
            entry["handle"].cancel()
            return True
        return False

    async def get_task(self, task_id: str) -> dict | None:
        """获取任务状态。"""
        task = self._tasks.get(task_id)
        return task.to_dict() if task else None

    async def list_tasks(self, status: TaskStatus | None = None) -> list[dict]:
        """列出任务。"""
        async with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [t.to_dict() for t in sorted(tasks, key=lambda x: (x.priority, x.created_at))]

    async def _process_queue(self) -> None:
        """后台任务处理循环。"""
        while self._running:
            async with self._lock:
                # 按优先级排序
                self._queue.sort(key=lambda t: (t.priority, t.created_at))
                pending = [t for t in self._queue if t.status == TaskStatus.PENDING]

            if pending:
                task = pending[0]
                async with self._lock:
                    if task in self._queue:
                        self._queue.remove(task)

                asyncio.create_task(self._execute_task(task))
                await asyncio.sleep(0.05)  # 小延迟防止空转
            else:
                await asyncio.sleep(0.1)

    async def _execute_task(self, task: Task) -> None:
        """执行单个任务。"""
        async with self._semaphore:
            task.status = TaskStatus.RUNNING
            task.started_at = time.time()
            logger.debug("[M10 INTEGRATION] 开始执行: %s", task.name)

            try:
                if task.timeout:
                    result = await asyncio.wait_for(
                        task.fn(**task.kwargs),
                        timeout=task.timeout,
                    )
                else:
                    result = await task.fn(**task.kwargs)
                task.status = TaskStatus.COMPLETED
                task.completed_at = time.time()
                logger.debug("[M10 INTEGRATION] 完成: %s", task.name)
            except asyncio.TimeoutError:
                task.status = TaskStatus.FAILED
                task.error = f"超时 ({task.timeout}s)"
                task.completed_at = time.time()
                logger.error("[M10 INTEGRATION] 超时: %s", task.name)
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                task.completed_at = time.time()
                logger.error("[M10 INTEGRATION] 失败: %s, error=%s", task.name, exc)


# 全局实例
_scheduler: TaskScheduler | None = None


def get_scheduler() -> TaskScheduler:
    """获取全局任务调度器。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
