"""
M9 ASCOM v1.0 - 调焦器驱动

焦点器位置控制、步进移动、温度补偿。

对应评审点: P3 (焦点器连接、步进控制、自动对焦、温度补偿)

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import threading
import time
from typing import Any

from src.ascom.constants import (
    ErrorCode,
    FOCUSER_DEFAULT_POSITION,
    FOCUSER_TEMP_COMPENSATION_ENABLED,
    DeviceType,
    ConnectionStatus,
)


class FocuserDriver:
    """ASCOM 调焦器驱动封装。

    实现:
    - P3.1: 焦点器连接
    - P3.2: 步进控制 (移动到指定位置)
    - P3.3: HFD 自动对焦
    - P3.4: 温度补偿
    """

    def __init__(self, driver_id: str = "") -> None:
        self._driver_id = driver_id
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._is_connected = False
        self._current_position = FOCUSER_DEFAULT_POSITION
        self._target_position = FOCUSER_DEFAULT_POSITION
        self._is_moving = False
        self._max_step = 60000
        self._step_size = 1
        self._temperature = 0.0
        self._temp_comp_enabled = FOCUSER_TEMP_COMPENSATION_ENABLED
        self._temp_comp_rate = 10  # 步/度
        self._lock = threading.Lock()

    # ================================================================== #
    #  P3.1 - 焦点器连接
    # ================================================================== #

    def connect(self, driver_id: str = "") -> dict[str, Any]:
        """连接 ASCOM 焦点器。

        Args:
            driver_id: ASCOM 驱动 ProgID

        Returns:
            连接结果, 包含焦点器信息
        """
        with self._lock:
            if self._is_connected:
                return self._ok_result("焦点器已连接")

            if not driver_id and not self._driver_id:
                return self._error_result(
                    ErrorCode.INVALID_DEVICE_ID,
                    "未提供驱动 ID",
                )

            try:
                import win32com.client  # type: ignore

                actual_id = driver_id or self._driver_id
                self._focuser_com = win32com.client.Dispatch(actual_id)
                self._focuser_com.Connected = True

                self._driver_id = actual_id
                self._is_connected = True
                self._connection_status = ConnectionStatus.CONNECTED

                # 获取最大步数
                try:
                    self._max_step = int(self._focuser_com.MaxStep)
                except Exception:
                    self._max_step = 60000

                # 读取当前位置
                try:
                    self._current_position = int(self._focuser_com.Position)
                except Exception:
                    self._current_position = FOCUSER_DEFAULT_POSITION

                return self._ok_result("焦点器连接成功")

            except ImportError:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    "缺少 pywin32 模块, 请运行: pip install pywin32",
                )
            except Exception as e:
                return self._error_result(
                    ErrorCode.CONNECTION_FAILED,
                    f"焦点器连接失败: {str(e)}",
                )

    def disconnect(self) -> dict[str, Any]:
        """断开焦点器连接。"""
        with self._lock:
            if not self._is_connected:
                return self._ok_result("焦点器已断开")

            try:
                self._focuser_com.Connected = False
                self._is_connected = False
                self._connection_status = ConnectionStatus.DISCONNECTED
                self._is_moving = False
                return self._ok_result("焦点器断开成功")
            except Exception as e:
                return self._error_result(
                    ErrorCode.DISCONNECT_FAILED,
                    f"断开连接失败: {str(e)}",
                )

    # ================================================================== #
    #  P3.2 - 步进控制
    # ================================================================== #

    def move_to(self, position: int) -> dict[str, Any]:
        """移动焦点器到指定位置。

        Args:
            position: 目标位置 (0 ~ MaxStep)

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "焦点器未连接",
                )

            if position < 0 or position > self._max_step:
                return self._error_result(
                    ErrorCode.INVALID_PARAMETER,
                    f"位置无效: {position}, 范围 0-{self._max_step}",
                )

            try:
                self._focuser_com.Move(position)
                self._target_position = position
                self._is_moving = True
                return self._ok_result(f"移动中: {position}")
            except Exception as e:
                return self._error_result(
                    ErrorCode.FOCUSER_MOVE_FAILED,
                    f"移动失败: {str(e)}",
                )

    def move_absolute(self, position: int) -> dict[str, Any]:
        """绝对移动 - 同 move_to。"""
        return self.move_to(position)

    def move_relative(self, offset: int) -> dict[str, Any]:
        """相对移动。

        Args:
            offset: 步数偏移 (正=外, 负=内)

        Returns:
            操作结果
        """
        target = self._current_position + offset
        return self.move_to(target)

    def abort_move(self) -> dict[str, Any]:
        """停止焦点器移动。

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "焦点器未连接",
                )

            try:
                if hasattr(self._focuser_com, "Halt"):
                    self._focuser_com.Halt()
                self._is_moving = False
                return self._ok_result("焦点器运动已停止")
            except Exception as e:
                return self._error_result(
                    ErrorCode.FOCUSER_MOVE_FAILED,
                    f"停止移动失败: {str(e)}",
                )

    # ================================================================== #
    #  P3.3 - 自动对焦 (HFD)
    # ================================================================== #

    def auto_focus(self, hfd_callback: Any = None) -> dict[str, Any]:
        """自动对焦, 通过 HFD (半高全宽) 测量找最佳焦点位置。

        Args:
            hfd_callback: 回调函数, 返回当前 HFD 值

        Returns:
            对焦结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "焦点器未连接",
                )

            if hfd_callback is None:
                return self._error_result(
                    ErrorCode.FOCUSER_NOT_SUPPORTED,
                    "需传入相机 HFD 回调函数: lambda -> float",
                )

        try:
            # 三步对焦: 测量 - 找到最佳点
            best_pos = self._current_position
            best_hfd = float("inf")

            # 扫描范围 200 步，步长 20
            scan_range = min(200, self._max_step // 4)
            step = 20
            start_pos = max(0, self._current_position - scan_range // 2)

            pos = start_pos
            while pos <= start_pos + scan_range:
                self.move_to(pos)
                time.sleep(0.5)  # 稳定时间
                hfd = hfd_callback()
                if hfd < best_hfd:
                    best_hfd = hfd
                    best_pos = pos
                pos += step

            # 移动到最佳位置
            self.move_to(best_pos)
            time.sleep(0.5)

            return {
                "success": True,
                "message": "自动对焦完成",
                "data": {
                    "best_position": best_pos,
                    "best_hfd": best_hfd,
                },
            }
        except Exception as e:
            return self._error_result(
                ErrorCode.FOCUSER_MOVE_FAILED,
                f"自动对焦失败: {str(e)}",
            )

    # ================================================================== #
    #  P3.4 - 温度补偿
    # ================================================================== #

    def set_temperature_compensation(self, enabled: bool) -> dict[str, Any]:
        """启用/禁用温度补偿。

        Args:
            enabled: 是否启用

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "焦点器未连接",
                )

            try:
                if hasattr(self._focuser_com, "Compensate"):
                    self._focuser_com.Compensate = enabled
                self._temp_comp_enabled = enabled
                return self._ok_result(
                    f"温度补偿: {'启用' if enabled else '禁用'}",
                )
            except Exception as e:
                return self._error_result(
                    ErrorCode.FOCUSER_NOT_SUPPORTED,
                    f"温度补偿不支持: {str(e)}",
                )

    def get_temperature(self) -> dict[str, Any]:
        """获取焦点器温度。

        Returns:
            温度 (摄氏度)
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "焦点器未连接",
                )

            try:
                if hasattr(self._focuser_com, "Temperature"):
                    self._temperature = float(self._focuser_com.Temperature)
                return {
                    "success": True,
                    "message": "读取温度成功",
                    "data": {"temperature": self._temperature},
                }
            except Exception as e:
                return self._error_result(
                    ErrorCode.FOCUSER_TEMPERATURE_ERROR,
                    f"温度读取失败: {str(e)}",
                )

    # ================================================================== #
    #  状态查询
    # ================================================================== #

    def get_position(self) -> dict[str, Any]:
        """获取当前焦点位置。

        Returns:
            位置和运动状态
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "焦点器未连接",
                )

            try:
                self._current_position = int(self._focuser_com.Position)
                self._is_moving = bool(
                    self._focuser_com.IsMoving
                    if hasattr(self._focuser_com, "IsMoving")
                    else False,
                )

                data: dict[str, Any] = {
                    "position": self._current_position,
                    "is_moving": self._is_moving,
                    "temperature": self._temperature,
                    "temp_comp_enabled": self._temp_comp_enabled,
                }
                return {
                    "success": True,
                    "message": "获取位置成功",
                    "data": data,
                }
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"读取位置失败: {str(e)}",
                )

    def get_status(self) -> dict[str, Any]:
        """获取焦点器完整状态。"""
        with self._lock:
            if not self._is_connected:
                return {
                    "success": True,
                    "message": "焦点器未连接",
                    "data": {
                        "device_type": DeviceType.FOCUSER.value,
                        "connection_status": self._connection_status.value,
                    },
                }

            try:
                status: dict[str, Any] = {
                    "device_type": DeviceType.FOCUSER.value,
                    "connection_status": self._connection_status.value,
                    "position": self._current_position,
                    "max_step": self._max_step,
                    "is_moving": self._is_moving,
                    "temperature": self._temperature,
                    "temp_comp_enabled": self._temp_comp_enabled,
                }

                if hasattr(self._focuser_com, "Name"):
                    status["name"] = self._focuser_com.Name
                if hasattr(self._focuser_com, "DriverVersion"):
                    status["driver_version"] = self._focuser_com.DriverVersion

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
    #  内部方法
    # ================================================================== #

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
