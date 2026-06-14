"""
Database Service v1.0 - 应用入口点

初始化 SQLAlchemy 连接池、表结构、配置 FastAPI 服务。
支持 lifespan 管理数据库生命周期，uvicorn 启动方式。

Usage:
    python -m database.main --host 0.0.0.0 --port 8001
    uvicorn database.main:app --host 0.0.0.0 --port 8001

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import argparse
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI


# ------------------------------------------------------------------ #
#  延迟导入 - 在 create_app 中初始化
# ------------------------------------------------------------------ #

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用程序。

    初始化数据库连接，挂载路由。

    Returns:
        配置完成的 FastAPI 应用
    """
    # 延迟导入（避免创建应用时就加载所有依赖）
    from src.database.api.router import router
    from src.database.core.db_manager import init_db
    from src.database.constants import LOG_DIR, DATA_DIR

    def _startup_tasks():
        """启动前任务：创建必要目录。"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    _startup_tasks()

    # 创建应用
    app = FastAPI(
        title="Database Service",
        description="M5 数据库管理 - 设备数据、观测数据、配置数据的存储与查询 v1.0",
        version="1.0",
        lifespan=_lifespan,
    )

    # 挂载路由
    app.include_router(router)

    return app


# ------------------------------------------------------------------ #
#  Lifespan 管理
# ------------------------------------------------------------------ #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用程序生命周期管理：启动时初始化数据库，关闭时清理连接。"""
    # === 启动阶段 ===
    from src.database.core.db_manager import DatabaseManager, init_db

    # 确保目录存在
    from src.database.constants import DATA_DIR, LOG_DIR
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 初始化数据库表结构(幂等)
    await init_db()

    # 执行迁移
    from src.database.core.db_manager import DatabaseManager
    from src.database.core.migration import MigrationManager

    session_factory = DatabaseManager.get_session_factory()
    async with session_factory() as session:
        migration_mgr = MigrationManager(session)
        applied = await migration_mgr.migrate()
        if applied:
            print(f"  [M5] 已应用迁移: {', '.join(applied)}")

    # 关闭 session
    await session.close()

    print("  ✓ Database Service 启动成功")

    yield  # === 运行阶段 ===

    # === 关闭阶段 ===
    print("  正在关闭 Database Service ...")
    await DatabaseManager.close()
    print("  ✓ Database Service 已关闭")


# ------------------------------------------------------------------ #
#  创建全局 app 实例（供 uvicorn 调用）
# ------------------------------------------------------------------ #

app = create_app()


# ------------------------------------------------------------------ #
#  CLI 入口
# ------------------------------------------------------------------ #

def main() -> None:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(description="Database Service v1.0")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="监听端口 (默认: 8001)")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")

    args = parser.parse_args()

    try:
        import uvicorn
        uvicorn.run(
            "database.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError:
        print("错误: 需要安装 uvicorn，请运行: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
