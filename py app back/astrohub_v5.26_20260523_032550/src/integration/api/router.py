"""
M10 Integration v1.0 - API 路由

集成服务路由: 健康聚合、E2E 流程、模块状态、集成报告。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from integration.constants import ErrorCode, ERROR_CODE_DESCRIPTION


router = APIRouter(prefix="/api/v1/integration", tags=["M10 Integration"])


# ================================================================== #
#  管理器注入
# ================================================================== #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) -> None:
    """注入管理器实例。"""
    _managers.update(kwargs)


def _get_health_aggregator() -> Any:
    mgr = _managers.get("health_aggregator")
    if mgr is None:
        raise HTTPException(status_code=500, detail="HealthAggregator 未初始化")
    return mgr


def _get_device_orchestrator() -> Any:
    mgr = _managers.get("device_orchestrator")
    if mgr is None:
        raise HTTPException(status_code=500, detail="DeviceOrchestrator 未初始化")
    return mgr


def _get_error_aggregator() -> Any:
    mgr = _managers.get("error_aggregator")
    if mgr is None:
        raise HTTPException(status_code=500, detail="ErrorAggregator 未初始化")
    return mgr


def _get_task_scheduler() -> Any:
    mgr = _managers.get("task_scheduler")
    if mgr is None:
        raise HTTPException(status_code=500, detail="TaskScheduler 未初始化")
    return mgr


# ================================================================== #
#  响应辅助
# ================================================================== #

def _ok_response(data: Any = None, message: str = "操作成功") -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def _error_response(code: ErrorCode, message: str = "") -> dict[str, Any]:
    return {
        "success": False,
        "message": message or ERROR_CODE_DESCRIPTION.get(code, code.value),
        "error_code": code.value,
        "data": None,
    }


# ================================================================== #
#  健康聚合 (P0.1/P0.3)
# ================================================================== #

@router.get("/health", summary="系统健康状态")
async def get_system_health() -> dict:
    """获取全模块健康聚合状态 (P0.1/P0.3)。"""
    agg = _get_health_aggregator()
    return _ok_response(data=agg.summary(), message="系统健康检查完成")


@router.get("/health/{module_name}", summary="单模块健康状态")
async def get_module_health(module_name: str) -> dict:
    """获取指定模块健康状态。"""
    agg = _get_health_aggregator()
    record = agg.get_record(module_name)
    if record is None:
        return _error_response(ErrorCode.MODULE_NOT_AVAILABLE, f"模块 '{module_name}' 未注册")
    return _ok_response(data=record.to_dict())


# ================================================================== #
#  E2E 流程 (P1)
# ================================================================== #

@router.post("/e2e/run", summary="执行端到端流程")
async def run_e2e_flow(device_id: str, flow_id: str = "", stages: str | None = None) -> dict:
    """设备发现→认证→流预览→校准完整流程 (P1.4)。"""
    import uuid
    from integration.constants import E2EStage

    fid = flow_id or f"e2e-{uuid.uuid4().hex[:8]}"

    parsed_stages = None
    if stages:
        try:
            parsed_stages = [E2EStage(s.strip()) for s in stages.split(",")]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"无效的阶段: {exc}")

    orchestrator = _get_device_orchestrator()
    result = await orchestrator.run_e2e_flow(
        flow_id=fid,
        device_id=device_id,
        stages=parsed_stages,
    )
    if result["success"]:
        return _ok_response(data=result["data"])
    return _error_response(ErrorCode.E2E_FLOW_FAILED, result["message"])


@router.get("/e2e/flows", summary="运行中的 E2E 流程")
async def list_running_flows() -> dict:
    """获取正在运行的端到端流程列表。"""
    orchestrator = _get_device_orchestrator()
    return _ok_response(data=orchestrator.get_running_flows())


# ================================================================== #
#  模块管理 (P0.2)
# ================================================================== #

@router.get("/modules", summary="已注册模块列表")
async def list_modules() -> dict:
    """获取所有已注册的子模块。"""
    orchestrator = _get_device_orchestrator()
    return _ok_response(data=orchestrator.list_modules())


# ================================================================== #
#  集成报告 (P4)
# ================================================================== #

@router.get("/report/error", summary="错误聚合报告")
async def get_error_report() -> dict:
    """获取错误聚合报告 (P4.1)。"""
    agg = _get_error_aggregator()
    return _ok_response(data=await agg.get_report())


@router.get("/report/tasks", summary="任务执行报告")
async def get_task_report(status: str | None = None) -> dict:
    """获取任务执行状态报告 (P4.1)。"""
    scheduler = _get_task_scheduler()
    from integration.core.task_scheduler import TaskStatus

    filter_status = None
    if status:
        try:
            filter_status = TaskStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效状态: {status}")

    tasks = await scheduler.list_tasks(status=filter_status)
    return _ok_response(data={"tasks": tasks, "total": len(tasks)})
