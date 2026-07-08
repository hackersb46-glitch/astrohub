"""
M9 ASCOM v1.0 - 滤镜轮驱动

滤镜位置切换、自定义标签、状态查询。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import threading
from typing import Any

from src.ascom.constants import (
    ErrorCode,
    DeviceType,
    ConnectionStatus,
)


class FilterWheelDriver:
    """ASCOM 滤镜轮驱动封装。

    实现:
    - 滤镜轮连接/断开
    - 切换到指定位置
    - 查询当前位置
    - 自定义滤镜标签
    """

    def __init__(self, driver_id: str = "") -> None:
        self._driver_id = driver_id
        _connection_status = ConnectionStatus.DISCONNECTED
        self._is_connected = False
        self._current_position = 0
        self._filter_names: list[str] = []
        self._positions = 0
        self._lock = threading.Lock()

    # ================================================================== #
    #  连接管理
    # ================================================================== #

    def connect(self, driver_id: str = "") -> dict[str, Any]:
        """连接滤镜轮。

        Args:
            driver_id: ASCOM 驱动 ProgID

        Returns:
            连接结果
        """
        from src.ascom.constants import ConnectionStatus
        with self._lock:
            if self._is_connected:
                return self._ok_result("滤镜轮已连接")

            if not driver_id and not self._driver_id:
                return self._error_result(
                    ErrorCode.INVALID_DEVICE_ID,
                    "未提供驱动 ID",
                )

            try:
                import win32com.client  # type: ignore

                actual_id = driver_id or self._driver_id
                self._fw_com = win32com.client.Dispatch(actual_id)
                self._fw_com.Connected = True
                self._driver_id = actual_id
                self._is_connected = True
                self._connection_status = ConnectionStatus.CONNECTED

                # 获取滤镜数量
                try:
                    self._positions = int(self._fw_com.Positions)
                except Exception:
                    self._positions = 0

                # 读取滤镜名称
                self._filter_names = self._read_filter_names()

                return self._ok_result("滤镜轮连接成功")

            except ImportError:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    "缺少 pywin32 模块, 请运行: pip install pywin32",
                )
            except Exception as e:
                return self._error_result(
                    ErrorCode.CONNECTION_FAILED,
                    f"滤镜轮连接失败: {str(e)}",
                )

    def disconnect(self) -> dict[str, Any]:
        """断开滤镜轮连接。"""
        with self._lock:
            if not self._is_connected:
                return self._ok_result("滤镜轮已断开")

            try:
                self._fw_com.Connected = False
                self._is_connected = False
                self._connection_status = ConnectionStatus.DISCONNECTED
                return self._ok_result("滤镜轮断开成功")
            except Exception as e:
                return self._error_result(
                    ErrorCode.DISCONNECT_FAILED,
                    f"断开连接失败: {str(e)}",
                )

    # ================================================================== #
    #  位置控制
    # ================================================================== #

    def set_position(self, position: int) -> dict[str, Any]:
        """切换到指定滤镜位置。

        Args:
            position: 滤镜位置 (0 ~ Positions-1)

        Returns:
            操作结果
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "滤镜轮未连接",
                )

            if position < 0 or (self._positions > 0 and position >= self._positions):
                return self._error_result(
                    ErrorCode.INVALID_PARAMETER,
                    f"位置无效: {position}, 范围 0-{self._positions - 1}",
                )

            try:
                self._fw_com.Position = position
                self._current_position = position
                return self._ok_result(f"切换到滤镜 {position}")
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"切换滤镜失败: {str(e)}",
                )

    def set_position_by_name(self, name: str) -> dict[str, Any]:
        """按名称切换滤镜。

        Args:
            name: 滤镜名称

        Returns:
            操作结果
        """
        for idx, fname in enumerate(self._filter_names):
            if fname.lower() == name.lower():
                return self.set_position(idx)

        return self._error_result(
            ErrorCode.INVALID_PARAMETER,
            f"滤镜不存在: {name}",
        )

    # ================================================================== #
    #  状态查询
    # ================================================================== #

    def get_position(self) -> dict[str, Any]:
        """获取当前滤镜位置。

        Returns:
            位置信息
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "滤镜轮未连接",
                )

            try:
                self._current_position = int(self._fw_com.Position)
                name = ""
                if 0 <= self._current_position < len(self._filter_names):
                    name = self._filter_names[self._current_position]
                return {
                    "success": True,
                    "message": "获取位置成功",
                    "data": {
                        "position": self._current_position,
                        "name": name,
                        "total": self._positions,
                    },
                }
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"读取位置失败: {str(e)}",
                )

    def get_status(self) -> dict[str, Any]:
        """获取滤镜轮完整状态。"""
        with self._lock:
            if not self._is_connected:
                return {
                    "success": True,
                    "message": "滤镜轮未连接",
                    "data": {
                        "device_type": DeviceType.FILTER_WHEEL.value,
                        "connection_status": self._connection_status.value,  # type: ignore
                    },
                }

            try:
                status: dict[str, Any] = {
                    "device_type": DeviceType.FILTER_WHEEL.value,
                    "connection_status": self._connection_status.value,  # type: ignore
                    "position": self._current_position,
                    "positions": self._positions,
                    "filter_names": self._filter_names,
                }

                if hasattr(self._fw_com, "Name"):
                    status["name"] = self._fw_com.Name
                if hasattr(self._fw_com, "DriverVersion"):
                    status["driver_version"] = self._fw_com.DriverVersion

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
    #  滤镜标签
    # ================================================================== #

    def get_filter_names(self) -> list[str]:
        """获取滤镜名称列表。"""
        return list(self._filter_names)

    def set_filter_name(self, position: int, name: str) -> dict[str, Any]:
        """设置滤镜名称 (本地缓存)。

        注意: ASCOM 滤镜轮本身不支持运行时改名, 仅缓存本地标签。
        """
        if position < 0 or position >= len(self._filter_names):
            return self._error_result(
                ErrorCode.INVALID_PARAMETER,
                f"位置无效: {position}",
            )

        self._filter_names[position] = name
        return self._ok_result(f"滤镜 {position} 已更名为: {name}")

    # ================================================================== #
    #  内部方法
    # ================================================================== #

    def _read_filter_names(self) -> list[str]:
        """读取滤镜名称。"""
        names = []
        for i in range(self._positions):
            try:
                name = self._fw_com.Name(i)
                names.append(str(name))
            except Exception:
                names.append(f"Filter {i}")
        if not names:
            for i in range(self._positions):
                names.append(f"Filter {i}")
        return names

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
