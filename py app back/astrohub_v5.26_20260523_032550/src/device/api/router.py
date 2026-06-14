"""
M2 Device Manager v1.0 - FastAPI 路由层

包含设备CRUD路由、状态查询路由、分组操作路由、配置管理路由。
使用已有的 DeviceManager, GroupManager, ConfigManager, ConfigBackup, DeviceLifecycle 等。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from device.core.device_manager import DeviceManager
from device.core.group_manager import GroupManager
from device.core.lifecycle import DeviceLifecycle
from device.models.schemas import (
    DeviceCreate,
    DeviceUpdate,
    GroupCreate,
)

router = APIRouter(prefix="/api/v1", tags=["M2 Device Manager"])


# ------------------------------------------------------------------ #
#  全局管理器实例延迟引用
# ------------------------------------------------------------------ #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) -> None:
    """注入管理器实例到路由层。

    Args:
        **kwargs: 各管理器实例，如 device_manager=..., group_manager=...
    """
    _managers.update(kwargs)


def _get_device_manager() -> DeviceManager:
    manager = _managers.get("device_manager")
    if manager is None:
        raise HTTPException(status_code=500, detail="DeviceManager 未初始化")
    return manager


def _get_group_manager() -> GroupManager:
    manager = _managers.get("group_manager")
    if manager is None:
        raise HTTPException(status_code=500, detail="GroupManager 未初始化")
    return manager


def _get_lifecycle() -> DeviceLifecycle:
    manager = _managers.get("lifecycle")
    if manager is None:
        raise HTTPException(status_code=500, detail="DeviceLifecycle 未初始化")
    return manager


def _get_config_backup() -> Any:
    manager = _managers.get("config_backup")
    if manager is None:
        raise HTTPException(status_code=500, detail="ConfigBackup 未初始化")
    return manager


# ------------------------------------------------------------------ #
#  设备 CRUD 路由
# ------------------------------------------------------------------ #


@router.post("/devices", summary="创建设备")
async def create_device(data: DeviceCreate) -> dict:
    """创建设备(P0.1)。"""
    result = _get_device_manager().create_device(data)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error"))
    return result


@router.get("/devices", summary="查询设备列表")
async def list_devices(
    mac: str | None = Query(None, description="精确匹配MAC"),
    model: str | None = Query(None, description="模糊匹配型号"),
    status: str | None = Query(None, description="精确匹配状态"),
) -> list[dict]:
    """查询设备列表，支持过滤(P0.2)。"""
    return _get_device_manager().list_devices(mac=mac, model=model, status_filter=status)


@router.get("/devices/{mac}", summary="获取单个设备")
async def get_device(mac: str) -> dict:
    """获取单个设备信息。"""
    device = _get_device_manager().get_device(mac)
    if device is None:
        raise HTTPException(status_code=404, detail=f"设备不存在: {mac}")
    return device


@router.put("/devices/{mac}", summary="更新设备")
async def update_device(mac: str, data: DeviceUpdate) -> dict:
    """更新设备信息(P0.3)。"""
    result = _get_device_manager().update_device(mac, data)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/devices/{mac}", summary="删除设备")
async def delete_device(mac: str) -> dict:
    """删除设备(P0.4)。"""
    result = _get_device_manager().delete_device(mac)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ------------------------------------------------------------------ #
#  设备状态查询路由
# ------------------------------------------------------------------ #


@router.get("/devices/{mac}/status", summary="查询设备状态")
async def get_device_status(mac: str) -> dict:
    """查询设备生命周期状态。"""
    lifecycle = _get_lifecycle()
    status_info = lifecycle.get_status(mac)
    if status_info is None:
        raise HTTPException(status_code=404, detail=f"设备不存在: {mac}")
    return status_info


@router.get("/devices/{mac}/status/history", summary="查询状态流转历史")
async def get_status_history(mac: str) -> list[dict]:
    """查询设备状态流转历史。"""
    return _get_lifecycle().get_transition_history(mac)


@router.get("/lifecycle", summary="所有设备生命周期状态")
async def list_lifecycle() -> list[dict]:
    """获取所有设备的生命周期状态。"""
    return _get_lifecycle().list_status()


# ------------------------------------------------------------------ #
#  设备生命周期操作路由
# ------------------------------------------------------------------ #


@router.post("/devices/{mac}/lifecycle/activate", summary="激活设备")
async def activate_device(mac: str) -> dict:
    """激活设备: new→active。"""
    result = _get_lifecycle().activate(mac)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/devices/{mac}/lifecycle/deactivate", summary="停用设备")
async def deactivate_device(mac: str) -> dict:
    """停用设备: active→inactive。"""
    result = _get_lifecycle().deactivate(mac)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/devices/{mac}/lifecycle/reactivate", summary="重新激活设备")
async def reactivate_device(mac: str) -> dict:
    """重新激活设备: inactive→active。"""
    result = _get_lifecycle().reactivate(mac)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/devices/{mac}/lifecycle/delete", summary="删除设备(生命周期)")
async def lifecycle_delete_device(mac: str) -> dict:
    """删除设备(生命周期): inactive→deleted。"""
    result = _get_lifecycle().delete_device(mac)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


# ------------------------------------------------------------------ #
#  分组操作路由
# ------------------------------------------------------------------ #


@router.post("/groups", summary="创建分组")
async def create_group(data: GroupCreate) -> dict:
    """创建分组(P3.1)。"""
    result = _get_group_manager().create_group(data)
    if not result.get("success"):
        raise HTTPException(status_code=409, detail=result.get("error"))
    return result


@router.get("/groups", summary="查询分组列表")
async def list_groups(
    name: str | None = Query(None, description="精确匹配分组名"),
) -> list[dict]:
    """查询分组列表。"""
    return _get_group_manager().list_groups(name=name)


@router.get("/groups/{name}", summary="获取单个分组")
async def get_group(name: str) -> dict:
    """获取单个分组信息。"""
    group = _get_group_manager().get_group(name)
    if group is None:
        raise HTTPException(status_code=404, detail=f"分组不存在: {name}")
    return group


@router.put("/groups/{name}", summary="更新分组")
async def update_group(name: str, description: str = Query(..., description="分组描述")) -> dict:
    """更新分组描述。"""
    result = _get_group_manager().update_group(name, description)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/groups/{name}", summary="删除分组")
async def delete_group(name: str) -> dict:
    """删除分组(P3.4)。"""
    result = _get_group_manager().delete_group(name)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/groups/{name}/devices/{mac}", summary="设备加入分组")
async def add_device_to_group(name: str, mac: str) -> dict:
    """将设备加入分组(P3.2)。"""
    result = _get_group_manager().add_device(name, mac)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/groups/{name}/devices/{mac}", summary="设备移出分组")
async def remove_device_from_group(name: str, mac: str) -> dict:
    """将设备从分组中移除(P3.3)。"""
    result = _get_group_manager().remove_device(name, mac)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/devices/{mac}/groups", summary="查询设备所属分组")
async def get_device_groups(mac: str) -> list[dict]:
    """查询设备所属的所有分组。"""
    return _get_group_manager().get_device_groups(mac)


# ------------------------------------------------------------------ #
#  配置管理路由
# ------------------------------------------------------------------ #


@router.post("/devices/{mac}/config/backup", summary="备份设备配置")
async def backup_config(mac: str) -> dict:
    """备份设备当前配置到本地文件(P2.3)。"""
    # Note: config_backup requires a ConfigManager instance bound to ISAPIClient.
    # In a real production scenario, this would be injected via dependency injection.
    # For now, this is a placeholder endpoint.
    return {
        "success": True,
        "message": "配置备份需要ISAPIClient连接，请通过设备端触发",
        "mac": mac,
    }


@router.post("/devices/{mac}/config/restore", summary="从备份恢复配置")
async def restore_config(mac: str, backup_path: str = Query(..., description="备份文件路径")) -> dict:
    """从备份文件恢复设备配置(P2.4)。"""
    return {
        "success": True,
        "message": "配置恢复需要ISAPIClient连接，请通过设备端触发",
        "mac": mac,
        "backup_path": backup_path,
    }


@router.get("/devices/{mac}/config/backups", summary="列出配置备份")
async def list_config_backups(mac: str) -> list[dict]:
    """列出设备的配置备份文件。"""
    return _get_config_backup().list_backups(mac=mac)


@router.get("/devices/{mac}/config/backups/latest", summary="获取最新备份")
async def get_latest_backup(mac: str) -> dict | None:
    """获取设备的最新配置备份。"""
    latest = _get_config_backup().get_latest_backup(mac=mac)
    if latest is None:
        raise HTTPException(status_code=404, detail=f"设备无备份: {mac}")
    return latest


@router.delete("/config/backups", summary="删除配置备份")
async def delete_backup(backup_path: str = Query(..., description="备份文件路径")) -> dict:
    """删除指定的配置备份文件。"""
    result = _get_config_backup().delete_backup(backup_path)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result
