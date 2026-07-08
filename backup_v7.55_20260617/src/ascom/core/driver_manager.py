"""
M9 ASCOM v1.0 - 驱动管理器

统一管理 ASCOM 各驱动的连接状态、生命周期。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from src.ascom.constants import (
    ErrorCode,
    ConnectionStatus,
)
from src.ascom.core.telescope_driver import TelescopeDriver
from src.ascom.core.focuser_driver import FocuserDriver
from src.ascom.core.dome_driver import DomeDriver
from src.ascom.core.filter_wheel import FilterWheelDriver
from src.ascom.core.weather_station import WeatherStationDriver


class DriverManager:
    """ASCOM 驱动管理器。

    集中管理所有驱动实例、连接状态、统一操作。
    """

    def __init__(self) -> None:
        self._telescope: Optional[TelescopeDriver] = None
        self._focuser: Optional[FocuserDriver] = None
        self._dome: Optional[DomeDriver] = None
        self._filter_wheel: Optional[FilterWheelDriver] = None
        self._weather_station: Optional[WeatherStationDriver] = None
        self._lock = threading.Lock()

    # ================================================================== #
    #  初始化/清理
    # ================================================================== #

    def initialize(self) -> dict[str, Any]:
        """初始化管理器 (创建所有驱动实例)。

        Returns:
            初始化结果
        """
        with self._lock:
            self._telescope = TelescopeDriver()
            self._focuser = FocuserDriver()
            self._dome = DomeDriver()
            self._filter_wheel = FilterWheelDriver()
            self._weather_station = WeatherStationDriver()

            return {
                "success": True,
                "message": "驱动管理器初始化成功",
                "data": {
                    "drivers": [
                        "telescope", "focuser", "dome",
                        "filter_wheel", "weather_station",
                    ],
                },
            }

    def shutdown(self) -> None:
        """关闭管理器, 断开所有设备。"""
        with self._lock:
            if self._telescope and self._telescope.is_connected:
                self._telescope.disconnect()
            if self._focuser and self._focuser.is_connected:
                self._focuser.disconnect()
            if self._dome and self._dome.is_connected:
                self._dome.disconnect()
            if self._filter_wheel and self._filter_wheel.is_connected:
                self._filter_wheel.disconnect()
            if self._weather_station and self._weather_station.is_connected:
                self._weather_station.disconnect()

    # ================================================================== #
    #  单个驱动
    # ================================================================== #

    def get_telescope(self) -> Optional[TelescopeDriver]:
        """获取望远镜驱动。"""
        return self._telescope

    def get_focuser(self) -> Optional[FocuserDriver]:
        """获取焦点器驱动。"""
        return self._focuser

    def get_dome(self) -> Optional[DomeDriver]:
        """获取圆顶驱动。"""
        return self._dome

    def get_filter_wheel(self) -> Optional[FilterWheelDriver]:
        """获取滤镜轮驱动。"""
        return self._filter_wheel

    def get_weather_station(self) -> Optional[WeatherStationDriver]:
        """获取气象站驱动。"""
        return self._weather_station

    # ================================================================== #
    #  连接状态
    # ================================================================== #

    def get_all_status(self) -> dict[str, Any]:
        """获取所有设备的连接状态。

        Returns:
            各设备状态汇总
        """
        status: dict[str, Any] = {}

        if self._telescope:
            result = self._telescope.get_status()
            status["telescope"] = result.get("data", {})
        else:
            status["telescope"] = {"connection_status": "not_initialized"}

        if self._focuser:
            result = self._focuser.get_status()
            status["focuser"] = result.get("data", {})
        else:
            status["focuser"] = {"connection_status": "not_initialized"}

        if self._dome:
            result = self._dome.get_status()
            status["dome"] = result.get("data", {})
        else:
            status["dome"] = {"connection_status": "not_initialized"}

        if self._filter_wheel:
            result = self._filter_wheel.get_status()
            status["filter_wheel"] = result.get("data", {})
        else:
            status["filter_wheel"] = {"connection_status": "not_initialized"}

        if self._weather_station:
            result = self._weather_station.get_status()
            status["weather_station"] = result.get("data", {})
        else:
            status["weather_station"] = {"connection_status": "not_initialized"}

        return status

    def get_connection_status(self, device_type: str) -> ConnectionStatus:
        """获取指定设备连接状态。

        Args:
            device_type: 设备类型 (telescope/focuser/dome/filter_wheel/weather_station)

        Returns:
            连接状态枚举
        """
        if device_type == "telescope" and self._telescope:
            return ConnectionStatus.CONNECTED if self._telescope.is_connected else ConnectionStatus.DISCONNECTED
        if device_type == "focuser" and self._focuser:
            return ConnectionStatus.CONNECTED if self._focuser.is_connected else ConnectionStatus.DISCONNECTED
        if device_type == "dome" and self._dome:
            return ConnectionStatus.CONNECTED if self._dome.is_connected else ConnectionStatus.DISCONNECTED
        if device_type == "filter_wheel" and self._filter_wheel:
            return ConnectionStatus.CONNECTED if self._filter_wheel.is_connected else ConnectionStatus.DISCONNECTED
        if device_type == "weather_station" and self._weather_station:
            return ConnectionStatus.CONNECTED if self._weather_station.is_connected else ConnectionStatus.DISCONNECTED

        return ConnectionStatus.DISCONNECTED

    def is_all_connected(self) -> bool:
        """是否所有设备都已连接。"""
        return all([
            self._telescope.is_connected if self._telescope else False,
            self._focuser.is_connected if self._focuser else False,
            self._dome.is_connected if self._dome else False,
            self._filter_wheel.is_connected if self._filter_wheel else False,
            self._weather_station.is_connected if self._weather_station else False,
        ])


# ================================================================== #
#  全局单例
# ================================================================== #

_driver_manager: Optional[DriverManager] = None


def get_driver_manager() -> DriverManager:
    """获取驱动管理器单例。"""
    global _driver_manager
    if _driver_manager is None:
        _driver_manager = DriverManager()
    return _driver_manager


def init_driver_manager() -> DriverManager:
    """初始化并返回驱动管理器。"""
    global _driver_manager
    _driver_manager = DriverManager()
    _driver_manager.initialize()
    return _driver_manager


def get_telescope() -> TelescopeDriver:
    """快捷获取望远镜驱动。"""
    mgr = get_driver_manager()
    t = mgr.get_telescope()
    if t is None:
        raise RuntimeError("TelescopeDriver 未初始化")
    return t


def get_focuser() -> FocuserDriver:
    """快捷获取焦点器驱动。"""
    mgr = get_driver_manager()
    f = mgr.get_focuser()
    if f is None:
        raise RuntimeError("FocuserDriver 未初始化")
    return f


def get_dome() -> DomeDriver:
    """快捷获取圆顶驱动。"""
    mgr = get_driver_manager()
    d = mgr.get_dome()
    if d is None:
        raise RuntimeError("DomeDriver 未初始化")
    return d


def get_filter_wheel() -> FilterWheelDriver:
    """快捷获取滤镜轮驱动。"""
    mgr = get_driver_manager()
    fw = mgr.get_filter_wheel()
    if fw is None:
        raise RuntimeError("FilterWheelDriver 未初始化")
    return fw


def get_weather_station() -> WeatherStationDriver:
    """快捷获取气象站驱动。"""
    mgr = get_driver_manager()
    ws = mgr.get_weather_station()
    if ws is None:
        raise RuntimeError("WeatherStationDriver 未初始化")
    return ws
