"""
M11 Deployment v1.0 - 部署后健康监控

服务健康检查、依赖端点检测、CPU/内存/磁盘监控 (P4.1-P4.2)。

P2.2: HTTP 健康检查端点, 检查服务依赖
P4.1: 系统监控 (CPU/内存/磁盘/网络)
P4.2: 服务监控 (API 响应时间/流状态/设备连接数)

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
from typing import Any

from deployment.constants import (
    ErrorCode,
    HEALTH_CHECK_INTERVAL,
    HEALTH_CHECK_RETRIES,
    HEALTH_CHECK_TIMEOUT,
    HEALTH_ENDPOINT,
    ALERT_THRESHOLD_CPU,
    ALERT_THRESHOLD_MEMORY,
    ALERT_THRESHOLD_DISK,
)


class HealthStatus:
    """健康状态结果。"""

    def __init__(
        self,
        service: str,
        healthy: bool,
        latency: float,
        details: dict[str, Any] | None = None,
    ):
        self.service = service
        self.healthy = healthy
        self.latency_ms = latency
        self.details = details or {}
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "healthy": self.healthy,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp,
            "details": self.details,
        }


class HealthMonitor:
    """健康监控器。

    定期执行健康检查，跟踪服务健康度趋势。
    """

    def __init__(self):
        """Initialize."""
        self._services: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []
        self._consecutive_failures: dict[str, int] = {}

    def register_service(self, name: str, url: str) -> None:
        """注册服务健康检查端点。

        Args:
            name: 服务名
            url: 健康检查 URL
        """
        self._services[name] = {
            "url": url,
            "status": "unknown",
            "last_check": None,
        }
        self._consecutive_failures[name] = 0

    def check_service(self, name: str) -> HealthStatus:
        """检查单个服务健康状态。

        Returns:
            HealthStatus 对象
        """
        if name not in self._services:
            return HealthStatus(
                service=name,
                healthy=False,
                latency_ms=0,
                details={"error": "服务未注册"},
            )

        svc = self._services[name]
        url = svc["url"]
        start = time.time()

        try:
            import urllib.request
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=HEALTH_CHECK_TIMEOUT) as resp:
                latency_ms = (time.time() - start) * 1000
                healthy = resp.status == 200

                if healthy:
                    self._consecutive_failures[name] = 0
                else:
                    self._consecutive_failures[name] = self._consecutive_failures.get(name, 0) + 1

                result = HealthStatus(
                    service=name,
                    healthy=healthy,
                    latency_ms=latency_ms,
                    details={"status_code": resp.status},
                )
                svc["status"] = "healthy" if healthy else "unhealthy"
                svc["last_check"] = time.time()

                self._history.append(result.to_dict())
                return result

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            self._consecutive_failures[name] = self._consecutive_failures.get(name, 0) + 1

            result = HealthStatus(
                service=name,
                healthy=False,
                latency_ms=latency_ms,
                details={"error": str(e)},
            )
            svc["status"] = "unhealthy"
            svc["last_check"] = time.time()

            self._history.append(result.to_dict())
            return result

    def check_all(self) -> list[HealthStatus]:
        """检查所有已注册服务。

        Returns:
            健康状态列表
        """
        return [self.check_service(name) for name in self._services]

    def is_critical(self, name: str) -> bool:
        """判断服务是否进入危险状态 (连续失败次数 > 阈值)。"""
        return self._consecutive_failures.get(name, 0) >= HEALTH_CHECK_RETRIES

    def get_summary(self) -> dict[str, Any]:
        """获取健康摘要。

        Returns:
            {total, healthy, unhealthy, services: [...]}
        """
        healthy = sum(
            1 for s in self._services.values() if s.get("status") == "healthy"
        )
        return {
            "total": len(self._services),
            "healthy": healthy,
            "unhealthy": len(self._services) - healthy,
            "services": [
                {"name": n, **s} for n, s in self._services.items()
            ],
        }

    @property
    def history(self) -> list[dict[str, Any]]:
        """检查历史 (最近 100 条)。"""
        return self._history[-100:]


# ------------------------------------------------------------------ #
#  系统监控 (P4.1)
# ------------------------------------------------------------------ #

class SystemMonitor:
    """系统资源监控。

    P4.1: CPU/内存/磁盘/网络 监控数据。
    """

    def collect_metrics(self) -> dict[str, Any]:
        """采集当前系统指标。

        Returns:
            {cpu_percent, memory_percent, disk_percent, alerts: []}
        """
        import psutil

        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent

        alerts = []
        if cpu > ALERT_THRESHOLD_CPU:
            alerts.append({"type": "cpu", "value": cpu, "threshold": ALERT_THRESHOLD_CPU})
        if memory > ALERT_THRESHOLD_MEMORY:
            alerts.append({"type": "memory", "value": memory, "threshold": ALERT_THRESHOLD_MEMORY})
        if disk > ALERT_THRESHOLD_DISK:
            alerts.append({"type": "disk", "value": disk, "threshold": ALERT_THRESHOLD_DISK})

        return {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "disk_percent": disk,
            "alerts": alerts,
            "timestamp": time.time(),
        }


# ------------------------------------------------------------------ #
#  单例
# ------------------------------------------------------------------ #

_default_monitor: HealthMonitor | None = None


def get_monitor() -> HealthMonitor:
    """获取默认 HealthMonitor。"""
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = HealthMonitor()
    return _default_monitor
