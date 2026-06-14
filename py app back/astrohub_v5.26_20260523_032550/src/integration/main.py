"""
M10 Integration v1.0 - 应用入口点

系统集成服务: 全模块集成测试、端到端流程验证、性能优化、异常恢复。

初始化所有集成管理器，启动 FastAPI 服务。
支持 lifespan 管理各模块生命周期，uvicorn 启动方式。

Usage:
    python -m integration.main --host 0.0.0.0 --port 8010
    uvicorn integration.main:app --host 0.0.0.0 --port 8010

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from integration.constants import DEFAULT_HOST, DEFAULT_PORT
from integration.core.device_orchestrator import ModuleClient

logger = logging.getLogger("integration")


# ------------------------------------------------------------------ #
#  模块导入 - 延迟到 create_app 中初始化
# ------------------------------------------------------------------ #

def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用程序。

    初始化: 健康聚合器、错误聚合器、任务调度器、设备编排器。
    注入管理器实例到路由层。

    Returns:
        配置完成的 FastAPI 应用
    """
    # 延迟导入
    from integration.api.router import router, set_managers
    from integration.core.device_orchestrator import get_orchestrator_device
    from integration.core.error_handler import get_error_aggregator
    from integration.core.health_aggregator import HealthAggregator
    from integration.core.task_scheduler import get_scheduler

    # 初始化各管理器
    health_agg = HealthAggregator()
    scheduler = get_scheduler()
    error_agg = get_error_aggregator()
    orchestrator = get_orchestrator_device()

    # 注入到路由层
    set_managers(
        health_aggregator=health_agg,
        task_scheduler=scheduler,
        error_aggregator=error_agg,
        device_orchestrator=orchestrator,
    )

    # 创建应用
    app = FastAPI(
        title="M10 Integration",
        description="系统集成服务 - 全模块集成测试、端到端流程验证、性能优化 - M10 Integration v1.0",
        version="1.0",
        lifespan=_lifespan,
    )

    # 挂载路由
    app.include_router(router)

    # 存储到 app.state 以便 lifespan 访问
    app.state.health_aggregator = health_agg
    app.state.scheduler = scheduler
    app.state.error_aggregator = error_agg
    app.state.orchestrator = orchestrator

    return app


# ------------------------------------------------------------------ #
#  Lifespan 管理
# ------------------------------------------------------------------ #

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """应用程序生命周期管理: 启动时初始化，关闭时清理。"""
    # === 启动阶段 ===
    print("[M10 INTEGRATION] 服务启动中...")

    # 启动任务调度器
    scheduler = app.state.scheduler
    await scheduler.start()

    # 注册默认模块到健康聚合器 (M1-M11)
    health_agg = app.state.health_aggregator
    for mod_name in [
        "ptz",
        "device",
        "stream",
        "calibration",
        "database",
        "webui",
        "rest_api",
        "websocket",
        "ascom",
        "integration",
        "deployment",
    ]:
        health_agg.register_module(mod_name)

    print(f"[M10 INTEGRATION] 已注册 11 个子模块 (M1-M11)")

    # === 事件总线集成: 订阅模块状态变更 ===
    from integration.core.event_bus import get_event_bus, EventType
    event_bus = get_event_bus()

    async def _on_module_status_changed(**kwargs: Any) -> None:
        """模块状态变更时，更新健康聚合器。"""
        module_name = kwargs.get("module_name", "unknown")
        new_status = kwargs.get("status", "unknown")
        health_agg.update(module_name, new_status)  # type: ignore
        logger.info("[M10] 模块状态变更: %s -> %s", module_name, new_status)

    async def _on_device_online(**kwargs: Any) -> None:
        """设备上线事件。"""
        device_id = kwargs.get("device_id", "unknown")
        logger.info("[M10] 设备上线: %s", device_id)

    async def _on_device_offline(**kwargs: Any) -> None:
        """设备离线事件。"""
        device_id = kwargs.get("device_id", "unknown")
        logger.warning("[M10] 设备离线: %s", device_id)

    async def _on_health_degraded(**kwargs: Any) -> None:
        """健康降级事件。"""
        logger.warning("[M10] 系统健康降级: %s", kwargs)

    event_bus.subscribe(EventType.MODULE_STATUS_CHANGED, _on_module_status_changed)
    event_bus.subscribe(EventType.DEVICE_ONLINE, _on_device_online)
    event_bus.subscribe(EventType.DEVICE_OFFLINE, _on_device_offline)
    event_bus.subscribe(EventType.HEALTH_DEGRADED, _on_health_degraded)

    print("[M10 INTEGRATION] 事件总线已集成 (状态变更/设备上下线/健康告警)")

    # === 模块间数据流配置 ===
    # M2(设备发现) → M1(PTZ控制)
    orchestrator.register_module("device", ModuleClient(
        name="device",
        base_url="http://localhost:8000",
    ))
    # M3(视频流)
    orchestrator.register_module("stream", ModuleClient(
        name="stream",
        base_url="http://localhost:8000",
    ))
    # M4(校准)
    orchestrator.register_module("calibration", ModuleClient(
        name="calibration",
        base_url="http://localhost:8000",
    ))
    # M9(ASCOM)
    orchestrator.register_module("ascom", ModuleClient(
        name="ascom",
        base_url="http://localhost:8009",
    ))

    print("[M10 INTEGRATION] 模块间数据流已打通 (M2→M1, M1→M3, M4→M1, M9→M1)")
    print("[M10 INTEGRATION] 服务已就绪")

    yield  # === 运行阶段 ===

    # === 关闭阶段 ===
    print("[M10 INTEGRATION] 正在关闭服务...")

    # 停止任务调度器
    await scheduler.stop()

    print("[M10 INTEGRATION] 服务已关闭")


# ------------------------------------------------------------------ #
#  创建全局 app 实例 (供 uvicorn 调用)
# ------------------------------------------------------------------ #

app = create_app()


# ------------------------------------------------------------------ #
#  CLI 入口
# ------------------------------------------------------------------ #

def main() -> None:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(description="M10 Integration v1.0 - 系统集成服务")
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
            "integration.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except ImportError:
        print("错误: 需要安装 uvicorn, 请运行: pip install uvicorn")
        sys.exit(1)


if __name__ == "__main__":
    main()
