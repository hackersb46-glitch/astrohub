"""任务编排器 - 负责任务调度、事件总线和错误处理."""

import asyncio
import uuid
import time
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskScheduler:
    def __init__(self) -> None:
        self._tasks: Dict[str, dict[str, Any]] = {}
        self._task_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._errors: List[dict[str, Any]] = []
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._priority_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

    async def start(self) -> None:
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        for task_info in self._tasks.values():
            task = task_info.get("handle")
            if task and not task.done():
                task.cancel()

    def submit_task(
        self,
        name: str,
        coro: Coroutine,
        priority: int = 0,
    ) -> str:
        task_id = str(uuid.uuid4())
        self._tasks[task_id] = {
            "name": name,
            "status": TaskStatus.PENDING,
            "priority": priority,
            "coro": coro,
            "created_at": time.monotonic(),
            "handle": None,
        }
        self._priority_queue.put_nowait((-priority, task_id))
        return task_id

    def cancel_task(self, task_id: str) -> bool:
        if task_id not in self._tasks:
            return False
        task_info = self._tasks[task_id]
        if task_info["status"] in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
            return False
        task_info["status"] = TaskStatus.CANCELLED
        handle = task_info.get("handle")
        if handle and not handle.done():
            handle.cancel()
        return True

    def get_task_status(self, task_id: str) -> Optional[dict[str, Any]]:
        if task_id not in self._tasks:
            return None
        task_info = self._tasks[task_id]
        return {
            "task_id": task_id,
            "name": task_info["name"],
            "status": task_info["status"].value,
            "priority": task_info["priority"],
        }

    async def publish_event(self, event_type: str, data: Any = None) -> None:
        handlers = self._event_handlers.get(event_type, [])
        for callback in handlers:
            try:
                result = callback(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                await self.record_error("event_bus", e, ErrorSeverity.MEDIUM)

    def subscribe_event(
        self, event_type: str, callback: Callable
    ) -> None:
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(callback)

    async def record_error(
        self, module: str, error: Exception, severity: ErrorSeverity = ErrorSeverity.MEDIUM
    ) -> None:
        error_record = {
            "module": module,
            "error": str(error),
            "severity": severity.value,
            "timestamp": time.monotonic(),
        }
        self._errors.append(error_record)

    def get_error_summary(self) -> dict[str, Any]:
        summary: dict[str, int] = {}
        for severity in ErrorSeverity:
            summary[severity.value] = 0
        for err in self._errors:
            summary[err["severity"]] += 1
        return {
            "total": len(self._errors),
            "by_severity": summary,
            "recent": self._errors[-10:] if self._errors else [],
        }

    async def _scheduler_loop(self) -> None:
        while self._running:
            try:
                _, task_id = await asyncio.wait_for(
                    self._priority_queue.get(), timeout=0.1
                )
                if task_id not in self._tasks:
                    continue
                task_info = self._tasks[task_id]
                if task_info["status"] != TaskStatus.PENDING:
                    continue
                task_info["status"] = TaskStatus.RUNNING
                handle = asyncio.create_task(self._run_task(task_id))
                task_info["handle"] = handle
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue

    async def _run_task(self, task_id: str) -> None:
        task_info = self._tasks[task_id]
        try:
            await task_info["coro"]
            task_info["status"] = TaskStatus.COMPLETED
        except asyncio.CancelledError:
            task_info["status"] = TaskStatus.CANCELLED
            raise
        except Exception as e:
            task_info["status"] = TaskStatus.FAILED
            await self.record_error(task_info["name"], e, ErrorSeverity.HIGH)
