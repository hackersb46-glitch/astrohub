"""
M6 Web UI Service v1.0 - FastAPI 路由层

仪表盘数据、通知系统、健康检查、SPA 路由。
使用 DashboardAggregator, NotificationManager, HealthChecker 等。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from webui.constants import NotificationLevel, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

router = APIRouter(prefix="/api/v1", tags=["M6 Web UI"])


# ------------------------------------------------------------------ #
#  全局管理器实例延迟引用
# ------------------------------------------------------------------ #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) -> None:
    """注入管理器实例到路由层。

    Args:
        **kwargs: 各管理器实例
    """
    _managers.update(kwargs)


def _get_dashboard_aggregator() -> Any:
    manager = _managers.get("dashboard_aggregator")
    if manager is None:
        raise HTTPException(status_code=500, detail="DashboardAggregator 未初始化")
    return manager


def _get_notification_manager() -> Any:
    manager = _managers.get("notification_manager")
    if manager is None:
        raise HTTPException(status_code=500, detail="NotificationManager 未初始化")
    return manager


def _get_health_checker() -> Any:
    manager = _managers.get("health_checker")
    if manager is None:
        raise HTTPException(status_code=500, detail="HealthChecker 未初始化")
    return manager


# ------------------------------------------------------------------ #
#  Dashboard 仪表盘路由
# ------------------------------------------------------------------ #

@router.get("/dashboard/overview", summary="获取仪表盘总览")
async def get_dashboard_overview() -> dict:
    """获取仪表盘聚合数据（设备统计、流状态、校准进度）。"""
    try:
        aggregator = _get_dashboard_aggregator()
        return await aggregator.get_overview()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"仪表盘数据获取失败: {str(e)}")


@router.post("/dashboard/refresh", summary="刷新仪表盘缓存")
async def refresh_dashboard() -> dict:
    """强制刷新仪表盘缓存数据。"""
    try:
        aggregator = _get_dashboard_aggregator()
        await aggregator.refresh()
        return {"status": "success", "message": "仪表盘已刷新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"仪表盘刷新失败: {str(e)}")


# ------------------------------------------------------------------ #
#  Notification 通知路由
# ------------------------------------------------------------------ #

@router.post("/notifications", summary="添加通知")
async def add_notification(
    level: str = Query(..., description="通知等级: info/warning/error/success"),
    message: str = Query(..., description="通知内容"),
    title: Optional[str] = Query(None, description="通知标题"),
    duration: int = Query(5000, description="自动消失时间(ms)"),
) -> dict:
    """添加新通知。"""
    try:
        notif_level = NotificationLevel(level)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法通知等级: {level}，可选值: info/warning/error/success")

    manager = _get_notification_manager()
    notification = manager.add(notif_level, message, title, duration)
    return {"status": "success", "data": notification.to_dict()}


@router.get("/notifications", summary="获取通知列表")
async def list_notifications(
    unread_only: bool = Query(False, description="仅显示未读通知"),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE, description="返回数量上限"),
) -> dict:
    """获取通知列表。"""
    manager = _get_notification_manager()
    if unread_only:
        notifications = manager.get_unread()
    else:
        notifications = manager.get_all(limit)

    return {
        "status": "success",
        "total": len(notifications),
        "data": notifications,
    }


@router.put("/notifications/{notification_id}/read", summary="标记通知已读")
async def mark_notification_read(notification_id: str) -> dict:
    """标记指定通知为已读。"""
    manager = _get_notification_manager()
    ok = manager.mark_read(notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"通知不存在: {notification_id}")
    return {"status": "success", "message": "已标记为已读"}


@router.post("/notifications/read-all", summary="标记所有通知已读")
async def mark_all_read() -> dict:
    """标记所有通知为已读。"""
    manager = _get_notification_manager()
    count = manager.mark_all_read()
    return {"status": "success", "marked": count}


@router.delete("/notifications", summary="清理通知")
async def clear_notifications(
    level: Optional[str] = Query(None, description="指定清理的通知等级"),
) -> dict:
    """清理通知，可选指定等级。"""
    manager = _get_notification_manager()
    if level:
        try:
            notif_level = NotificationLevel(level)
            count = manager.clear(notif_level)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"非法通知等级: {level}")
    else:
        count = manager.clear()

    return {"status": "success", "cleared": count}


@router.get("/notifications/count", summary="获取通知数量")
async def notification_count(
    level: Optional[str] = Query(None, description="指定等级的通知数"),
) -> dict:
    """获取通知数量统计。"""
    manager = _get_notification_manager()
    if level:
        try:
            notif_level = NotificationLevel(level)
            count = manager.count(notif_level)
        except ValueError:
            count = 0
    else:
        count = manager.count()

    return {"total": count}


# ------------------------------------------------------------------ #
#  Health Check 健康检查路由
# ------------------------------------------------------------------ #

@router.get("/health", summary="M6 自身健康检查")
async def health_self() -> dict:
    """获取 M6 自身健康状态。"""
    checker = _get_health_checker()
    return await checker.check_self()


@router.get("/health/all", summary="全部服务健康检查")
async def health_all() -> dict:
    """检查所有后端服务（M2-M5）的健康状态。"""
    try:
        checker = _get_health_checker()
        return await checker.check_all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"健康检查失败: {str(e)}")
