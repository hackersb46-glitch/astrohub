"""
M7 REST API v1.0 - FastAPI 路由定义

实现端点:
- P1: 设备 CRUD、状态、配置    - /devices/*
- P2: 流启动/停止、快照        - /streams/*
- P3: 校准启动/停止、进度      - /calibration/*
- P4: 观测数据、历史、统计      - /observations, /stats, /history
- P5: JWT 登录                 - /auth/*

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from rest_api.constants import (
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    ERROR_CODE_TO_HTTP,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from rest_api.core.request_validator import validate_mac, normalize_mac


# ------------------------------------------------------------------ #
#  路由器定义 (各独立模块, 便于单独挂载)
# ------------------------------------------------------------------ #

device_router = APIRouter(prefix="/devices", tags=["P1 设备管理"])
stream_router = APIRouter(prefix="/streams", tags=["P2 流控制"])
calibration_router = APIRouter(prefix="/calibration", tags=["P3 校准管理"])
data_router = APIRouter(tags=["P4 数据查询"])
auth_router = APIRouter(prefix="/auth", tags=["P5 认证"])


# ------------------------------------------------------------------ #
#  全局管理器实例延迟引用
# ------------------------------------------------------------------ #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) -> None:
    """注入管理器实例到路由层。

    Args:
        **kwargs: 各管理器实例 (如 device_manager=..., stream_manager=...)
    """
    _managers.update(kwargs)


def _get_device_manager() -> Any:
    mgr = _managers.get("device_manager")
    if mgr is None:
        raise HTTPException(
            status_code=500,
            detail=_error_payload(ErrorCode.INTERNAL_ERROR, "DeviceManager 未初始化"),
        )
    return mgr


def _get_stream_manager() -> Any:
    mgr = _managers.get("stream_manager")
    if mgr is None:
        raise HTTPException(
            status_code=500,
            detail=_error_payload(ErrorCode.INTERNAL_ERROR, "StreamManager 未初始化"),
        )
    return mgr


def _get_calibration_manager() -> Any:
    mgr = _managers.get("calibration_manager")
    if mgr is None:
        raise HTTPException(
            status_code=500,
            detail=_error_payload(ErrorCode.INTERNAL_ERROR, "CalibrationManager 未初始化"),
        )
    return mgr


def _get_observation_service() -> Any:
    mgr = _managers.get("observation_service")
    if mgr is None:
        raise HTTPException(
            status_code=500,
            detail=_error_payload(ErrorCode.INTERNAL_ERROR, "ObservationService 未初始化"),
        )
    return mgr


def _get_stats_service() -> Any:
    mgr = _managers.get("stats_service")
    if mgr is None:
        raise HTTPException(
            status_code=500,
            detail=_error_payload(ErrorCode.INTERNAL_ERROR, "StatsService 未初始化"),
        )
    return mgr


def _get_auth_service() -> Any:
    mgr = _managers.get("auth_service")
    if mgr is None:
        raise HTTPException(
            status_code=500,
            detail=_error_payload(ErrorCode.INTERNAL_ERROR, "AuthService 未初始化"),
        )
    return mgr


# ================================================================== #
#  P1: 设备管理 (P1.1-P1.7)
# ================================================================== #

@device_router.post("", summary="创建设备", status_code=201)
async def create_device(data: dict) -> dict:
    """创建设备 (P1.1)。

    请求体: mac, model, ip, port, ...
    成功返回 201 + 设备信息; MAC 重复返回 409。
    """
    mac_raw = data.get("mac", "")
    valid, err = validate_mac(mac_raw)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    mac = normalize_mac(mac_raw)
    result = _get_device_manager().create_device(mac=mac, **data)

    if not result.get("success"):
        error_text = result.get("error", "")
        if "exists" in error_text.lower() or "duplicate" in error_text.lower():
            raise HTTPException(
                status_code=409,
                detail=_error_payload(ErrorCode.DEVICE_ALREADY_EXISTS, error_text),
            )
        raise HTTPException(
            status_code=422,
            detail=_error_payload(ErrorCode.VALIDATION_ERROR, error_text),
        )
    return result


@device_router.get("", summary="查询设备列表")
async def list_devices(
    mac: str | None = Query(None, description="精确匹配 MAC"),
    model: str | None = Query(None, description="模糊匹配型号"),
    status: str | None = Query(None, description="精确匹配状态 (active/inactive)"),
    page: int = Query(DEFAULT_PAGE, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页数量"),
) -> dict:
    """查询设备列表, 支持分页与过滤 (P1.2)。"""
    return _get_device_manager().list_devices(
        mac=mac,
        model=model,
        status_filter=status,
        page=page,
        page_size=page_size,
    )


@device_router.get("/{mac}", summary="获取单个设备")
async def get_device(mac: str) -> dict:
    """获取单个设备详情 (P1.3)。"""
    valid, err = validate_mac(mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    device = _get_device_manager().get_device(normalize_mac(mac))
    if device is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.DEVICE_NOT_FOUND, f"设备不存在: {mac}"),
        )
    return device


@device_router.put("/{mac}", summary="更新设备")
async def update_device(mac: str, data: dict) -> dict:
    """更新设备信息 (P1.4)。"""
    valid, err = validate_mac(mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    result = _get_device_manager().update_device(normalize_mac(mac), data)
    if not result.get("success"):
        raise HTTPException(
            status_code=400 if result.get("not_found") else 422,
            detail=_error_payload(
                ErrorCode.DEVICE_NOT_FOUND if result.get("not_found") else ErrorCode.VALIDATION_ERROR,
                result.get("error", ""),
            ),
        )
    return result


@device_router.delete("/{mac}", summary="删除设备", status_code=204)
async def delete_device(mac: str) -> Response:
    """删除设备 (P1.5)。在线设备删除返回 409。"""
    valid, err = validate_mac(mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    result = _get_device_manager().delete_device(normalize_mac(mac))
    if not result.get("success"):
        error_text = result.get("error", "")
        if "online" in error_text.lower():
            raise HTTPException(
                status_code=409,
                detail=_error_payload(ErrorCode.DEVICE_ONLINE_CANNOT_DELETE, error_text),
            )
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.DEVICE_NOT_FOUND, error_text),
        )
    return Response(status_code=204)


@device_router.get("/{mac}/status", summary="查询设备状态")
async def get_device_status(mac: str) -> dict:
    """查询设备在线/离线状态及最后心跳时间 (P1.6)。"""
    valid, err = validate_mac(mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    mgr = _get_device_manager()
    if hasattr(mgr, "get_device_status"):
        status_info = mgr.get_device_status(normalize_mac(mac))
    else:
        device = mgr.get_device(normalize_mac(mac))
        if device is None:
            raise HTTPException(
                status_code=404,
                detail=_error_payload(ErrorCode.DEVICE_NOT_FOUND, f"设备不存在: {mac}"),
            )
        status_info = {
            "mac": normalize_mac(mac),
            "status": device.get("status", "unknown"),
            "last_heartbeat": device.get("last_heartbeat"),
        }
    return status_info


@device_router.get("/{mac}/config", summary="读取设备配置")
async def get_device_config(mac: str) -> dict:
    """读取设备完整配置 (P1.7 - GET)。"""
    valid, err = validate_mac(mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    device = _get_device_manager().get_device(normalize_mac(mac))
    if device is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.DEVICE_NOT_FOUND, f"设备不存在: {mac}"),
        )
    return {
        "mac": normalize_mac(mac),
        "config": device.get("config", device),
    }


@device_router.put("/{mac}/config", summary="写入设备配置")
async def update_device_config(mac: str, data: dict) -> dict:
    """写入设备配置 (P1.7 - PUT)。"""
    valid, err = validate_mac(mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    device = _get_device_manager().get_device(normalize_mac(mac))
    if device is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.DEVICE_NOT_FOUND, f"设备不存在: {mac}"),
        )

    # 更新配置并确认
    updated = _get_device_manager().update_device(normalize_mac(mac), {"config": data})
    if not updated.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_payload(ErrorCode.VALIDATION_ERROR, updated.get("error", "")),
        )
    return updated


# ================================================================== #
#  P1 补充: 设备历史 (P4.2)
# ================================================================== #

@device_router.get("/{mac}/history", summary="查询设备历史")
async def get_device_history(
    mac: str,
    start_time: str | None = Query(None, description="开始时间 (ISO 8601)"),
    end_time: str | None = Query(None, description="结束时间 (ISO 8601)"),
    event_type: str | None = Query(None, description="事件类型过滤"),
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict:
    """查询设备状态变化历史和配置变更历史 (P4.2)。"""
    valid, err = validate_mac(mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    return _get_device_manager().get_history(
        mac=normalize_mac(mac),
        start_time=start_time,
        end_time=end_time,
        event_type=event_type,
        page=page,
        page_size=page_size,
    )


# ================================================================== #
#  P2: 流控制 (P2.1-P2.4)
# ================================================================== #

@stream_router.post("/{device_mac}/start", summary="启动视频流")
async def start_stream(device_mac: str) -> dict:
    """启动指定设备的视频流 (P2.1)。

    设备离线返回 409; 流已启动返回 409。
    """
    valid, err = validate_mac(device_mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    result = _get_stream_manager().start_stream(normalize_mac(device_mac))
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.STREAM_NOT_FOUND, "流不存在"),
        )
    if not result.get("success"):
        error_text = result.get("error", "")
        if "offline" in error_text.lower() or "not found" in error_text.lower() and "device" in error_text.lower():
            raise HTTPException(
                status_code=409,
                detail=_error_payload(ErrorCode.DEVICE_OFFLINE, error_text),
            )
        if "active" in error_text.lower() or "running" in error_text.lower():
            raise HTTPException(
                status_code=409,
                detail=_error_payload(ErrorCode.STREAM_ALREADY_ACTIVE, error_text),
            )
        raise HTTPException(
            status_code=400,
            detail=_error_payload(ErrorCode.VALIDATION_ERROR, error_text),
        )
    return result


@stream_router.post("/{device_mac}/stop", summary="停止视频流")
async def stop_stream(device_mac: str) -> dict:
    """停止指定设备的视频流 (P2.2)。"""
    valid, err = validate_mac(device_mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    result = _get_stream_manager().stop_stream(normalize_mac(device_mac))
    if result is None or result.get("not_found"):
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.STREAM_NOT_FOUND, "流未启动"),
        )
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_payload(ErrorCode.STREAM_ERROR, result.get("error", "")),
        )
    return result


@stream_router.get("/{device_mac}", summary="查询流状态")
async def get_stream_status(device_mac: str) -> dict:
    """查询视频流当前状态和元数据 (P2.3)。

    返回状态: active / stopped / error
    包含码率、分辨率、帧率信息。
    """
    valid, err = validate_mac(device_mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    status_info = _get_stream_manager().get_stream_status(normalize_mac(device_mac))
    if status_info is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.STREAM_NOT_FOUND, f"流不存在: {device_mac}"),
        )
    return status_info


@stream_router.post("/{device_mac}/snapshot", summary="截取视频帧")
async def take_snapshot(device_mac: str) -> dict:
    """从当前流中截取一帧画面 (P2.4)。响应时间 <2秒。"""
    valid, err = validate_mac(device_mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    result = _get_stream_manager().take_snapshot(normalize_mac(device_mac))
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.STREAM_NOT_FOUND, "流不存在, 无法截图"),
        )
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=_error_payload(ErrorCode.STREAM_ERROR, result.get("error", "")),
        )
    return result


# ================================================================== #
#  P3: 校准管理 (P3.1-P3.4)
# ================================================================== #

@calibration_router.post("/{device_mac}/{calibration_type}", summary="启动校准")
async def start_calibration(device_mac: str, calibration_type: str) -> dict:
    """启动指定类型的校准流程 (P3.1)。

    设备离线返回 409; 校准进行中返回 409。
    """
    valid, err = validate_mac(device_mac)
    if not valid:
        raise HTTPException(status_code=422, detail=err)  # type: ignore[arg-type]

    result = _get_calibration_manager().start_calibration(
        mac=normalize_mac(device_mac),
        calibration_type=calibration_type,
    )
    if not result.get("success"):
        error_text = result.get("error", "")
        if "offline" in error_text.lower():
            raise HTTPException(
                status_code=409,
                detail=_error_payload(ErrorCode.DEVICE_OFFLINE, error_text),
            )
        if "progress" in error_text.lower() or "running" in error_text.lower():
            raise HTTPException(
                status_code=409,
                detail=_error_payload(ErrorCode.CALIBRATION_IN_PROGRESS, error_text),
            )
        raise HTTPException(
            status_code=400,
            detail=_error_payload(ErrorCode.VALIDATION_ERROR, error_text),
        )
    return result


@calibration_router.post("/{id}/stop", summary="停止校准")
async def stop_calibration(id: str) -> dict:
    """停止正在进行的校准, 回滚已修改参数 (P3.2)。

    校准已完成返回 404。
    """
    result = _get_calibration_manager().stop_calibration(id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.CALIBRATION_ALREADY_COMPLETED, "校准已完成或不存在"),
        )
    return result


@calibration_router.get("/{id}", summary="查询校准进度")
async def get_calibration_progress(id: str) -> dict:
    """查询校准当前步骤和状态 (P3.3)。

    返回: 当前步骤/总步骤/状态, 实时更新。
    """
    progress = _get_calibration_manager().get_calibration_progress(id)
    if progress is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.CALIBRATION_NOT_FOUND, f"校准任务不存在: {id}"),
        )
    return progress


@calibration_router.get("/{id}/result", summary="获取校准结果")
async def get_calibration_result(id: str) -> dict:
    """获取校准完成后的结果报告 (P3.4)。"""
    result = _get_calibration_manager().get_calibration_result(id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(ErrorCode.CALIBRATION_NOT_FOUND, f"校准结果不存在: {id}"),
        )
    return result


# ================================================================== #
#  P4: 数据查询 (P4.1-P4.3)
# ================================================================== #

@data_router.get("/observations", summary="查询观测数据")
async def list_observations(
    device_mac: str | None = Query(None, description="设备 MAC 地址"),
    start_time: str | None = Query(None, description="开始时间 (ISO 8601)"),
    end_time: str | None = Query(None, description="结束时间 (ISO 8601)"),
    observation_type: str | None = Query(None, description="观测类型"),
    page: int = Query(DEFAULT_PAGE, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict:
    """查询观测数据, 支持时间范围/设备/类型过滤, 分页 (P4.1)。"""
    return _get_observation_service().list_observations(
        device_mac=device_mac,
        start_time=start_time,
        end_time=end_time,
        observation_type=observation_type,
        page=page,
        page_size=page_size,
    )


@data_router.get("/stats", summary="获取统计信息")
async def get_stats() -> dict:
    """获取聚合统计信息 (P4.3)。

    返回设备总数/在线数/流状态等统计。
    响应时间 <100ms。
    """
    return _get_stats_service().get_stats()


# ================================================================== #
#  P5: 认证 (P5.1)
# ================================================================== #

@auth_router.post("/login", summary="用户登录")
async def login(data: dict) -> dict:
    """用户登录, 返回 JWT tokens。

    请求体: {"username": "...", "password": "..."}
    成功返回: {access_token, refresh_token, token_type, role}
    凭证无效返回: 401
    """
    username = data.get("username", "")
    password = data.get("password", "")

    if not username or not password:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                ErrorCode.VALIDATION_ERROR,
                "username 和 password 不能为空",
            ),
        )

    return _get_auth_service().authenticate(username=username, password=password)


@auth_router.post("/refresh", summary="刷新 Token")
async def refresh_token(data: dict) -> dict:
    """使用 refresh_token 获取新的 access_token。"""
    refresh_tk = data.get("refresh_token", "")
    if not refresh_tk:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(ErrorCode.VALIDATION_ERROR, "refresh_token 不能为空"),
        )

    from rest_api.core.auth import get_jwt_manager
    jwt_mgr = get_jwt_manager()
    try:
        payload = jwt_mgr.verify_token(refresh_tk)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=401,
                detail=_error_payload(ErrorCode.INVALID_TOKEN, "无效的 refresh token"),
            )
        subject = payload.get("sub", "")
        role = payload.get("role", "viewer")
        return {
            "access_token": jwt_mgr.create_access_token(subject=subject, role=role),
            "token_type": "bearer",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail=_error_payload(ErrorCode.INVALID_TOKEN, "Token 验证失败"),
        )


# ================================================================== #
#  统一错误响应 (P6.1)
# ================================================================== #

def _error_payload(code: ErrorCode, message: str, details: Any = None) -> dict:
    """构造符合 P6.1 标准的统一错误响应格式。

    格式: {"code": "...", "message": "...", "details": ...}
    """
    payload = {
        "code": code.value,
        "message": message or ERROR_CODE_DESCRIPTION.get(code, "未知错误"),
    }
    if details is not None:
        payload["details"] = details
    return payload
