"""
M7 REST API v1.0 - API 网关 / 路由聚合

实现:
- 路由器注册与管理
- API 版本控制
- 健康检查端点
- 服务摘要端点
- 聚合路由挂载点

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI

from rest_api.constants import API_V1_PREFIX
from rest_api.api.router import (
    device_router,
    stream_router,
    calibration_router,
    data_router,
    auth_router,
)


# ------------------------------------------------------------------ #
#  API 网关
# ------------------------------------------------------------------ #

class APIGateway:
    """API 网关: 聚合所有子路由, 统一挂载到 FastAPI 应用。

    路由层次:
        /api/v1/devices/*          - 设备管理 (P1)
        /api/v1/streams/*          - 流控制 (P2)
        /api/v1/calibration/*      - 校准 (P3)
        /api/v1/observations       - 数据查询 (P4)
        /api/v1/stats              - 统计聚合 (P4)
        /api/v1/auth/*             - 认证 (P5)
    """

    def __init__(self):
        self._routers: list[tuple[APIRouter, str]] = []
        self._tags: list[str] = []

    def register(self, router: APIRouter, tag: str = "") -> None:
        """注册路由器到网关。

        Args:
            router: FastAPI APIRouter 实例
            tag: 路由分组标签 (用于 OpenAPI 文档)
        """
        self._routers.append((router, tag))
        if tag:
            self._tags.append(tag)

    def mount_to(self, app: FastAPI, prefix: str = API_V1_PREFIX) -> None:
        """将所有注册的路由器挂载到 FastAPI 应用。

        Args:
            app: FastAPI 应用实例
            prefix: 路由前缀, 默认 /api/v1
        """
        for router, _tag in self._routers:
            app.include_router(router, prefix=prefix)

    def get_registered_count(self) -> int:
        """获取已注册的路由器数量。"""
        return len(self._routers)

    def get_tags(self) -> list[str]:
        """获取所有路由分组的 OpenAPI 标签。"""
        return self._tags

    def build_summary(self) -> dict:
        """构建 API 摘要信息。

        Returns:
            包含路由数量、分组、版本等信息的 dict
        """
        all_routes = []
        for router, tag in self._routers:
            for route in router.routes:
                all_routes.append({
                    "path": str(route.path),
                    "methods": list(route.methods),
                    "tag": tag,
                })

        return {
            "total_routes": len(all_routes),
            "total_groups": len(self._tags),
            "groups": self._tags,
            "routes": all_routes,
        }


# ------------------------------------------------------------------ #
#  健康检查端点
# ------------------------------------------------------------------ #

def create_health_router() -> APIRouter:
    """创建健康检查路由器。

    返回:
        GET /health - 服务健康检查
        GET /api/v1/summary - API 摘要
    """
    router = APIRouter()

    gateway = APIGateway()
    gateway.register(device_router, "设备管理")
    gateway.register(stream_router, "流控制")
    gateway.register(calibration_router, "校准管理")
    gateway.register(data_router, "数据查询")
    gateway.register(auth_router, "认证")

    @router.get("/health", summary="服务健康检查", tags=["System"])
    async def health_check() -> dict:
        """服务健康状态检查。

        Returns:
            服务状态信息 {"status": "healthy", "version": "1.0"}
        """
        return {
            "status": "healthy",
            "version": "1.0",
            "service": "M7 REST API",
        }

    @router.get("/api/v1/summary", summary="API 摘要", tags=["System"])
    async def api_summary() -> dict:
        """返回 API 路由摘要。

        Returns:
            包含路由总数、分组、所有端点路径等信息
        """
        return gateway.build_summary()

    return router


# ------------------------------------------------------------------ #
#  注册全局网关
# ------------------------------------------------------------------ #

_gateway: APIGateway | None = None


def get_gateway() -> APIGateway:
    """获取全局 API 网关实例。"""
    global _gateway
    if _gateway is None:
        _gateway = APIGateway()
        _gateway.register(device_router, "设备管理")
        _gateway.register(stream_router, "流控制")
        _gateway.register(calibration_router, "校准")
        _gateway.register(data_router, "数据查询")
        _gateway.register(auth_router, "认证")
    return _gateway
