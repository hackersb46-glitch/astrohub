"""
M11 Deployment Service v1.0 - 应用入口点

FastAPI 部署管理网关: Docker 构建/编排、服务管理、健康检查、回滚、日志查询。

初始化所有核心模块 (部署配置/健康监控/日志收集/中间件/路由), 启动 FastAPI 服务。
支持 lifespan 管理各模块生命周期, uvicorn 启动方式。

Usage:
    python -m deployment.main --host 0.0.0.0 --port 8011
    uvicorn deployment.main:app --host 0.0.0.0 --port 8011

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from deployment.constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    LOG_DIR,
)


# ------------------------------------------------------------------ #
#  模块导入 - 延迟到 create_app 中初始化
# ------------------------------------------------------------------ #

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用程序。

    初始化: 部署配置、健康监控、日志收集、所有路由。
    注入管理器实例到路由层。

    Returns:
        配置完成的 FastAPI 应用
    """
    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # === 初始化管理器实例 ===
    from deployment.api.router import (
        set_managers,
        router,
        health_router,
    )
    from deployment.core.docker_builder import DockerBuilder
    from deployment.core.service_manager import ServiceManager
    from deployment.core.health_monitor import HealthMonitor
    from deployment.core.rollback import RollbackManager
    from deployment.core.log_collector import LogCollector

    # 创建管理器实例
    docker_builder = DockerBuilder()
    service_manager = ServiceManager()
    health_monitor = HealthMonitor()
    rollback_manager = RollbackManager()
    log_collector = LogCollector.instance()

    # 注入到路由层
    set_managers(
        docker_builder=docker_builder,
        service_manager=service_manager,
        health_monitor=health_monitor,
        rollback_manager=rollback_manager,
        log_collector=log_collector,
    )

    # === 创建 FastAPI 应用 ===
    app = FastAPI(
        title="M11 Deployment Service",
        description="部署管理 REST API 网关 - Docker 构建/编排、服务管理、健康检查、回滚、日志查询 - M11 Deployment Service v1.0",
        version="1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=_lifespan,
    )

    # === 注册路由 ===
    app.include_router(health_router)
    app.include_router(router)

    return app


# ------------------------------------------------------------------ #
#  Lifespan 管理
# ------------------------------------------------------------------ #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用程序生命周期管理: 启动时初始化, 关闭时清理。"""
    # === 启动阶段 ===
    print("[M11 Deployment] 服务启动中...")

    # 启动健康监控定时任务 (可选)
    # health_monitor = HealthMonitor()
    # health_monitor.start_monitoring()

    # 启动日志轮转任务 (可选)
    # log_collector = LogCollector.instance()
    # log_collector.start_rotation()

    print("[M11 Deployment] 服务已就绪")

    yield  # === 运行阶段 ===

    # === 关闭阶段 ===
    print("[M11 Deployment] 正在关闭服务...")

    # 停止健康监控
    # health_monitor.stop_monitoring()

    # 清理日志收集器
    # log_collector.stop_rotation()

    print("[M11 Deployment] 服务已关闭")


# ------------------------------------------------------------------ #
#  创建全局 app 实例 (供 uvicorn 调用)
# ------------------------------------------------------------------ #

app = create_app()


# ------------------------------------------------------------------ #
#  CLI 入口
# ------------------------------------------------------------------ #

def main() -> None:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(description="M11 Deployment Service v1.0")
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
            "deployment.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError:
        print("错误: 需要安装 uvicorn, 请运行: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
