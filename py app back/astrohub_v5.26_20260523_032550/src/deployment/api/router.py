"""
M11 Deployment v1.0 - FastAPI 路由

部署、健康、配置、回滚、日志端点。

- P0: 部署 (docker-compose up/down)
- P2: 服务启停、健康检查
- P3: 备份/恢复
- P4: 监控/日志

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from deployment.constants import (
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
)


# ------------------------------------------------------------------ #
#  路由器
# ------------------------------------------------------------------ #

router = APIRouter(prefix="/api/v1/deploy", tags=["M11 部署管理"])
health_router = APIRouter(prefix="/health", tags=["M11 健康检查"])


# ------------------------------------------------------------------ #
#  全局管理器实例延迟引用
# ------------------------------------------------------------------ #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) -> None:
    """注入管理器实例。"""
    _managers.update(kwargs)


def _get_docker_builder() -> Any:
    mgr = _managers.get("docker_builder")
    if mgr is None:
        raise HTTPException(
            status_code=500,
            detail=_error_payload(ErrorCode.INTERNAL_ERROR, "DockerBuilder 未初始化"),
        )
    return mgr


def _get_service_manager() -> Any:
    mgr = _managers.get("service_manager")
    if mgr is None:
        from deployment.core.service_manager import ServiceManager
        mgr = ServiceManager()
        _managers["service_manager"] = mgr
    return mgr


def _get_health_monitor() -> Any:
    mgr = _managers.get("health_monitor")
    if mgr is None:
        from deployment.core.health_monitor import HealthMonitor
        mgr = HealthMonitor()
        _managers["health_monitor"] = mgr
    return mgr


def _get_rollback_manager() -> Any:
    mgr = _managers.get("rollback_manager")
    if mgr is None:
        from deployment.core.rollback import RollbackManager
        mgr = RollbackManager()
        _managers["rollback_manager"] = mgr
    return mgr


def _get_log_collector() -> Any:
    mgr = _managers.get("log_collector")
    if mgr is None:
        from deployment.core.log_collector import LogCollector
        mgr = LogCollector.instance()
        _managers["log_collector"] = mgr
    return mgr


def _get_deployment_config() -> Any:
    from deployment.core.deployment_config import EnvironmentConfig, ConfigValidator
    return EnvironmentConfig(), ConfigValidator()


# ================================================================== #
#  P0: 部署管理
# ================================================================== #

@router.post("/build", summary="构建 Docker 镜像")
async def build_docker_image(data: dict) -> dict:
    """构建 Docker 镜像 (P0.1)。

    请求体: {"image_name": "...", "tag": "latest", "target": "..."}
    """
    image_name = data.get("image_name", "")
    tag = data.get("tag", "latest")
    target = data.get("target")

    if not image_name:
        raise HTTPException(status_code=422, detail=_error_payload(
            ErrorCode.VALIDATION_ERROR, "image_name 不能为空"
        ))

    from deployment.core.docker_builder import DockerBuildError

    try:
        builder = _get_docker_builder()
        result = builder.build(image_name=image_name, tag=tag, target=target)
        return {"success": True, "image": result, "tag": tag}
    except DockerBuildError as e:
        raise HTTPException(status_code=500, detail=_error_payload(e.code, e.message))


@router.post("/compose/up", summary="启动所有服务 (docker-compose up)")
async def compose_up(data: dict | None = None) -> dict:
    """启动所有服务 (P0.3)。"""
    from deployment.core.docker_builder import DockerBuildError, DockerBuilder
    from pathlib import Path

    compose_file = Path(data.get("compose_file", "docker-compose.yml")) if data else Path("docker-compose.yml")

    try:
        builder = _get_docker_builder()
        output = builder.compose_up(compose_file=compose_file)
        return {"success": True, "output": output}
    except DockerBuildError as e:
        raise HTTPException(status_code=500, detail=_error_payload(e.code, e.message))


@router.post("/down", summary="停止所有服务 (docker-compose down)")
async def compose_down(data: dict | None = None) -> dict:
    """停止所有服务 (P2.1)。"""
    from pathlib import Path

    compose_file = Path(data.get("compose_file", "docker-compose.yml")) if data else Path("docker-compose.yml")

    from deployment.core.docker_builder import DockerBuildError

    try:
        builder = _get_docker_builder()
        output = builder.compose_down(compose_file=compose_file)
        return {"success": True, "output": output}
    except DockerBuildError as e:
        raise HTTPException(status_code=500, detail=_error_payload(e.code, e.message))


# ================================================================== #
#  P2: 服务管理
# ================================================================== #

@router.post("/service/start", summary="启动服务")
async def start_service(data: dict) -> dict:
    """启动指定服务 (P2.1)。

    请求体: {"service_name": "...", "command": "..."}
    """
    from deployment.core.service_manager import ServiceMgr

    svc_name = data.get("service_name", "")
    cmd = data.get("command")

    mgr = _get_service_manager()
    mgr.service_name = svc_name
    try:
        ok = mgr.start(command=cmd)
        return {"success": ok, "service": svc_name, "status": mgr.status.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_payload(ErrorCode.SERVICE_START_FAILED, str(e)))


@router.post("/service/stop", summary="停止服务")
async def stop_service(data: dict) -> dict:
    """停止指定服务 (P2.1)。"""
    from deployment.core.service_manager import ServiceError

    svc_name = data.get("service_name", "")
    cmd = data.get("command")

    mgr = _get_service_manager()
    try:
        ok = mgr.stop(command=cmd)
        return {"success": ok, "service": svc_name, "status": mgr.status.value}
    except ServiceError as e:
        raise HTTPException(status_code=500, detail=_error_payload(e.code, e.message))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_payload(ErrorCode.SERVICE_STOP_FAILED, str(e)))


@router.get("/service/status", summary="查询服务状态")
async def get_service_status(service_name: str = Query("astro-hub", description="服务名")) -> dict:
    """查询服务当前状态 (P2.2)。"""
    mgr = _get_service_manager()
    return mgr.get_status()


# ================================================================== #
#  P2.2: 健康检查
# ================================================================== #

@health_router.get("", summary="全局健康检查")
async def global_health() -> dict:
    """全局健康检查端点。

    返回所有已注册服务的健康状态摘要。
    """
    monitor = _get_health_monitor()
    return monitor.get_summary()


@health_router.get("/detailed", summary="详细健康检查")
async def detailed_health() -> dict:
    """执行所有服务健康检查并返回详情。"""
    monitor = _get_health_monitor()
    results = monitor.check_all()
    return {
        "results": [r.to_dict() for r in results],
    }


@router.post("/health/register", summary="注册服务健康检查")
async def register_health_check(data: dict) -> dict:
    """注册服务健康检查端点。

    请求体: {"name": "...", "url": "..."}
    """
    name = data.get("name", "")
    url = data.get("url", "")

    if not name or not url:
        raise HTTPException(status_code=422, detail=_error_payload(
            ErrorCode.VALIDATION_ERROR, "name 和 url 不能为空"
        ))

    monitor = _get_health_monitor()
    monitor.register_service(name=name, url=url)
    return {"success": True, "registered": name}


# ================================================================== #
#  P3: 回滚管理
# ================================================================== #

@router.post("/snapshot", summary="创建部署快照")
async def create_snapshot(data: dict) -> dict:
    """创建当前部署状态快照 (P3 前置)。

    请求体: {"version": "...", "compose_file": "..."}
    """
    version = data.get("version", "")
    compose_file = data.get("compose_file")

    if not version:
        raise HTTPException(status_code=422, detail=_error_payload(
            ErrorCode.VALIDATION_ERROR, "version 不能为空"
        ))

    from pathlib import Path

    rm = _get_rollback_manager()
    snap_id = rm.snapshot(version=version, compose_file=Path(compose_file) if compose_file else None)
    return {"success": True, "snapshot_id": snap_id, "version": version}


@router.post("/rollback", summary="回滚到指定版本")
async def rollback(data: dict) -> dict:
    """执行回滚。

    请求体: {"version": "..."} 或 {} = 回退到上一版本
    """
    from deployment.core.rollback import RollbackError

    version = data.get("version")

    rm = _get_rollback_manager()
    try:
        result = rm.rollback(version=version)
        return result
    except RollbackError as e:
        raise HTTPException(status_code=500, detail=_error_payload(e.code, e.message))


@router.get("/versions", summary="查询可用版本")
async def list_versions() -> dict:
    """查询所有可回滚的版本。"""
    rm = _get_rollback_manager()
    return {"versions": rm.available_versions}


# ================================================================== #
#  P4: 监控与日志
# ================================================================== #

@router.get("/logs", summary="查询部署日志")
async def get_logs(
    service: str | None = Query(None, description="服务名过滤"),
    level: str | None = Query(None, description="级别过滤 (info, warning, error)"),
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
) -> dict:
    """查询日志 (P2.3)。"""
    collector = _get_log_collector()
    offset = (page - 1) * page_size
    entries = collector.query(service=service, level=level, limit=page_size, offset=offset)

    return {
        "total": collector.count(service=service, level=level),
        "page": page,
        "page_size": page_size,
        "logs": [e.to_dict() for e in entries],
    }


@router.get("/logs/stats", summary="日志统计")
async def log_stats() -> dict:
    """获取日志统计摘要。"""
    collector = _get_log_collector()
    return collector.get_stats()


@router.get("/monitor/system", summary="系统监控指标")
async def system_monitor() -> dict:
    """获取当前系统资源指标 (CPU/内存/磁盘)。"""
    from deployment.core.health_monitor import SystemMonitor
    sm = SystemMonitor()
    return sm.collect_metrics()


# ================================================================== #
#  P1: 配置管理
# ================================================================== #

@router.get("/config/env", summary="获取环境配置")
async def get_env_config() -> dict:
    """获取当前环境配置 (P1.1)。"""
    from deployment.core.deployment_config import EnvironmentConfig

    env_cfg = EnvironmentConfig()
    try:
        config = env_cfg.load()
        return {
            "environment": env_cfg.environment,
            "config": {k: "***" if "SECRET" in k or "PASSWORD" in k else v for k, v in config.items()},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=_error_payload(ErrorCode.CONFIG_NOT_FOUND, str(e)))


@router.post("/config/validate", summary="校验配置")
async def validate_config(data: dict) -> dict:
    """校验配置完整性 (P1.3)。

    请求体: 配置字典，缺失必需配置时返回错误
    """
    from deployment.core.deployment_config import ConfigValidationError, ConfigValidator

    validator = ConfigValidator()
    try:
        validator.validate_or_raise(data)
        return {"valid": True, "message": "配置校验通过"}
    except ConfigValidationError as e:
        return {"valid": False, "error": e.message, "code": e.code.value}


# ================================================================== #
#  统一错误响应
# ================================================================== #

def _error_payload(code: ErrorCode, message: str, details: Any = None) -> dict:
    """构造统一错误响应格式。

    格式: {"code": "...", "message": "...", "details": ...}
    """
    payload = {
        "code": code.value,
        "message": message or ERROR_CODE_DESCRIPTION.get(code, "未知错误"),
    }
    if details is not None:
        payload["details"] = details
    return payload
