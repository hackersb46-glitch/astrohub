"""
M6 Web UI Service v1.0 - 应用入口点

初始化仪表盘聚合器、通知管理器、健康检查器，配置 FastAPI 服务。
支持 lifespan 管理各模块生命周期，uvicorn 启动方式。

Usage:
    python -m webui.main --host 0.0.0.0 --port 8002
    uvicorn webui.main:app --host 0.0.0.0 --port 8002

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI


# ------------------------------------------------------------------ #
#  模块导入 - 延迟到 create_app 中初始化
# ------------------------------------------------------------------ #

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用程序。

    初始化所有管理器实例，注入到路由层，挂载 SPA 静态文件服务。

    Returns:
        配置完成的 FastAPI 应用
    """
    # 延迟导入
    from webui.api.router import router, set_managers
    from webui.constants import DATA_DIR, LOG_DIR
    from webui.core.dashboard import DashboardAggregator
    from webui.core.health_check import HealthChecker
    from webui.core.notification import NotificationManager
    from webui.core.web_server import SPAServer

    # 确保必要目录存在
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 初始化各管理器
    dashboard_aggregator = DashboardAggregator()
    notification_manager = NotificationManager()
    health_checker = HealthChecker()
    spa_server = SPAServer()

    # 注入到路由层
    set_managers(
        dashboard_aggregator=dashboard_aggregator,
        notification_manager=notification_manager,
        health_checker=health_checker,
    )

    # 创建应用
    app = FastAPI(
        title="M6 Web UI Service",
        description="设备管理、流预览、校准控制的 Web 前端后端服务 - M6 Web UI v1.0",
        version="1.0",
        lifespan=_lifespan,
    )

    # 挂载 API 路由
    app.include_router(router)

    # 将管理器存储到 app.state 以便 lifespan 访问
    app.state.dashboard_aggregator = dashboard_aggregator
    app.state.notification_manager = notification_manager
    app.state.health_checker = health_checker
    app.state.spa_server = spa_server

    return app


# ------------------------------------------------------------------ #
#  Lifespan 管理
# ------------------------------------------------------------------ #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用程序生命周期管理：启动时初始化各模块，关闭时清理资源。"""
    # === 启动阶段 ===
    dashboard = app.state.dashboard_aggregator

    # 初始化 Dashboard HTTP 客户端
    await dashboard.init()

    print("  ✓ M6 Web UI Service 启动成功")

    yield  # === 运行阶段 ===

    # === 关闭阶段 ===
    print("  正在关闭 M6 Web UI Service ...")

    # 关闭 Dashboard 连接
    await dashboard.close()

    print("  ✓ M6 Web UI Service 已关闭")


# ------------------------------------------------------------------ #
#  创建全局 app 实例（供 uvicorn 调用）
# ------------------------------------------------------------------ #

app = create_app()


# ------------------------------------------------------------------ #
#  CLI 入口
# ------------------------------------------------------------------ #

def main() -> None:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(description="M6 Web UI Service v1.0")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8002, help="监听端口 (默认: 8002)")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")

    args = parser.parse_args()

    try:
        import uvicorn
        uvicorn.run(
            "webui.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError:
        print("错误: 需要安装 uvicorn，请运行: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
