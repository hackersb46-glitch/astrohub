"""
M6 Web UI Service v1.0 - 仪表盘数据聚合

聚合设备状态、校准进度、流状态等仪表盘数据，供前端页面调用。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from webui.constants import (
    DATABASE_URL,
    DASHBOARD_REFRESH_INTERVAL,
)


class DashboardAggregator:
    """仪表盘数据聚合器。

    从 M2/M3/M4/M5 各后端服务聚合数据，统一返回给前端仪表盘。
    """

    def __init__(self, database_base_url: Optional[str] = None):
        """初始化仪表盘聚合器。

        Args:
            database_base_url: Database Service 地址
        """
        self._database_base_url = database_base_url or DATABASE_URL
        self._client: Optional[httpx.AsyncClient] = None
        self._last_refresh: Optional[datetime] = None
        self._cached_data: Dict[str, Any] = {}

    async def init(self) -> None:
        """初始化 HTTP 客户端。"""
        self._client = httpx.AsyncClient(base_url=self._database_base_url, timeout=10.0)

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_overview(self) -> Dict[str, Any]:
        """获取仪表盘总览数据。

        Returns:
            包含设备总数、在线数、离线数、校准状态等汇总数据
        """
        overview: Dict[str, Any] = {
            "device_summary": await self._get_device_summary(),
            "stream_status": await self._get_stream_status(),
            "calibration_progress": await self._get_calibration_progress(),
            "last_refresh": datetime.now().isoformat(),
        }
        self._last_refresh = datetime.now()
        self._cached_data = overview
        return overview

    async def refresh(self) -> None:
        """刷新仪表盘缓存数据。"""
        await self.get_overview()

    async def _get_device_summary(self) -> Dict[str, Any]:
        """获取设备汇总数据（从 Database Service）。

        Returns:
            设备总数、在线数、离线数、分组数
        """
        try:
            if not self._client:
                return {"total": 0, "online": 0, "offline": 0, "groups": 0}

            response = await self._client.get("/api/v1/devices", params={"page": 1, "page_size": 1})
            if response.status_code == 200:
                data = response.json()
                return {
                    "total": data.get("total", 0),
                    "online": 0,  # 需 M5 支持状态统计
                    "offline": 0,
                    "groups": 0,  # 需 M5 支持分组统计
                }
        except (httpx.RequestError, Exception):
            pass

        return {"total": 0, "online": 0, "offline": 0, "groups": 0}

    async def _get_stream_status(self) -> Dict[str, Any]:
        """获取视频流状态（从 M3 Stream Service）。

        Returns:
            活跃流数、录制中流数等
        """
        # TODO: 对接 M3 Stream Service API
        return {"active_streams": 0, "recording_streams": 0}

    async def _get_calibration_progress(self) -> Dict[str, Any]:
        """获取校准进度（从 M4 Calibration Service）。

        Returns:
            当前校准状态、已完成步骤等
        """
        try:
            if not self._client:
                return {"status": "idle", "current_step": None, "completed_steps": []}

            response = await self._client.get("/api/v1/calibration/status")
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": data.get("state", "idle"),
                    "current_step": data.get("current_step"),
                    "completed_steps": data.get("completed_steps", []),
                }
        except (httpx.RequestError, Exception):
            pass

        return {"status": "idle", "current_step": None, "completed_steps": []}

    @property
    def last_refresh(self) -> Optional[datetime]:
        """最后刷新时间。"""
        return self._last_refresh
