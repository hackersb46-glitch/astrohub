"""
M9 ASCOM v1.0 - 应用入口点

ASCOM 天文设备集成 REST API 网关: 望远镜、焦点器、圆顶、滤镜轮、气象站。

初始化 DriverManager, 启动 FastAPI 服务。
支持 lifespan 管理各设备生命周期, uvicorn 启动方式。

Usage:
    python -m ascom.main --host 0.0.0.0 --port 8009
    uvicorn ascom.main:app --host 0.0.0.0 --port 8009

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.ascom.constants import DEFAULT_HOST, DEFAULT_PORT


# ------------------------------------------------------------------ #
#  Lifespan 管理
# ------------------------------------------------------------------ #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用程序生命周期管理: 启动时初始化驱动, 关闭时断开所有设备。"""
    # === 启动阶段 ===
    print("[M9 ASCOM] 服务启动中...")

    from src.ascom.core.driver_manager import init_driver_manager
    mgr = init_driver_manager()
    status = mgr.get_all_status()
    print(f"[M9 ASCOM] 驱动管理器初始化完成: {list(status.keys())}")
    print("[M9 ASCOM] 服务已就绪")

    yield  # === 运行阶段 ===

    # === 关闭阶段 ===
    print("[M9 ASCOM] 正在关闭服务...")
    mgr.shutdown()
    print("[M9 ASCOM] 所有设备已断开, 服务已关闭")


# ------------------------------------------------------------------ #
#  创建 FastAPI 应用
# ------------------------------------------------------------------ #

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用程序。

    注册: ASCOM 路由、lifespan 生命周期管理。

    Returns:
        配置完成的 FastAPI 应用
    """
    app = FastAPI(
        title="M9 ASCOM",
        description="ASCOM 天文设备集成 REST API - 望远镜、焦点器、圆顶、滤镜轮、气象站",
        version="1.0",
        lifespan=_lifespan,
    )

    # === 注册路由 ===
    from src.ascom.api.router import router
    app.include_router(router)

    return app


# ------------------------------------------------------------------ #
#  创建全局 app 实例 (供 uvicorn 调用)
# ------------------------------------------------------------------ #

app = create_app()


# ------------------------------------------------------------------ #
#  CLI 入口
# ------------------------------------------------------------------ #

def main() -> None:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(description="M9 ASCOM v1.0 - ASCOM 天文设备集成 REST API")
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
            "ascom.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError:
        print("错误: 需要安装 uvicorn, 请运行: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
