"""
Database Service v1.0 - FastAPI 路由层

设备 CRUD 路由、分组管理路由、观测数据路由、操作日志路由、配置版本路由。
使用 DeviceRepository, GroupRepository, ConfigStore, OperationLogRepo 等。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from src.database.core.db_manager import (
    DatabaseManager,
    Device,
    ConfigSnapshot,
    Group,
    OperationLog,
)
from src.database.core.device_repo import DeviceRepository, normalize_mac
from src.database.core.group_repo import GroupRepository
from src.database.core.config_store import ConfigStore
from src.database.core.operation_log import OperationLogRepo
from src.database.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

router = APIRouter(prefix="/api/v1", tags=["M5 Database"])


# ------------------------------------------------------------------ #
#  Dependency 注入
# ------------------------------------------------------------------ #

async def get_device_repo() -> DeviceRepository:
    """获取 DeviceRepository 实例。"""
    session_factory = DatabaseManager.get_session_factory()
    async with session_factory() as session:
        yield DeviceRepository(session)


async def get_group_repo() -> GroupRepository:
    """获取 GroupRepository 实例。"""
    session_factory = DatabaseManager.get_session_factory()
    async with session_factory() as session:
        yield GroupRepository(session)


async def get_config_store() -> ConfigStore:
    """获取 ConfigStore 实例。"""
    session_factory = DatabaseManager.get_session_factory()
    async with session_factory() as session:
        yield ConfigStore(session)


async def get_operation_log_repo() -> OperationLogRepo:
    """获取 OperationLogRepo 实例。"""
    session_factory = DatabaseManager.get_session_factory()
    async with session_factory() as session:
        yield OperationLogRepo(session)


# ------------------------------------------------------------------ #
#  设备 CRUD 路由 (P1)
# ------------------------------------------------------------------ #

@router.post("/devices", summary="创建设备(P1.1)")
async def create_device(data: Dict[str, Any]) -> dict:
    """创建设备记录。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            device = await repo.create_device(data)
            await session.commit()
            return {"status": "success", "data": device.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.get("/devices/{mac}", summary="查询设备(按MAC)(P1.2)")
async def get_device(mac: str) -> dict:
    """按 MAC 精确查询设备。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            device = await repo.get_device_by_mac(mac)
            if device is None:
                raise HTTPException(status_code=404, detail=f"设备不存在: {mac}")
            return {"status": "success", "data": device.to_dict()}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.get("/devices", summary="分页查询设备列表")
async def list_devices(
    status: Optional[str] = Query(None, description="按状态筛选"),
    group_id: Optional[int] = Query(None, description="按分组筛选"),
    search: Optional[str] = Query(None, description="模糊搜索 MAC/IP/Model"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> dict:
    """分页查询设备列表，支持状态/分组/模糊搜索过滤。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            devices, total = await repo.list_devices(
                status=status,
                group_id=group_id,
                search=search,
                page=page,
                page_size=page_size,
            )
            return {
                "status": "success",
                "total": total,
                "page": page,
                "page_size": page_size,
                "data": [d.to_dict() for d in devices],
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.put("/devices/{mac}", summary="更新设备(P1.3)")
async def update_device(mac: str, data: Dict[str, Any]) -> dict:
    """更新设备信息。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            device = await repo.update_device(mac, data)
            await session.commit()
            return {"status": "success", "data": device.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.delete("/devices/{mac}", summary="删除设备(P1.4)")
async def delete_device(mac: str) -> dict:
    """删除设备记录及关联数据。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            await repo.delete_device(mac)
            await session.commit()
            return {"status": "success", "message": f"设备已删除: {mac}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ------------------------------------------------------------------ #
#  状态历史路由 (P1.5)
# ------------------------------------------------------------------ #

@router.get("/devices/{mac}/status-history", summary="查询设备状态历史(P1.5)")
async def get_status_history(
    mac: str,
    start_time: Optional[str] = Query(None, description="起始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数上限"),
) -> dict:
    """查询设备状态变更历史。"""
    try:
        mac = normalize_mac(mac)
        st = datetime.fromisoformat(start_time) if start_time else None
        et = datetime.fromisoformat(end_time) if end_time else None

        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            history = await repo.get_status_history(mac, start_time=st, end_time=et, limit=limit)
            return {
                "status": "success",
                "data": [h.to_dict() for h in history],
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ------------------------------------------------------------------ #
#  配置快照路由 (P1.6)
# ------------------------------------------------------------------ #

@router.post("/devices/{mac}/config-snapshots", summary="保存配置快照(P1.6)")
async def save_config_snapshot(mac: str, data: Dict[str, Any]) -> dict:
    """保存设备配置快照。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            snapshot = await repo.save_config_snapshot(mac, data)
            await session.commit()
            return {"status": "success", "data": snapshot.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.get("/devices/{mac}/config-snapshots/latest", summary="获取最新配置快照")
async def get_latest_config_snapshot(mac: str) -> dict:
    """获取设备最新配置快照。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = DeviceRepository(session)
            snapshot = await repo.get_config_snapshot(mac)
            if snapshot is None:
                return {"status": "success", "data": None}
            return {"status": "success", "data": snapshot.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ------------------------------------------------------------------ #
#  分组管理路由
# ------------------------------------------------------------------ #

@router.post("/groups", summary="创建分组")
async def create_group(name: str, description: Optional[str] = None) -> dict:
    """创建分组。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = GroupRepository(session)
            group = await repo.create_group(name, description)
            await session.commit()
            return {"status": "success", "data": group.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.get("/groups", summary="分页查询分组列表")
async def list_groups(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> dict:
    """分页查询分组列表。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = GroupRepository(session)
            groups, total = await repo.list_groups(page=page, page_size=page_size)
            return {
                "status": "success",
                "total": total,
                "page": page,
                "page_size": page_size,
                "data": [g.to_dict() for g in groups],
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.put("/groups/{group_id}", summary="更新分组")
async def update_group(group_id: int, name: Optional[str] = None, description: Optional[str] = None) -> dict:
    """更新分组信息。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = GroupRepository(session)
            group = await repo.update_group(group_id, name=name, description=description)
            await session.commit()
            return {"status": "success", "data": group.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.delete("/groups/{group_id}", summary="删除分组")
async def delete_group(group_id: int) -> dict:
    """删除分组。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = GroupRepository(session)
            ok = await repo.delete_group(group_id)
            if not ok:
                raise HTTPException(status_code=404, detail=f"分组不存在: {group_id}")
            await session.commit()
            return {"status": "success", "message": f"分组已删除: {group_id}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.get("/groups/{group_id}/devices", summary="查询分组下设备")
async def get_group_devices(group_id: int) -> dict:
    """获取分组下的所有设备。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = GroupRepository(session)
            devices = await repo.get_group_devices(group_id)
            return {
                "status": "success",
                "data": [d.to_dict() for d in devices],
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.put("/groups/{group_id}/devices/{mac}", summary="添加设备到分组")
async def add_device_to_group(group_id: int, mac: str) -> dict:
    """将设备添加到分组。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = GroupRepository(session)
            device = await repo.add_device_to_group(mac, group_id)
            await session.commit()
            return {"status": "success", "data": device.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.delete("/devices/{mac}/group", summary="移除设备分组")
async def remove_device_from_group(mac: str) -> dict:
    """将设备从分组中移除。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = GroupRepository(session)
            device = await repo.remove_device_from_group(mac)
            await session.commit()
            return {"status": "success", "data": device.to_dict()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ------------------------------------------------------------------ #
#  操作日志路由
# ------------------------------------------------------------------ #

@router.post("/operation-logs", summary="记录操作日志")
async def create_operation_log(
    operation: str,
    status: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[str] = None,
    operator: Optional[str] = None,
) -> dict:
    """记录操作日志。"""
    try:
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = OperationLogRepo(session)
            log_entry = await repo.log_operation(
                operation=operation,
                status=status,
                target_type=target_type,
                target_id=target_id,
                details=details,
                operator=operator,
            )
            await session.commit()
            return {"status": "success", "data": log_entry.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


@router.get("/operation-logs", summary="查询操作日志")
async def query_operation_logs(
    operation: Optional[str] = Query(None, description="按操作名称筛选"),
    target_type: Optional[str] = Query(None, description="按目标类型筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    start_time: Optional[str] = Query(None, description="起始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO 格式"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> dict:
    """分页查询操作日志。"""
    try:
        st = datetime.fromisoformat(start_time) if start_time else None
        et = datetime.fromisoformat(end_time) if end_time else None

        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            repo = OperationLogRepo(session)
            logs, total = await repo.query_logs(
                operation=operation,
                target_type=target_type,
                status=status,
                start_time=st,
                end_time=et,
                page=page,
                page_size=page_size,
            )
            return {
                "status": "success",
                "total": total,
                "page": page,
                "page_size": page_size,
                "data": [log.to_dict() for log in logs],
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")


# ------------------------------------------------------------------ #
#  配置版本管理路由
# ------------------------------------------------------------------ #

@router.get("/devices/{mac}/config-versions", summary="查询配置版本历史")
async def get_config_versions(
    mac: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, description="每页条数"),
) -> dict:
    """分页查询配置版本历史。"""
    try:
        mac = normalize_mac(mac)
        session_factory = DatabaseManager.get_session_factory()
        async with session_factory() as session:
            store = ConfigStore(session)
            snapshots, total = await store.get_config_history(mac, page=page, page_size=page_size)
            return {
                "status": "success",
                "total": total,
                "page": page,
                "page_size": page_size,
                "data": [s.to_dict() for s in snapshots],
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")
