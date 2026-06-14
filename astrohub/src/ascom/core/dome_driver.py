"""
M9 ASCOM v1.0 - 圆顶驱动

圆顶角度控制、旋转方向、跟随望远镜同步。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import threading
from typing import Any

from src.ascom.constants import (
    ErrorCode,
    ERROR_CODE_DESCRIPTION,
    DeviceType,
    ConnectionStatus,
    DomeDirection,
)


class DomeDriver:
    """ASCOM 圆顶驱动封装。

    实现:
    - 圆顶连接/断开
    - 旋转到指定角度
    - 停止旋转
    - 读取当前方位角
    - 旋转方向控制
    - 快门开/关
    """

    def __init__(self, driver_id: str = "") -> None:
        self._driver_id = driver_id
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._is_connected = False
        self._current_azimuth = 0.0
        self._target_azimuth = 0.0
        self._is_slewing = False
        self._slaved = False
        self._shutter_open = False
        self._direction: DomeDirection = DomeDirection.CLOCKWISE
        self._lock = threading.Lock()

    # ================================================================== #
    #  连接管理
    # ================================================================== #

    def connect(self, driver_id: str = "") -> dict[str, Any]:
        """连接圆顶设备。

        Args:
            driver_id: ASCOM 驱动 ID (ProgID), 如 "ASCOM.Simulator.Dome"

        Returns:
            连接结果字典
        """
        with self._lock:
            if self._is_connected:
                return self._ok_result("圆顶已连接")

            if not driver_id and not self._driver_id:
                return self._error_result(
                    ErrorCode.INVALID_DEVICE_ID,
                    "未提供驱动 ID",
                )

            try:
                import win32com.client  # type: ignore

                actual_id = driver_id or self._driver_id
                self._dome_com = win32com.client.Dispatch(actual_id)
                self._dome_com.Connected = True
                self._driver_id = actual_id
                self._is_connected = True
                self._connection_status = ConnectionStatus.CONNECTED
                return self._ok_result("圆顶连接成功")

            except ImportError:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    "缺少 pywin32 模块, 请运行: pip install pywin32",
                )
            except Exception as e:
                return self._error_result(
                    ErrorCode.CONNECTION_FAILED,
                    f"圆顶连接失败: {str(e)}",
                )

    def disconnect(self) -> dict[str, Any]:
        """断开圆顶连接。"""
        with self._lock:
            if not self._is_connected:
                return self._ok_result("圆顶已断开")

            try:
                self._dome_com.Connected = False
                self._is_connected = False
                self._connection_status = ConnectionStatus.DISCONNECTED
                self._is_slewing = False
                return self._ok_result("圆顶断开成功")
            except Exception as e:
                return self._error_result(
                    ErrorCode.DISCONNECT_FAILED,
                    f"断开连接失败: {str(e)}",
                )

    # ================================================================== #
    #  旋转控制
    # ================================================================== #

    def slew_to_azimuth(self, azimuth: float) -> dict[str, Any]:
        """旋转圆顶到指定方位角。

        Args:
            azimuth: 目标方位角 (0-360 度)

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "圆顶未连接",
                )

            if not 0 <= azimuth < 360:
                return self._error_result(
                    ErrorCode.INVALID_PARAMETER,
                    f"方位角无效: {azimuth}, 范围 0-360",
                )

            try:
                self._target_azimuth = azimuth
                self._dome_com.SlewToAzimuth(azimuth)
                self._is_slewing = True
                return self._ok_result(f"圆顶旋转中: {azimuth}°")
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"Slew 失败: {str(e)}",
                )

    def abort_slew(self) -> dict[str, Any]:
        """停止圆顶旋转。

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "圆顶未连接",
                )

            try:
                self._dome_com.AbortSlew()
                self._is_slewing = False
                self._current_azimuth = self._read_azimuth()
                return self._ok_result("圆顶旋转已停止")
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"停止旋转失败: {str(e)}",
                )

    # ================================================================== #
    #  状态查询
    # ================================================================== #

    def get_position(self) -> dict[str, Any]:
        """获取圆顶当前位置。

        Returns:
            方位角信息
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "圆顶未连接",
                )

            try:
                azimuth = self._read_azimuth()
                return {
                    "success": True,
                    "message": "获取位置成功",
                    "data": {
                        "azimuth": azimuth,
                        "is_slewing": self._dome_com.Slewing if hasattr(self._dome_com, "Slewing") else self._is_slewing,
                        "connected": True,
                    },
                }
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"读取位置失败: {str(e)}",
                )

    def get_status(self) -> dict[str, Any]:
        """获取圆顶完整状态。

        Returns:
            完整状态信息
        """
        with self._lock:
            if not self._is_connected:
                return {
                    "success": True,
                    "message": "圆顶未连接",
                    "data": {
                        "device_type": DeviceType.DOME.value,
                        "connection_status": self._connection_status.value,
                    },
                }

            try:
                status: dict[str, Any] = {
                    "device_type": DeviceType.DOME.value,
                    "connection_status": self._connection_status.value,
                    "azimuth": self._read_azimuth(),
                    "is_slewing": self._is_slewing,
                    "slaved": self._slaved,
                    "shutter_open": self._shutter_open,
                    "direction": self._direction.value,
                }

                if hasattr(self._dome_com, "DriverVersion"):
                    status["driver_version"] = self._dome_com.DriverVersion
                if hasattr(self._dome_com, "Name"):
                    status["name"] = self._dome_com.Name
                if hasattr(self._dome_com, "ShutterStatus"):
                    status["shutter_open"] = self._dome_com.ShutterStatus

                return {
                    "success": True,
                    "message": "获取状态成功",
                    "data": status,
                }
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"读取状态失败: {str(e)}",
                )

    # ================================================================== #
    #  圆顶属性
    # ================================================================== #

    def set_slaved(self, slaved: bool) -> dict[str, Any]:
        """设置圆顶跟随望远镜。

        Args:
            slaved: 是否跟随

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "圆顶未连接",
                )

            try:
                self._dome_com.Slaved = slaved
                self._slaved = slaved
                return self._ok_result(f"圆顶跟随: {'开' if slaved else '关'}")
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"设置跟随失败: {str(e)}",
                )

    def set_shutter(self, open_shutter: bool) -> dict[str, Any]:
        """控制快门开关。

        Args:
            open_shutter: True 打开, False 关闭

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "圆顶未连接",
                )

            try:
                self._dome_com.ShutterOpen = open_shutter
                self._shutter_open = open_shutter
                return self._ok_result(f"快门: {'开' if open_shutter else '关'}")
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"快门控制失败: {str(e)}",
                )

    # ================================================================== #
    #  内部方法
    # ================================================================== #

    def _read_azimuth(self) -> float:
        """读取当前方位角。"""
        try:
            return float(self._dome_com.Azimuth)
        except Exception:
            return self._current_azimuth

    @property
    def is_connected(self) -> bool:
        """连接状态。"""
        return self._is_connected

    @staticmethod
    def _ok_result(message: str) -> dict[str, Any]:
        """成功结果。"""
        return {"success": True, "message": message, "data": {}}

    @staticmethod
    def _error_result(code: ErrorCode, message: str) -> dict[str, Any]:
        """错误结果。"""
        return {
            "success": False,
            "message": message,
            "code": code.value,
            "data": {},
        }
