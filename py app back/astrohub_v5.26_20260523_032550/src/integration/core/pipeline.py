"""
M10 Integration v1.0 - 数据处理管道

可链式组合的数据处理管道，用于跨模块数据流转与转换。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("integration")


# 管道阶段函数类型
StageFn = Callable[[dict], dict]
AsyncStageFn = Callable[[dict], Coroutine[Any, Any, dict]]


# ================================================================== #
#  管道阶段
# ================================================================== #

class PipelineStage:
    """管道中的单个处理阶段。"""

    __slots__ = ("name", "fn", "timeout")

    def __init__(
        self,
        name: str,
        fn: StageFn | AsyncStageFn,
        timeout: float | None = None,
    ) -> None:
        self.name = name
        self.fn = fn
        self.timeout = timeout

    async def execute(self, data: dict) -> dict:
        """执行阶段处理。

        Args:
            data: 输入数据

        Returns:
            处理后的数据

        Raises:
            ValueError: 阶段处理失败
        """
        try:
            if asyncio.iscoroutinefunction(self.fn):
                if self.timeout:
                    result = await asyncio.wait_for(self.fn(data), timeout=self.timeout)
                else:
                    result = await self.fn(data)
            else:
                result = self.fn(data)

            if result is None:
                raise ValueError(f"阶段 {self.name} 返回 None")
            return result
        except Exception as exc:
            logger.error("[M10 INTEGRATION] 管道阶段失败: %s, error=%s", self.name, exc)
            raise


# ================================================================== #
#  数据管道
# ================================================================== #

class Pipeline:
    """可链式组合的数据处理管道。

    数据按顺序流经各阶段，每阶段可修改数据并传递给下一阶段。
    适用于 E2E 流程中 (P1) 的数据流转，如: 设备发现→认证→数据转换。
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._stages: list[PipelineStage] = []
        self._started = False

    def add_stage(
        self,
        name: str,
        fn: StageFn | AsyncStageFn,
        timeout: float | None = None,
    ) -> Pipeline:
        """添加处理阶段。

        Args:
            name: 阶段名称
            fn: 处理函数 (同步或异步)
            timeout: 阶段超时 (秒)

        Returns:
            self (支持链式调用)
        """
        self._stages.append(PipelineStage(name=name, fn=fn, timeout=timeout))
        return self

    async def run(self, initial_data: dict | None = None) -> dict:
        """执行管道。从第一阶段到最后一阶段，依次流转。

        Args:
            initial_data: 初始输入数据

        Returns:
            管道最终输出

        Raises:
            RuntimeError: 管道执行失败
        """
        data = initial_data or {}
        data["_pipeline"] = self.name
        data["_started_at"] = time.time()

        logger.debug("[M10 INTEGRATION] 管道开始: %s, 阶段数=%d", self.name, len(self._stages))

        for i, stage in enumerate(self._stages):
            try:
                data["_current_stage"] = stage.name
                data = await stage.execute(data)
                logger.debug("[M10 INTEGRATION] 管道阶段 %d/%d 完成: %s", i + 1, len(self._stages), stage.name)
            except Exception as exc:
                data["_failed_stage"] = stage.name
                data["_error"] = str(exc)
                data["_completed_at"] = time.time()
                logger.error("[M10 INTEGRATION] 管道 %s 在阶段 '%s' 失败: %s", self.name, stage.name, exc)
                raise RuntimeError(
                    f"管道 {self.name} 在阶段 '{stage.name}' 失败: {exc}"
                ) from exc

        data["_completed_at"] = time.time()
        data.pop("_current_stage", None)
        duration = data["_completed_at"] - data["_started_at"]
        logger.debug("[M10 INTEGRATION] 管道完成: %s, 耗时=%.2fs", self.name, duration)
        return data

    def stage_count(self) -> int:
        """返回阶段数。"""
        return len(self._stages)

    def stage_names(self) -> list[str]:
        """返回所有阶段名称。"""
        return [s.name for s in self._stages]

    def reset(self) -> None:
        """清空所有阶段。"""
        self._stages.clear()


# ================================================================== #
#  管道编排器 (多个管道)
# ================================================================== #

class PipelineOrchestrator:
    """管理多个管道，支持按名调用。"""

    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}

    def register(self, pipeline: Pipeline) -> None:
        """注册管道。"""
        self._pipelines[pipeline.name] = pipeline

    async def run(self, name: str, data: dict | None = None) -> dict:
        """运行指定管道。"""
        pipe = self._pipelines.get(name)
        if not pipe:
            raise KeyError(f"管道 '{name}' 未注册")
        return await pipe.run(data)

    def list_pipelines(self) -> list[str]:
        """列出所有已注册管道。"""
        return list(self._pipelines.keys())


# 全局编排器
_orchestrator: PipelineOrchestrator | None = None


def get_orchestrator() -> PipelineOrchestrator:
    """获取全局管道编排器。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = PipelineOrchestrator()
    return _orchestrator
