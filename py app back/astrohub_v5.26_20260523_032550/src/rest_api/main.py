"""
M7 REST API v1.0 - 应用入口点

FastAPI API 网关: 设备管理、流控制、校准、数据查询。

初始化所有核心模块 (认证/限流/中间件/路由), 启动 FastAPI 服务。
支持 lifespan 管理各模块生命周期, uvicorn 启动方式。

Usage:
    python -m rest_api.main --host 0.0.0.0 --port 8000
    uvicorn rest_api.main:app --host 0.0.0.0 --port 8000

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from rest_api.constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DOCS_URL,
    JWT_DEFAULT_SECRET,
    LOG_DIR,
    OPENAPI_URL,
    RATE_LIMIT_DEFAULT_REQUESTS,
    RATE_LIMIT_DEFAULT_WINDOW,
    REDOC_URL,
)


# ------------------------------------------------------------------ #
#  模块导入 - 延迟到 create_app 中初始化
# ------------------------------------------------------------------ #

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用程序。

    初始化: 认证 (JWT/API Key)、限流、中间件、所有路由。
    注入管理器实例到路由层。

    Returns:
        配置完成的 FastAPI 应用
    """
    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # === 初始化认证模块 ===
    from rest_api.core.auth import (
        get_jwt_manager,
        get_auth_service,
        init_auth,
    )
    init_auth(secret=_get_jwt_secret())

    # === 初始化限流器 ===
    from rest_api.core.rate_limiter import init_rate_limiter
    init_rate_limiter(
        default_requests=RATE_LIMIT_DEFAULT_REQUESTS,
        window_seconds=RATE_LIMIT_DEFAULT_WINDOW,
    )

    # === 初始化管理器实例 (占位 - 由各子模块提供) ===
    from rest_api.core.api_gateway import get_gateway
    from rest_api.api.router import (
        set_managers,
        device_router,
        stream_router,
        calibration_router,
        data_router,
        auth_router,
    )

    # 创建占位管理器 (生产环境应接入真实实现)
    device_mgr = _create_device_manager_placeholder()
    stream_mgr = _create_stream_manager_placeholder()
    calibration_mgr = _create_calibration_manager_placeholder()
    observation_svc = _create_observation_service_placeholder()
    stats_svc = _create_stats_service_placeholder()
    auth_svc = get_auth_service()

    # 注入到路由层
    set_managers(
        device_manager=device_mgr,
        stream_manager=stream_mgr,
        calibration_manager=calibration_mgr,
        observation_service=observation_svc,
        stats_service=stats_svc,
        auth_service=auth_svc,
    )

    # === 创建 FastAPI 应用 ===
    app = FastAPI(
        title="M7 REST API",
        description="设备管理、流控制、校准、数据查询 REST API 网关 - M7 REST API v1.0",
        version="1.0",
        docs_url=DOCS_URL,
        redoc_url=REDOC_URL,
        openapi_url=OPENAPI_URL,
        lifespan=_lifespan,
    )

    # === 注册中间件 (P0.1/P5.3/P6.2/P6.3) ===
    from rest_api.core.middleware import setup_middleware
    setup_middleware(app)

    # === 注册路由 ===
    from rest_api.core.api_gateway import create_health_router
    app.include_router(create_health_router())
    app.include_router(device_router, prefix="/api/v1")
    app.include_router(stream_router, prefix="/api/v1")
    app.include_router(calibration_router, prefix="/api/v1")
    app.include_router(data_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")

    # 注册全局网关
    gateway = get_gateway()
    gateway.mount_to(app)

    return app


# ------------------------------------------------------------------ #
#  Lifespan 管理
# ------------------------------------------------------------------ #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用程序生命周期管理: 启动时初始化, 关闭时清理。"""
    # === 启动阶段 ===
    print("[M7 API] 服务启动中...")

    # 启动限流器清理任务 (可选)
    # rate_limiter = get_rate_limiter()
    # 定期清理过期记录

    print("[M7 API] 服务已就绪")

    yield  # === 运行阶段 ===

    # === 关闭阶段 ===
    print("[M7 API] 正在关闭服务...")
    print("[M7 API] 服务已关闭")


# ------------------------------------------------------------------ #
#  占位管理器 (生产环境替换为真实实现)
# ------------------------------------------------------------------ #

class _PlaceholderManager:
    """占位管理器 - 返回标准响应格式, 提示需要真实实现。"""

    def __getattr__(self, name: str):
        def _method(*args, **kwargs):
            return {
                "success": True,
                "message": f"[PLACEHOLDER] {self.__class__.__name__}.{name} 需要真实实现",
                "data": {},
            }
        return _method


def _create_device_manager_placeholder():
    """设备管理占位。"""
    return _PlaceholderManager()


def _create_stream_manager_placeholder():
    """流控制占位。"""
    return _PlaceholderManager()


def _create_calibration_manager_placeholder():
    """校准管理占位。"""
    return _PlaceholderManager()


def _create_observation_service_placeholder():
    """观测数据服务占位。"""
    return _PlaceholderManager()


def _create_stats_service_placeholder():
    """统计服务占位。"""
    mgr = _PlaceholderManager()
    # 确保 get_stats 返回有意义的默认值
    mgr.get_stats = lambda: {
        "total_devices": 0,
        "online_devices": 0,
        "active_streams": 0,
        "active_calibrations": 0,
    }
    return mgr


# ------------------------------------------------------------------ #
#  JWT Secret 获取
# ------------------------------------------------------------------ #

def _get_jwt_secret() -> str:
    """从环境变量获取 JWT Secret, 否则使用默认值。

    生产环境务必设置 REST_API_JWT_SECRET 环境变量。
    """
    import os
    secret = os.environ.get("REST_API_JWT_SECRET")
    if secret:
        return secret
    print("[REST_API WARNING] 使用默认 JWT Secret, 生产环境请设置 REST_API_JWT_SECRET")
    return JWT_DEFAULT_SECRET


# ------------------------------------------------------------------ #
#  创建全局 app 实例 (供 uvicorn 调用)
# ------------------------------------------------------------------ #

app = create_app()


# ------------------------------------------------------------------ #
#  CLI 入口
# ------------------------------------------------------------------ #

def main() -> None:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(description="M7 REST API v1.0")
    parser.add_argument(
        "--host", default=DEFAULT_HOST,
        help=f"监听地址 (默认: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"监听端口 (默认: {DEFAULT_PORT})",
    )
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")

    args = parser.parse_args()

    try:
        import uvicorn
        uvicorn.run(
            "rest_api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError:
        print("错误: 需要安装 uvicorn, 请运行: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
