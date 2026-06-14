"""
M10 Integration v1.0 - 健康状态聚合

汇总各子模块的健康状态，生成系统级健康报告。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
from typing import Any

from integration.constants import ErrorCode, IntegrationStatus, ModuleStatus


class HealthRecord:
    """单个模块的健康记录。"""

    __slots__ = ("name", "status", "latency_ms", "last_check", "details")

    def __init__(
        self,
        name: str,
        status: ModuleStatus = ModuleStatus.UNKNOWN,
        latency_ms: float = 0.0,
        details: dict | None = None,
    ) -> None:
        self.name = name
        self.status = status
        self.latency_ms = latency_ms
        self.last_check = time.time()
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 1),
            "last_check": self.last_check,
            "details": self.details,
        }


class HealthAggregator:
    """全模块健康状态聚合器。

    整合 M1-M9 各模块健康状态，计算系统级健康度，
    支持 P0.1/P0.3 服务启动验证场景。
    """

    def __init__(self) -> None:
        self._records: dict[str, HealthRecord] = {}
        self._callbacks: list = []

    def register_module(self, name: str) -> None:
        """注册被监控的模块。"""
        if name not in self._records:
            self._records[name] = HealthRecord(name=name)

    def update(self, name: str, status: ModuleStatus, latency_ms: float = 0.0, details: dict | None = None) -> None:
        """更新模块健康状态。

        Args:
            name: 模块名 (如 m2_device_manager, m3_stream_service)
            status: 健康状态
            latency_ms: 健康检查响应延迟 (ms)
            details: 额外详情
        """
        if name not in self._records:
            self.register_module(name)
        record = self._records[name]
        record.status = status
        record.latency_ms = latency_ms
        record.last_check = time.time()
        record.details = details or {}

    def get_record(self, name: str) -> HealthRecord | None:
        """获取单个模块健康记录。"""
        return self._records.get(name)

    def get_all(self) -> dict[str, dict]:
        """获取所有模块健康状态。"""
        return {name: record.to_dict() for name, record in self._records.items()}

    def overall_status(self) -> IntegrationStatus:
        """根据各模块状态计算系统级状态。

        Returns:
            系统级集成状态
        """
        if not self._records:
            return IntegrationStatus.INITIALIZING

        statuses = [r.status for r in self._records.values()]

        all_up = all(s in (ModuleStatus.UP, ModuleStatus.UNKNOWN) for s in statuses)
        if all_up:
            return IntegrationStatus.READY

        any_down = any(s == ModuleStatus.DOWN for s in statuses)
        if any_down:
            # 有模块完全不可用
            return IntegrationStatus.ERROR

        # 部分降级
        return IntegrationStatus.DEGRADED

    def summary(self) -> dict:
        """生成健康摘要报告 (用于 P4 集成报告)。"""
        status = self.overall_status()
        counts = {"up": 0, "down": 0, "degraded": 0, "unknown": 0}
        for r in self._records.values():
            counts[r.status.value] = counts.get(r.status.value, 0) + 1

        return {
            "overall": status.value,
            "total_modules": len(self._records),
            "counts": counts,
            "modules": self.get_all(),
            "timestamp": time.time(),
        }
