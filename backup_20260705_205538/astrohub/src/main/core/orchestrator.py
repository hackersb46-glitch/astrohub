"""
M12 Unified Integration v1.0 - 模块编排器

协调 M1-M11 模块的生命周期：启动、停止、重启、状态查询。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import datetime, timezone
from typing import Any

from src.main.constants import MODULE_ORDER

logger = logging.getLogger("m12.orchestrator")


class Orchestrator:
    """M1-M11 模块生命周期编排器。

    按 MODULE_ORDER 顺序初始化模块，反向顺序停止模块。
    """

    def __init__(self) -> None:
        self._modules: dict[str, Any] = {}
        self._status: dict[str, dict[str, Any]] = {}
        self._started = False

    async def start(self) -> None:
        """按 MODULE_ORDER 顺序初始化所有模块。"""
        if self._started:
            logger.warning("编排器已启动，跳过重复初始化")
            return

        logger.info("=== M12 编排器启动 ===")
        for module_name in MODULE_ORDER:
            try:
                logger.info("初始化模块: %s ...", module_name)
                module_instance = await self._init_module(module_name)
                self._modules[module_name] = module_instance
                self._status[module_name] = {
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "error": None,
                }
                logger.info("模块 %s 初始化成功", module_name)
            except Exception as e:
                logger.error("模块 %s 初始化失败: %s", module_name, e)
                self._status[module_name] = {
                    "status": "error",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(e),
                }

        self._started = True
        logger.info("=== M12 编排器启动完成 (%d/%d 模块) ===",
                     self._running_count(), len(MODULE_ORDER))

    async def stop(self) -> None:
        """按反向顺序停止所有模块。"""
        if not self._started:
            logger.warning("编排器未启动，无需停止")
            return

        logger.info("=== M12 编排器停止中 ===")
        for module_name in reversed(MODULE_ORDER):
            try:
                logger.info("停止模块: %s ...", module_name)
                await self._stop_module(module_name)
                if module_name in self._status:
                    self._status[module_name]["status"] = "stopped"
                logger.info("模块 %s 已停止", module_name)
            except Exception as e:
                logger.error("模块 %s 停止失败: %s", module_name, e)

        self._started = False
        logger.info("=== M12 编排器已停止 ===")

    async def restart_module(self, name: str) -> dict[str, Any]:
        """重启指定模块。

        Args:
            name: 模块名称（如 m1_ptz_astro）

        Returns:
            操作结果 dict
        """
        if name not in MODULE_ORDER:
            return {
                "success": False,
                "message": f"未知模块: {name}",
            }

        logger.info("重启模块: %s", name)
        try:
            await self._stop_module(name)
            self._modules.pop(name, None)

            module_instance = await self._init_module(name)
            self._modules[name] = module_instance
            self._status[name] = {
                "status": "running",
                "restarted_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
            logger.info("模块 %s 重启成功", name)
            return {
                "success": True,
                "message": f"模块 {name} 已重启",
            }
        except Exception as e:
            logger.error("模块 %s 重启失败: %s", name, e)
            self._status[name] = {
                "status": "error",
                "restarted_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
            }
            return {
                "success": False,
                "message": f"模块 {name} 重启失败: {e}",
            }

    def get_module_status(self) -> dict[str, dict[str, Any]]:
        """返回所有模块的状态。

        Returns:
            {module_name: {status, started_at/restarted_at, error}} 字典
        """
        result = {}
        for module_name in MODULE_ORDER:
            if module_name in self._status:
                result[module_name] = dict(self._status[module_name])
            else:
                result[module_name] = {
                    "status": "not_loaded",
                    "started_at": None,
                    "error": None,
                }
        return result

    def get_module(self, name: str) -> Any | None:
        """获取指定模块实例。

        Args:
            name: 模块名称

        Returns:
            模块实例，未找到返回 None
        """
        return self._modules.get(name)

    def _running_count(self) -> int:
        """统计运行中模块数量。"""
        return sum(
            1 for s in self._status.values()
            if s.get("status") == "running"
        )

    # ---- 内部辅助方法 ----

    async def _init_module(self, module_name: str) -> Any:
        """动态导入并初始化单个模块。

        尝试以下入口（按优先级）:
        1. {module_name}.main:create_app()  -> FastAPI app
        2. {module_name}.core.*Manager      -> 管理器实例
        3. 降级为模块对象本身
        
        v7.12: 模块不存在时返回 None 而不是抛出异常
        """
        try:
            mod = importlib.import_module(f"src.{module_name}.main")
            if hasattr(mod, "create_app"):
                return mod.create_app()
        except (ImportError, ModuleNotFoundError):
            pass

        try:
            mod = importlib.import_module(f"src.{module_name}.core")
            for attr_name in dir(mod):
                if attr_name.endswith("Manager"):
                    cls = getattr(mod, attr_name)
                    if isinstance(cls, type):
                        return cls()
        except (ImportError, ModuleNotFoundError):
            pass

        # 降级：导入模块本身
        try:
            mod = importlib.import_module(f"src.{module_name}")
            return mod
        except (ImportError, ModuleNotFoundError):
            logger.warning("模块 src.%s 不存在，跳过", module_name)
            return None

    async def _stop_module(self, name: str) -> None:
        """停止单个模块。

        尝试调用 app._shutdown()、stop()、close() 等方法。
        """
        instance = self._modules.get(name)
        if instance is None:
            return

        # 尝试 FastAPI app 的 lifespan shutdown
        if hasattr(instance, "_shutdown") and callable(instance._shutdown):
            await instance._shutdown()  # type: ignore[misc]

        # 尝试通用 stop() 方法
        if hasattr(instance, "stop") and callable(instance.stop):
            result = instance.stop()
            if asyncio.iscoroutine(result):
                await result

        # 尝试 close() 方法
        if hasattr(instance, "close") and callable(instance.close):
            result = instance.close()
            if asyncio.iscoroutine(result):
                await result
