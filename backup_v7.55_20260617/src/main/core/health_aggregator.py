"""
M12 Unified Integration v1.0 - 健康状态聚合器

聚合 M1-M11 模块的健康状态，计算系统整体健康度。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.main.constants import HealthStatus, MODULE_ORDER

logger = logging.getLogger("m12.health_aggregator")


class HealthAggregator:
    """M1-M11 模块健康状态聚合器。
    
    收集各模块健康状态，计算系统整体健康度。
    整体状态取所有模块中最差状态。
    """
    
    _STATUS_SEVERITY = {
        HealthStatus.UNHEALTHY: 3,
        HealthStatus.DEGRADED: 2,
        HealthStatus.UNKNOWN: 1,
        HealthStatus.HEALTHY: 0,
    }
    
    def __init__(self) -> None:
        self._module_status: dict[str, dict[str, Any]] = {}
    
    def aggregate(self, module_status: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        """聚合所有模块的健康状态。
        
        Args:
            module_status: 可选的模块状态字典。如果提供，会更新内部状态。
                          格式: {module_name: {status: str, details: Any}}
        
        Returns:
            聚合结果:
            - overall: 整体健康状态 (HealthStatus)
            - modules: 各模块详细状态
            - timestamp: 聚合时间
            - summary: 统计摘要
        """
        if module_status is not None:
            self._module_status.update(module_status)
        
        overall = self._calculate_overall()
        summary = self._generate_summary()
        
        return {
            "overall": overall.value,
            "modules": dict(self._module_status),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
        }
    
    def get_overall_status(self) -> HealthStatus:
        """返回当前整体健康状态。"""
        return self._calculate_overall()
    
    def update_module_status(
        self, module_name: str, status: HealthStatus, details: str = ""
    ) -> None:
        """更新单个模块的健康状态。
        
        Args:
            module_name: 模块名称
            status: 健康状态枚举
            details: 详细信息
        """
        self._module_status[module_name] = {
            "status": status.value,
            "details": details,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug("模块 %s 状态更新: %s", module_name, status.value)
    
    def get_module_status(self, module_name: str) -> dict[str, Any]:
        """获取指定模块的健康状态。
        
        Args:
            module_name: 模块名称
        
        Returns:
            模块状态字典，未找到返回默认 UNKNOWN 状态
        """
        return self._module_status.get(
            module_name,
            {
                "status": HealthStatus.UNKNOWN.value,
                "details": "未报告状态",
                "updated_at": None,
            },
        )
    
    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """返回所有模块的健康状态。
        
        确保 MODULE_ORDER 中的所有模块都有状态条目。
        """
        result = {}
        for module_name in MODULE_ORDER:
            result[module_name] = self.get_module_status(module_name)
        return result
    
    # ---- 内部辅助方法 ----
    
    def _calculate_overall(self) -> HealthStatus:
        """计算整体健康状态（取最差状态）。"""
        if not self._module_status:
            return HealthStatus.UNKNOWN
        
        worst = HealthStatus.HEALTHY
        worst_severity = self._STATUS_SEVERITY[HealthStatus.HEALTHY]
        
        for module_name in MODULE_ORDER:
            module_data = self._module_status.get(module_name, {})
            status_str = module_data.get("status", HealthStatus.UNKNOWN.value)
            try:
                status = HealthStatus(status_str)
            except ValueError:
                status = HealthStatus.UNKNOWN
            
            severity = self._STATUS_SEVERITY.get(status, 1)
            if severity > worst_severity:
                worst = status
                worst_severity = severity
        
        return worst
    
    def _generate_summary(self) -> dict[str, int]:
        """生成统计摘要。"""
        counts = {s.value: 0 for s in HealthStatus}
        
        for module_data in self._module_status.values():
            status = module_data.get("status", HealthStatus.UNKNOWN.value)
            if status in counts:
                counts[status] += 1
        
        return {
            "total": len(self._module_status),
            **counts,
        }