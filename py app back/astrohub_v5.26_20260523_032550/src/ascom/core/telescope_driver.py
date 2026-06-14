"""
M9 ASCOM v1.0 - 望远镜驱动

望远镜连接、Slew 控制、位置查询、跟踪模式、取消 Slew。

对应评审点: P1 (望远镜连接、Slew 控制、位置查询、跟踪模式、Slew 取消)

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Optional

from src.ascom.constants import (
    ErrorCode,
    DEFAULT_TRACKING_MODE,
    CONNECT_TIMEOUT_SECONDS,
    COMMAND_TIMEOUT_SECONDS,
    DeviceType,
    ConnectionStatus,
    TrackingMode,
    TelescopeStatus,
)


class TelescopeDriver:
    """ASCOM 望远镜驱动封装。

    实现:
    - P1.1: 望远镜连接 (获取望远镜状态: homing/tracking)
    - P1.2: SlewToCoordinates (赤经/赤纬)
    - P1.3: 位置查询 (RightAscension / Declination)
    - P1.4: 跟踪模式设置 (sidereal/lunar/solar/off)
    - P1.5: AbortSlew (取消正在进行的 Slew)
    """

    def __init__(self, driver_id: str = "") -> None:
        self._driver_id = driver_id
        self._is_connected = False
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._current_ra = 0.0
        self._current_dec = 0.0
        self._is_slewing = False
        self._tracking_mode = TrackingMode.OFF
        self._is_parked = False
        self._is_homed = False
        self._lock = threading.Lock()

    # ================================================================== #
    #  P1.1 - 望远镜连接
    # ================================================================== #

    def connect(self, driver_id: str = "") -> dict[str, Any]:
        """连接 ASCOM 望远镜。

        Args:
            driver_id: ASCOM 驱动 ProgID

        Returns:
            连接结果, 包含望远镜初始状态
        """
        with self._lock:
            if self._is_connected:
                return self._ok_result("望远镜已连接")

            if not driver_id and not self._driver_id:
                return self._error_result(
                    ErrorCode.INVALID_DEVICE_ID,
                    "未提供驱动 ID",
                )

            try:
                import win32com.client  # type: ignore

                actual_id = driver_id or self._driver_id
                self._scope_com = win32com.client.Dispatch(actual_id)
                self._scope_com.Connected = True

                self._driver_id = actual_id
                self._is_connected = True
                self._connection_status = ConnectionStatus.CONNECTED

                # 获取初始状态
                self._current_ra = float(getattr(self._scope_com, "RightAscension", 0.0) or 0.0)
                self._current_dec = float(getattr(self._scope_com, "Declination", 0.0) or 0.0)
                self._is_slewing = bool(getattr(self._scope_com, "IsSlew", False))

                # 跟踪模式
                try:
                    tracking = int(self._scope_com.Tracking)
                    mode_map = {
                        0: TrackingMode.OFF,
                        1: TrackingMode.SIDEREAL,
                        2: TrackingMode.LUNAR,
                        3: TrackingMode.SOLAR,
                    }
                    self._tracking_mode = mode_map.get(tracking, TrackingMode.OFF)
                except Exception:
                    self._tracking_mode = TrackingMode.OFF

                # 归位状态
                try:
                    self._is_homed = bool(self._scope_com.IsHomed if hasattr(self._scope_com, "IsHomed") else False)
                except Exception:
                    self._is_homed = False

                return {
                    "success": True,
                    "message": "望远镜连接成功",
                    "data": {
                        "ra": self._current_ra,
                        "dec": self._current_dec,
                        "tracking_mode": self._tracking_mode.value,
                        "is_slewing": self._is_slewing,
                        "is_homed": self._is_homed,
                    },
                }

            except ImportError:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    "缺少 pywin32 模块, 请运行: pip install pywin32",
                )
            except Exception as e:
                return self._error_result(
                    ErrorCode.CONNECTION_FAILED,
                    f"望远镜连接失败: {str(e)}",
                )

    def disconnect(self) -> dict[str, Any]:
        """断开望远镜连接。"""
        with self._lock:
            if not self._is_connected:
                return self._ok_result("望远镜已断开")

            try:
                self._scope_com.Connected = False
                self._is_connected = False
                self._connection_status = ConnectionStatus.DISCONNECTED
                self._is_slewing = False
                return self._ok_result("望远镜断开成功")
            except Exception as e:
                return self._error_result(
                    ErrorCode.DISCONNECT_FAILED,
                    f"断开连接失败: {str(e)}",
                )

    # ================================================================== #
    #  P1.2 - Slew 控制
    # ================================================================== #

    def slew_to_coordinates(
        self,
        ra: float,
        dec: float,
        timeout: int = COMMAND_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        """Slew 到目标赤经/赤纬坐标。

        Args:
            ra: 目标赤经 (小时, 0-24)
            dec: 目标赤纬 (度, -90~+90)
            timeout: 超时时间 (秒)

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "望远镜未连接",
                )

            # 坐标验证
            if not 0 <= ra <= 24:
                return self._error_result(
                    ErrorCode.TELESCOPE_INVALID_COORDS,
                    f"赤经无效: {ra}, 范围 0-24 小时",
                )
            if not -90 <= dec <= 90:
                return self._error_result(
                    ErrorCode.TELESCOPE_INVALID_COORDS,
                    f"赤纬无效: {dec}, 范围 -90~+90 度",
                )

            try:
                self._scope_com.SlewToCoordinates(ra, dec)
                self._is_slewing = True
                return self._ok_result(f"Slew 中: RA={ra}, Dec={dec}")
            except Exception as e:
                return self._error_result(
                    ErrorCode.TELESCOPE_SLEW_FAILED,
                    f"Slew 失败: {str(e)}",
                )

    def wait_for_slew(self, timeout: int = COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
        """等待 Slew 完成 (阻塞)。

        Args:
            timeout: 超时时间 (秒)

        Returns:
            Slew 结果
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self._is_slewing:
                break
            time.sleep(0.5)
            try:
                is_slewing = bool(self._scope_com.IsSlew)
                if not is_slewing:
                    self._is_slewing = False
                    # 更新最终位置
                    self._current_ra = float(self._scope_com.RightAscension)
                    self._current_dec = float(self._scope_com.Declination)
                    return {
                        "success": True,
                        "message": "Slew 完成",
                        "data": {
                            "ra": self._current_ra,
                            "dec": self._current_dec,
                        },
                    }
            except Exception:
                pass

        self._is_slewing = False
        return self._error_result(
            ErrorCode.TELESCOPE_SLEW_TIMEOUT,
            f"Slew 超时 ({timeout}s)",
        )

    # ================================================================== #
    #  P1.3 - 位置查询
    # ================================================================== #

    def get_position(self) -> dict[str, Any]:
        """查询望远镜当前位置。

        Returns:
            赤经/赤纬坐标
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "望远镜未连接",
                )

            try:
                self._current_ra = float(self._scope_com.RightAscension)
                self._current_dec = float(self._scope_com.Declination)
                self._is_slewing = bool(self._scope_com.IsSlew)

                return {
                    "success": True,
                    "message": "获取位置成功",
                    "data": {
                        "ra": self._current_ra,
                        "dec": self._current_dec,
                        "is_slewing": self._is_slewing,
                    },
                }
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"读取位置失败: {str(e)}",
                )

    # ================================================================== #
    #  P1.4 - 跟踪模式
    # ================================================================== #

    def set_tracking_mode(self, mode: TrackingMode) -> dict[str, Any]:
        """设置望远镜跟踪模式。

        Args:
            mode: 跟踪模式 (sidereal/lunar/solar/off)

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "望远镜未连接",
                )

            # ASCOM 跟踪模式映射: 0=off, 1=sidereal, 2=lunar, 3=solar
            mode_map = {
                TrackingMode.OFF: 0,
                TrackingMode.SIDEREAL: 1,
                TrackingMode.LUNAR: 2,
                TrackingMode.SOLAR: 3,
            }
            ascom_mode = mode_map.get(mode, 0)

            try:
                self._scope_com.Tracking = ascom_mode
                self._tracking_mode = mode
                return self._ok_result(f"跟踪模式切换: {mode.value}")
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"设置跟踪模式失败: {str(e)}",
                )

    # ================================================================== #
    #  P1.5 - Slew 取消
    # ================================================================== #

    def abort_slew(self) -> dict[str, Any]:
        """取消正在进行的 Slew 操作。

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "望远镜未连接",
                )

            try:
                if hasattr(self._scope_com, "AbortSlew"):
                    self._scope_com.AbortSlew()
                self._is_slewing = False
                self._current_ra = float(self._scope_com.RightAscension)
                self._current_dec = float(self._scope_com.Declination)
                return self._ok_result("Slew 已取消, 望远镜停在当前位置")
            except Exception as e:
                return self._error_result(
                    ErrorCode.TELESCOPE_ABORT_FAILED,
                    f"取消 Slew 失败: {str(e)}",
                )

    # ================================================================== #
    #  额外状态
    # ================================================================== #

    def park(self) -> dict[str, Any]:
        """望远镜归位 (Park)。

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "望远镜未连接",
                )

            try:
                self._scope_com.Park()
                self._is_parked = True
                return self._ok_result("望远镜已归位")
            except Exception as e:
                return self._error_result(
                    ErrorCode.TELESCOPE_PARK_FAILED,
                    f"归位失败: {str(e)}",
                )

    def unpark(self) -> dict[str, Any]:
        """解除归位 (UnPark)。

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "望远镜未连接",
                )

            try:
                self._scope_com.Unpark()
                self._is_parked = False
                return self._ok_result("望远镜已解除归位")
            except Exception as e:
                return self._error_result(
                    ErrorCode.TELESCOPE_UNPARK_FAILED,
                    f"解除归位失败: {str(e)}",
                )

    def get_status(self) -> dict[str, Any]:
        """获取望远镜完整状态。"""
        with self._lock:
            if not self._is_connected:
                return {
                    "success": True,
                    "message": "望远镜未连接",
                    "data": {
                        "device_type": DeviceType.TELESCOPE.value,
                        "connection_status": self._connection_status.value,
                    },
                }

            try:
                self._current_ra = float(self._scope_com.RightAscension)
                self._current_dec = float(self._scope_com.Declination)
                self._is_slewing = bool(self._scope_com.IsSlew)

                status: dict[str, Any] = {
                    "device_type": DeviceType.TELESCOPE.value,
                    "connection_status": self._connection_status.value,
                    "ra": self._current_ra,
                    "dec": self._current_dec,
                    "is_slewing": self._is_slewing,
                    "tracking_mode": self._tracking_mode.value,
                    "is_parked": bool(self._scope_com.AtPark),
                    "is_homed": bool(getattr(self._scope_com, "IsHomed", False)),
                }

                if hasattr(self._scope_com, "Name"):
                    status["name"] = self._scope_com.Name
                if hasattr(self._scope_com, "DriverVersion"):
                    status["driver_version"] = self._scope_com.DriverVersion
                if hasattr(self._scope_com, "ApertureDiameter"):
                    status["aperture"] = float(self._scope_com.ApertureDiameter)

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

    def _get_tracking_status(self) -> str:
        """获取跟踪状态字符串。"""
        if self._is_slewing:
            return TelescopeStatus.SLEWING.value
        if self._tracking_mode != TrackingMode.OFF:
            return TelescopeStatus.TRACKING.value
        if self._is_parked:
            return TelescopeStatus.PARKED.value
        return TelescopeStatus.IDLE.value

    @property
    def is_connected(self) -> bool:
        """连接状态。"""
        return self._is_connected

    @staticmethod
    def _ok_result(message: str) -> dict[str, Any]:
        return {"success": True, "message": message, "data": {}}

    @staticmethod
    def _error_result(code: ErrorCode, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "message": message,
            "code": code.value,
            "data": {},
        }
