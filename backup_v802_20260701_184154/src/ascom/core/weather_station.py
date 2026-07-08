"""
M9 ASCOM v1.0 - 气象站驱动

气象数据读取: 温度、湿度、风速、天空温度、露点、安全阈值。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from src.ascom.constants import (
    ErrorCode,
    WEATHER_POLL_INTERVAL,
    WEATHER_SAFE_HUMIDITY,
    WEATHER_SAFE_WIND_SPEED,
    DeviceType,
    ConnectionStatus,
)


class WeatherStationDriver:
    """ASCOM 气象站驱动封装。

    实现:
    - 气象站连接/断开
    - 数据轮询读取
    - 阈值检查 (风速/湿度)
    - 安全状态判断
    """

    def __init__(self, driver_id: str = "") -> None:
        from src.ascom.constants import WEATHER_SAFE_WIND_SPEED, WEATHER_SAFE_HUMIDITY
        self._driver_id = driver_id
        self._is_connected = False
        self._connection_status = ConnectionStatus.DISCONNECTED
        self._temperature = 0.0
        self._humidity = 0.0
        self._wind_speed = 0.0
        self._wind_gust = 0.0
        self._dew_point = 0.0
        self._sky_temperature = 0.0
        self._rain_rate = 0.0
        self._wind_direction = 0.0
        self._safe_wind = WEATHER_SAFE_WIND_SPEED
        self._safe_humidity = WEATHER_SAFE_HUMIDITY
        self._poll_interval = WEATHER_POLL_INTERVAL
        self._is_safe = True
        self._lock = threading.Lock()

    # ================================================================== #
    #  连接管理
    # ================================================================== #

    def connect(self, driver_id: str = "") -> dict[str, Any]:
        """连接气象站。

        Args:
            driver_id: ASCOM 驱动 ProgID

        Returns:
            连接结果
        """
        from src.ascom.constants import ConnectionStatus, WEATHER_SAFE_WIND_SPEED, WEATHER_SAFE_HUMIDITY
        with self._lock:
            if self._is_connected:
                return self._ok_result("气象站已连接")

            if not driver_id and not self._driver_id:
                return self._error_result(
                    ErrorCode.INVALID_DEVICE_ID,
                    "未提供驱动 ID",
                )

            try:
                import win32com.client  # type: ignore

                actual_id = driver_id or self._driver_id
                self._weather_com = win32com.client.Dispatch(actual_id)
                self._weather_com.Connected = True
                self._driver_id = actual_id
                self._is_connected = True
                self._connection_status = ConnectionStatus.CONNECTED

                # 初始数据读取
                self._refresh_data()

                return self._ok_result("气象站连接成功")

            except ImportError:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    "缺少 pywin32 模块, 请运行: pip install pywin32",
                )
            except Exception as e:
                return self._error_result(
                    ErrorCode.CONNECTION_FAILED,
                    f"气象站连接失败: {str(e)}",
                )

    def disconnect(self) -> dict[str, Any]:
        """断开气象站连接。"""
        with self._lock:
            if not self._is_connected:
                return self._ok_result("气象站已断开")

            try:
                self._weather_com.Connected = False
                self._is_connected = False
                self._connection_status = ConnectionStatus.DISCONNECTED
                return self._ok_result("气象站断开成功")
            except Exception as e:
                return self._error_result(
                    ErrorCode.DISCONNECT_FAILED,
                    f"断开连接失败: {str(e)}",
                )

    # ================================================================== #
    #  数据读取
    # ================================================================== #

    def get_data(self) -> dict[str, Any]:
        """读取当前气象数据。

        Returns:
            温度、湿度、风速等
        """
        with self._lock:
            if not self._is_connected:
                return self._error_result(
                    ErrorCode.NOT_CONNECTED,
                    "气象站未连接",
                )

            try:
                self._refresh_data()
                self._update_safety()

                return {
                    "success": True,
                    "message": "获取数据成功",
                    "data": {
                        "temperature": self._round(self._temperature),
                        "humidity": self._round(self._humidity),
                        "wind_speed": self._round(self._wind_speed),
                        "wind_gust": self._round(self._wind_gust),
                        "dew_point": self._round(self._dew_point),
                        "sky_temperature": self._round(self._sky_temperature),
                        "rain_rate": self._round(self._rain_rate),
                        "wind_direction": self._wind_direction,
                        "is_safe": self._is_safe,
                        "safe_wind": self._round(self._safe_wind),
                        "safe_humidity": self._round(self._safe_humidity),
                    },
                }
            except Exception as e:
                return self._error_result(
                    ErrorCode.INTERNAL_ERROR,
                    f"读取数据失败: {str(e)}",
                )

    def get_status(self) -> dict[str, Any]:
        """获取气象站完整状态。"""
        data_result = self.get_data()
        if not data_result.get("success"):
            return data_result

        data_result["data"]["device_type"] = DeviceType.WEATHER_STATION.value
        data_result["data"]["connection_status"] = self._connection_status.value
        return data_result

    def is_weather_safe(self) -> bool:
        """判断当前气象条件是否安全。"""
        with self._lock:
            if not self._is_connected:
                return False
            self._refresh_data()
            self._update_safety()
            return self._is_safe

    # ================================================================== #
    #  阈值配置
    # ================================================================== #

    def set_safe_wind_speed(self, wind_speed: float) -> dict[str, Any]:
        """设置安全风速上限。

        Args:
            wind_speed: 风速 (m/s)

        Returns:
            操作结果
        """
        with self._lock:
            self._safe_wind = wind_speed
            self._update_safety()
            return self._ok_result(f"安全风速已设置为: {wind_speed} m/s")

    def set_safe_humidity(self, humidity: float) -> dict[str, Any]:
        """设置安全湿度上限。

        Args:
            humidity: 湿度 (%)

        Returns:
            操作结果
        """
        with self._lock:
            self._safe_humidity = humidity
            self._update_safety()
            return self._ok_result(f"安全湿度已设置为: {humidity}%")

    # ================================================================== #
    #  内部方法
    # ================================================================== #

    def _refresh_data(self) -> None:
        """从设备刷新数据。"""
        if not self._is_connected:
            return

        try:
            if hasattr(self._weather_com, "Temperature"):
                self._temperature = float(self._weather_com.Temperature)
            if hasattr(self._weather_com, "Humidity"):
                self._humidity = float(self._weather_com.Humidity)
            if hasattr(self._weather_com, "WindSpeed"):
                self._wind_speed = float(self._weather_com.WindSpeed)
            if hasattr(self._weather_com, "WindGust"):
                self._wind_gust = float(self._weather_com.WindGust)
            if hasattr(self._weather_com, "DewPoint"):
                self._dew_point = float(self._weather_com.DewPoint)
            if hasattr(self._weather_com, "SkyTemperature"):
                self._sky_temperature = float(self._weather_com.SkyTemperature)
            if hasattr(self._weather_com, "RainRate"):
                self._rain_rate = float(self._weather_com.RainRate)
            if hasattr(self._weather_com, "WindDirection"):
                self._wind_direction = float(self._weather_com.WindDirection)
        except Exception:
            pass  # 保持上次已知值

    def _update_safety(self) -> None:
        """更新安全状态。"""
        self._is_safe = (
            self._wind_speed < self._safe_wind
            and self._humidity < self._safe_humidity
        )

    @staticmethod
    def _round(value: float, ndigits: int = 2) -> float:
        """四舍五入。"""
        return round(value, ndigits)

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
