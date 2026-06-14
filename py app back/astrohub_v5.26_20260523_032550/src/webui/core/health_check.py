"""
M6 Web UI Service v1.0 - 健康检查

检查 M6 自身及各后端服务（M2-M5）的可达性与健康状态。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import httpx

from webui.constants import HealthStatus


@dataclass
class ServiceHealth:
    """单个服务的健康状态。"""

    name: str
    url: str
    status: str  # healthy/degraded/unhealthy
    latency_ms: float
    message: str = ""
    last_check: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class HealthChecker:
    """健康检查器。

    检查 M6 自身状态以及 M2-M5 各后端服务的可达性。
    """

    def __init__(self, service_urls: Optional[Dict[str, str]] = None):
        """初始化健康检查器。

        Args:
            service_urls: 各后端服务的健康检查 URL
        """
        self._service_urls = service_urls or {
            "database": "http://localhost:8001/api/v1/devices?page=1&page_size=1",
            "calibration": "http://localhost:8000/api/v1/calibration/status",
            "m3_stream": "http://localhost:8000/api/v1/streams",
            "device": "http://localhost:8000/api/v1/devices",
        }
        self._last_results: Dict[str, ServiceHealth] = {}

    async def check_all(self) -> Dict[str, Any]:
        """检查所有服务的健康状态。

        Returns:
            各服务健康状态汇总，包含总体状态
        """
        import asyncio
        from datetime import datetime

        results = {}
        tasks = [
            self._check_service(name, url)
            for name, url in self._service_urls.items()
        ]
        service_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in service_results:
            if isinstance(result, ServiceHealth):
                results[result.name] = result.to_dict()
                self._last_results[result.name] = result

        # 总体健康状态
        overall = self._calculate_overall_health(results)

        return {
            "status": overall.value,
            "timestamp": datetime.now().isoformat(),
            "services": results,
        }

    async def check_self(self) -> Dict[str, Any]:
        """检查 M6 自身健康状态。

        Returns:
            M6 自身健康信息
        """
        from datetime import datetime

        return {
            "status": HealthStatus.HEALTHY.value,
            "service": "webui",
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "uptime": "running",
        }

    async def _check_service(self, name: str, url: str) -> ServiceHealth:
        """检查单个服务的健康状态。

        Args:
            name: 服务名称
            url: 健康检查 URL

        Returns:
            服务健康状态
        """
        from datetime import datetime

        client = httpx.AsyncClient(timeout=5.0)
        try:
            start = time.monotonic()
            response = await client.get(url)
            latency = (time.monotonic() - start) * 1000

            if response.status_code < 300:
                return ServiceHealth(
                    name=name,
                    url=url,
                    status=HealthStatus.HEALTHY.value,
                    latency_ms=round(latency, 2),
                    message="OK",
                    last_check=datetime.now().isoformat(),
                )
            else:
                return ServiceHealth(
                    name=name,
                    url=url,
                    status=HealthStatus.DEGRADED.value,
                    latency_ms=round(latency, 2),
                    message=f"HTTP {response.status_code}",
                    last_check=datetime.now().isoformat(),
                )
        except httpx.ConnectError:
            return ServiceHealth(
                name=name,
                url=url,
                status=HealthStatus.UNHEALTHY.value,
                latency_ms=0,
                message="无法连接",
                last_check=datetime.now().isoformat(),
            )
        except Exception as e:
            return ServiceHealth(
                name=name,
                url=url,
                status=HealthStatus.UNHEALTHY.value,
                latency_ms=0,
                message=str(e),
                last_check=datetime.now().isoformat(),
            )
        finally:
            await client.aclose()

    def _calculate_overall_health(self, results: Dict[str, dict]) -> HealthStatus:
        """计算总体健康状态。

        Args:
            results: 各服务健康状态

        Returns:
            总体健康状态
        """
        if not results:
            return HealthStatus.DEGRADED

        statuses = [r.get("status") for r in results.values()]

        if all(s == HealthStatus.HEALTHY.value for s in statuses):
            return HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY.value for s in statuses):
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.DEGRADED
