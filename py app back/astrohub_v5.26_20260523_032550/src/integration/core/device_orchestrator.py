"""
M10 Integration v1.0 - 设备编排器

多模块设备协同操作，协调 M1-M9 各模块执行设备级端到端流程。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from integration.constants import (
    E2EStage,
    ErrorCode,
    E2E_FLOW_TIMEOUT,
    INTEGRATION_STARTUP_TIMEOUT,
)
from integration.core.error_handler import (
    E2EFlowError,
    IntegrationError,
    ModuleCommunicationError,
    get_error_aggregator,
)
from integration.core.event_bus import EventType, get_event_bus

logger = logging.getLogger("integration")


# ================================================================== #
#  模块客户端接口
# ================================================================== #

class ModuleClient:
    """子模块客户端接口。

    每个被集成的模块 (M1-M9) 需要提供一个客户端实例，
    设备编排器通过客户端间调用各模块。

    Supports both direct Python calls (manager instance) and HTTP calls (base_url).
    """

    def __init__(self, name: str, base_url: str = "", manager: Any = None) -> None:
        self.name = name
        self.base_url = base_url
        self._manager = manager  # Direct Python manager instance
        self._available = False
        self._last_check = 0.0

    async def health_check(self) -> bool:
        """检查模块是否可用。"""
        if self._manager:
            # Direct check via manager instance
            try:
                if hasattr(self._manager, "get_status"):
                    status = self._manager.get_status()
                    ok = status.get("status") in ("running", "UP", "healthy") if isinstance(status, dict) else True
                elif hasattr(self._manager, "is_connected"):
                    ok = bool(self._manager.is_connected)
                else:
                    ok = True
                self._available = ok
                self._last_check = time.time()
                return ok
            except Exception:
                self._available = False
                return False

        # HTTP health check
        if self.base_url:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        ok = resp.status == 200
                        self._available = ok
                        self._last_check = time.time()
                        return ok
            except ImportError:
                # Fallback to urllib
                try:
                    import urllib.request
                    req = urllib.request.Request(f"{self.base_url}/health")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        ok = resp.status == 200
                        self._available = ok
                        self._last_check = time.time()
                        return ok
                except Exception:
                    self._available = False
                    return False
            except Exception:
                self._available = False
                return False

        self._available = True
        self._last_check = time.time()
        return True

    async def call(self, action: str, **kwargs: Any) -> dict:
        """调用模块操作。

        Tries direct Python call first (manager), falls back to HTTP.
        """
        # Direct Python call
        if self._manager:
            return await self._call_direct(action, **kwargs)

        # HTTP call
        if self.base_url:
            return await self._call_http(action, **kwargs)

        return {"success": False, "message": f"模块 {self.name} 无可用连接方式", "data": None}

    async def _call_direct(self, action: str, **kwargs: Any) -> dict:
        """Direct Python method call on manager."""
        try:
            method = getattr(self._manager, action, None)
            if method is None:
                return {"success": False, "message": f"方法 {action} 不存在于 {self.name}", "data": None}

            if asyncio.iscoroutinefunction(method):
                result = await method(**kwargs)
            else:
                result = method(**kwargs)

            if isinstance(result, dict):
                return result
            return {"success": True, "message": "调用成功", "data": result}
        except Exception as exc:
            return {"success": False, "message": f"调用 {self.name}.{action} 失败: {exc}", "data": None}

    async def _call_http(self, action: str, **kwargs: Any) -> dict:
        """HTTP call to module API."""
        try:
            import urllib.request
            import urllib.parse
            import json

            url = f"{self.base_url}/api/v1/{action}"

            # Build URL with query params for GET, body for POST
            if kwargs:
                query = urllib.parse.urlencode(kwargs)
                url = f"{url}?{query}"

            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return {"success": True, "message": "HTTP 调用成功", "data": data}
        except Exception as exc:
            return {"success": False, "message": f"HTTP 调用 {self.name}/{action} 失败: {exc}", "data": None}

    @property
    def is_available(self) -> bool:
        return self._available


# ================================================================== #
#  设备编排器
# ================================================================== #

class DeviceOrchestrator:
    """设备级端到端流程编排器。

    协调多个模块 (M1-M9) 执行完整设备生命周期:
    设备发现 → 认证 → 流预览 → 校准

    对应评审 P1 (端到端流程)。
    """

    def __init__(self) -> None:
        self._clients: dict[str, ModuleClient] = {}
        self._running_flows: dict[str, dict] = {}
        self._event_bus = get_event_bus()

    def register_module(self, name: str, client: ModuleClient) -> None:
        """注册模块客户端。

        Args:
            name: 模块名 (如 m2_device_manager)
            client: 模块客户端实例
        """
        self._clients[name] = client
        logger.info("[M10 INTEGRATION] 模块已注册: %s", name)

    def unregister_module(self, name: str) -> None:
        """注销模块客户端。"""
        self._clients.pop(name, None)
        logger.info("[M10 INTEGRATION] 模块已注销: %s", name)

    async def health_check_all(self, timeout: float = INTEGRATION_STARTUP_TIMEOUT) -> dict[str, bool]:
        """检查所有已注册模块的健康状态。

        Args:
            timeout: 总超时 (秒)

        Returns:
            {模块名: 是否可用}
        """
        results: dict[str, bool] = {}
        async def _check_one(name: str, client: ModuleClient) -> None:
            try:
                ok = await asyncio.wait_for(client.health_check(), timeout=timeout)
                results[name] = ok
            except asyncio.TimeoutError:
                results[name] = False
            except Exception as exc:
                logger.warning("[M10 INTEGRATION] 模块健康检查失败: %s, error=%s", name, exc)
                results[name] = False

        checks = [_check_one(name, client) for name, client in self._clients.items()]
        await asyncio.gather(*checks, return_exceptions=True)
        return results

    async def run_e2e_flow(
        self,
        flow_id: str,
        device_id: str,
        stages: list[E2EStage] | None = None,
        timeout: float = E2E_FLOW_TIMEOUT,
    ) -> dict:
        """执行端到端设备流程。

        Args:
            flow_id: 流程 ID
            device_id: 设备 ID
            stages: 要执行的阶段列表 (默认全部)
            timeout: 流程超时 (秒)

        Returns:
            流程执行结果
        """
        if stages is None:
            stages = list(E2EStage)

        # 发布流程开始事件
        await self._event_bus.publish(
            EventType.E2E_FLOW_STARTED,
            flow_id=flow_id,
            device_id=device_id,
            stages=[s.value for s in stages],
        )

        flow_data: dict = {
            "flow_id": flow_id,
            "device_id": device_id,
            "stages": [],
            "started_at": time.time(),
        }
        self._running_flows[flow_id] = flow_data

        try:
            for stage in stages:
                result = await asyncio.wait_for(
                    self._execute_stage(stage, device_id),
                    timeout=timeout,
                )
                flow_data["stages"].append({
                    "stage": stage.value,
                    "success": result.get("success", False),
                    "data": result.get("data"),
                })
                if not result.get("success"):
                    # 阶段失败，发布失败事件
                    await self._event_bus.publish(
                        EventType.E2E_FLOW_FAILED,
                        flow_id=flow_id,
                        device_id=device_id,
                        failed_stage=stage.value,
                        error=result.get("message", "未知错误"),
                    )
                    # 记录错误
                    await get_error_aggregator().record(
                        E2EFlowError(
                            stage=stage.value,
                            message=result.get("message", "阶段执行失败"),
                        )
                    )
                    return {
                        "success": False,
                        "message": f"流程在阶段 '{stage.value}' 失败",
                        "data": flow_data,
                    }

            # 全流程成功
            flow_data["completed_at"] = time.time()
            await self._event_bus.publish(
                EventType.E2E_FLOW_COMPLETED,
                flow_id=flow_id,
                device_id=device_id,
            )
            return {
                "success": True,
                "message": "端到端流程执行成功",
                "data": flow_data,
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "message": f"端到端流程超时 ({timeout}s)",
                "data": flow_data,
            }
        except Exception as exc:
            await self._event_bus.publish(
                EventType.E2E_FLOW_FAILED,
                flow_id=flow_id,
                device_id=device_id,
                error=str(exc),
            )
            return {
                "success": False,
                "message": f"端到端流程异常: {exc}",
                "data": flow_data,
            }
        finally:
            self._running_flows.pop(flow_id, None)

    async def _execute_stage(self, stage: E2EStage, device_id: str) -> dict:
        """执行单个 E2E 阶段。

        根据阶段类型路由到对应模块客户端。
        """
        logger.info("[M10 INTEGRATION] E2E 阶段: %s, 设备: %s", stage.value, device_id)

        if stage == E2EStage.DEVICE_DISCOVERY:
            return await self._stage_device_discovery(device_id)
        elif stage == E2EStage.AUTHENTICATION:
            return await self._stage_authentication(device_id)
        elif stage == E2EStage.STREAM_PREVIEW:
            return await self._stage_stream_preview(device_id)
        elif stage == E2EStage.CALIBRATION:
            return await self._stage_calibration(device_id)
        else:
            return {"success": False, "message": f"未知阶段: {stage.value}", "data": None}

    async def _stage_device_discovery(self, device_id: str) -> dict:
        """阶段: 设备发现 (M1/M2)。"""
        client = self._clients.get("device")
        if not client:
            return {"success": False, "message": "设备管理模块未注册", "data": None}
        try:
            return await client.call("discover", device_id=device_id)
        except Exception as exc:
            return {"success": False, "message": f"设备发现失败: {exc}", "data": None}

    async def _stage_authentication(self, device_id: str) -> dict:
        """阶段: 设备认证 (M2)。"""
        client = self._clients.get("device")
        if not client:
            return {"success": False, "message": "设备管理模块未注册", "data": None}
        try:
            return await client.call("authenticate", device_id=device_id)
        except Exception as exc:
            return {"success": False, "message": f"设备认证失败: {exc}", "data": None}

    async def _stage_stream_preview(self, device_id: str) -> dict:
        """阶段: 流预览 (M3)。"""
        client = self._clients.get("stream")
        if not client:
            return {"success": False, "message": "流服务模块未注册", "data": None}
        try:
            return await client.call("start_preview", device_id=device_id)
        except Exception as exc:
            return {"success": False, "message": f"流预览失败: {exc}", "data": None}

    async def _stage_calibration(self, device_id: str) -> dict:
        """阶段: 校准 (M4)。"""
        client = self._clients.get("calibration")
        if not client:
            return {"success": False, "message": "校准模块未注册", "data": None}
        try:
            return await client.call("run_calibration", device_id=device_id)
        except Exception as exc:
            return {"success": False, "message": f"校准失败: {exc}", "data": None}

    def get_running_flows(self) -> dict:
        """获取正在运行的流程。"""
        return dict(self._running_flows)

    def list_modules(self) -> list[dict]:
        """获取已注册模块列表。"""
        return [
            {"name": name, "available": client.is_available, "url": client.base_url}
            for name, client in self._clients.items()
        ]


# 全局实例
_orchestrator: DeviceOrchestrator | None = None


def get_orchestrator_device() -> DeviceOrchestrator:
    """获取全局设备编排器。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = DeviceOrchestrator()
    return _orchestrator
