"""
AstroHub v2.0 - ASCOM 设备管理器

管理 ASCOM 平台设备的连接、状态查询、能力获取。
支持望远镜、圆顶、调焦器、滤镜轮、气象站等设备类型。
"""

from __future__ import annotations

import threading
from typing import Any

from src.config import CONFIG_DIR
from src.logger import get_logger

log = get_logger("ascom_manager")

# 设备类型常量
DEVICE_TYPE_TELESCOPE = "telescope"
DEVICE_TYPE_DOME = "dome"
DEVICE_TYPE_FOCUSER = "focuser"
DEVICE_TYPE_FILTER_WHEEL = "filter_wheel"
DEVICE_TYPE_WEATHER = "weather"

DEVICE_TYPES = {
    DEVICE_TYPE_TELESCOPE,
    DEVICE_TYPE_DOME,
    DEVICE_TYPE_FOCUSER,
    DEVICE_TYPE_FILTER_WHEEL,
    DEVICE_TYPE_WEATHER,
}

# 连接状态常量
STATUS_DISCONNECTED = "disconnected"
STATUS_CONNECTING = "connecting"
STATUS_CONNECTED = "connected"
STATUS_ERROR = "error"


# ============================================================
# Data Models
# ============================================================


class ASCOMDevice:
    """ASCOM 设备信息模型。"""

    def __init__(self, device_id: str, device_type: str, name: str = "", driver_info: str = "") -> None:
        """初始化设备信息。

        Args:
            device_id: ASCOM 设备唯一标识符 (ProgID)。
            device_type: 设备类型 (telescope/dome/focuser/filter_wheel/weather)。
            name: 设备名称。
            driver_info: 驱动信息描述。
        """
        self.device_id = device_id
        self.device_type = device_type
        self.name = name
        self.driver_info = driver_info
        self.status = STATUS_DISCONNECTED
        self.connection: Any | None = None
        self.capabilities: dict[str, Any] = {}
        self.error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """将设备信息转换为字典。

        Returns:
            包含设备所有属性的字典。
        """
        return {
            "device_id": self.device_id,
            "device_type": self.device_type,
            "name": self.name,
            "driver_info": self.driver_info,
            "status": self.status,
            "capabilities": self.capabilities,
            "error_message": self.error_message,
        }


# ============================================================
# ASCOMManager
# ============================================================


class ASCOMManager:
    """ASCOM 设备管理器。

    提供 ASCOM 平台设备连接管理、状态监控、能力查询等功能。
    使用 COM 自动化与 ASCOM 驱动交互。
    """

    def __init__(self, platform: str = "windows") -> None:
        """初始化 ASCOM 平台连接。

        Args:
            platform: ASCOM 平台类型，默认 windows。可选 linux (Alpaca 协议)。
        """
        self._platform = platform
        self._devices: dict[str, ASCOMDevice] = {}
        self._lock = threading.RLock()
        self._initialized = False

        # 平台初始化标记
        try:
            if self._platform == "windows":
                self._init_windows_platform()
            else:
                self._init_alpaca_platform()
            self._initialized = True
            log.info(f"ASCOMManager 初始化完成, platform={self._platform}")
        except Exception as e:
            log.error(f"ASCOM 平台初始化失败: {e}")
            self._initialized = False

    def _init_windows_platform(self) -> None:
        """初始化 Windows ASCOM 平台 (COM)。"""
        try:
            import win32com.client  # type: ignore[import-not-found]

            self._com_available = True
            log.info("Windows ASCOM 平台 (COM) 就绪")
        except ImportError:
            self._com_available = False
            log.warning("pywin32 不可用，ASCOM COM 功能受限")

    def _init_alpaca_platform(self) -> None:
        """初始化 Alpaca 平台 (HTTP API)。"""
        try:
            import requests  # type: ignore[import-not-found]

            self._alpaca_available = True
            self._alpaca_base_url = "http://localhost:5555/api/v1"
            log.info("Alpaca ASCOM 平台 (HTTP) 就绪")
        except ImportError:
            self._alpaca_available = False
            log.warning("requests 不可用，Alpaca 功能受限")

    # ============================================================
    # Device Connection
    # ============================================================

    def connect_telescope(self, device_id: str) -> bool:
        """连接望远镜驱动。

        Args:
            device_id: 望远镜设备 ProgID (如 "ASCOM.Simulator.Telescope")。

        Returns:
            True 连接成功，False 失败。
        """
        return self._connect_device(device_id, DEVICE_TYPE_TELESCOPE)

    def connect_dome(self, device_id: str) -> bool:
        """连接圆顶驱动。

        Args:
            device_id: 圆顶设备 ProgID (如 "ASCOM.Simulator.Dome")。

        Returns:
            True 连接成功，False 失败。
        """
        return self._connect_device(device_id, DEVICE_TYPE_DOME)

    def connect_focuser(self, device_id: str) -> bool:
        """连接调焦器驱动。

        Args:
            device_id: 调焦器设备 ProgID (如 "ASCOM.Simulator.Focuser")。

        Returns:
            True 连接成功，False 失败。
        """
        return self._connect_device(device_id, DEVICE_TYPE_FOCUSER)

    def connect_filter_wheel(self, device_id: str) -> bool:
        """连接滤镜轮驱动。

        Args:
            device_id: 滤镜轮设备 ProgID (如 "ASCOM.Simulator.FilterWheel")。

        Returns:
            True 连接成功，False 失败。
        """
        return self._connect_device(device_id, DEVICE_TYPE_FILTER_WHEEL)

    def connect_weather(self, device_id: str) -> bool:
        """连接气象站。

        Args:
            device_id: 气象站设备 ProgID (如 "ASCOM.Simulator.WeatherData")。

        Returns:
            True 连接成功，False 失败。
        """
        return self._connect_device(device_id, DEVICE_TYPE_WEATHER)

    # ============================================================
    # Internal Connection Logic
    # ============================================================

    def _connect_device(self, device_id: str, device_type: str) -> bool:
        """内部通用设备连接方法。

        Args:
            device_id: 设备 ProgID。
            device_type: 设备类型。

        Returns:
            True 连接成功，False 失败。
        """
        with self._lock:
            if not self._initialized:
                log.error("ASCOM 平台未初始化，无法连接设备")
                return False

            if device_id in self._devices:
                existing = self._devices[device_id]
                if existing.status == STATUS_CONNECTED:
                    log.info(f"设备已连接: {device_id}")
                    return True
                log.info(f"重新连接设备: {device_id}")

            device = ASCOMDevice(device_id=device_id, device_type=device_type)

            try:
                if self._platform == "windows" and self._com_available:
                    import win32com.client  # type: ignore[import-not-found]

                    device.status = STATUS_CONNECTING
                    log.info(f"正在通过 COM 连接 {device_type}: {device_id}")

                    device.connection = win32com.client.Dispatch(device_id)
                    device.connection.Connected = True

                    device.name = getattr(device.connection, "Name", device_id)
                    device.driver_info = getattr(device.connection, "DriverInfo", "")
                    device.status = STATUS_CONNECTED

                elif self._alpaca_available:
                    import requests  # type: ignore[import-not-found]

                    device.status = STATUS_CONNECTING
                    device_number = self._alpaca_find_device(device_id, device_type)
                    url = f"{self._alpaca_base_url}/{device_type}s/{device_number}/connected"
                    log.info(f"正在通过 Alpaca 连接 {device_type}: {device_id}")

                    resp = requests.put(url, json={"ClientID": 0, "ClientTransactionID": 1, "Connected": True}, timeout=10)
                    resp.raise_for_status()

                    device.connection = {"device_number": device_number, "type_endpoint": device_type}
                    device.name = device_id
                    device.status = STATUS_CONNECTED

                else:
                    log.error("无可用的 ASCOM 平台后端 (COM/Alpaca)")
                    device.status = STATUS_ERROR
                    device.error_message = "No ASCOM platform backend available"

                if device.status == STATUS_CONNECTED:
                    self._load_capabilities(device)
                    self._devices[device_id] = device
                    log.info(f"设备连接成功: {device_type} - {device.name} ({device_id})")
                    return True
                else:
                    self._devices[device_id] = device
                    return False

            except Exception as e:
                device.status = STATUS_ERROR
                device.error_message = str(e)
                self._devices[device_id] = device
                log.error(f"设备连接失败 [{device_type}] {device_id}: {e}")
                return False

    def _alpaca_find_device(self, device_id: str, device_type: str) -> int:
        """通过 Alpaca 发现设备编号。

        Args:
            device_id: 设备 ProgID。
            device_type: 设备类型。

        Returns:
            设备编号 (integer)。
        """
        import requests  # type: ignore[import-not-found]

        url = f"{self._alpaca_base_url}/management/apidevices"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()

        devices = resp.json().get("Value", [])
        for dev in devices:
            if dev.get("DeviceType", "").lower() == device_type.lower():
                return dev.get("DeviceNumber", 0)

        log.warning(f"未找到 Alpaca 设备: {device_id} ({device_type}), 返回默认编号 0")
        return 0

    def _load_capabilities(self, device: ASCOMDevice) -> None:
        """加载设备能力信息。

        Args:
            device: 已连接的 ASCOMDevice 实例。
        """
        if device.connection is None:
            return

        try:
            device.capabilities = self._get_capabilities_internal(device)
        except Exception as e:
            log.warning(f"获取设备能力失败 [{device.device_id}]: {e}")
            device.capabilities = {}

    # ============================================================
    # Status & Capabilities
    # ============================================================

    def get_device_status(self, device_id: str) -> dict[str, Any]:
        """获取设备状态。

        Args:
            device_id: 设备 ProgID。

        Returns:
            设备状态字典，包含 status, name, type, capabilities 等字段。
            设备不存在时返回基础状态。
        """
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                log.warning(f"设备状态查询失败，设备不存在: {device_id}")
                return {
                    "device_id": device_id,
                    "status": STATUS_DISCONNECTED,
                    "name": "",
                    "device_type": "unknown",
                    "capabilities": {},
                    "error_message": "Device not found",
                }

            # 实时更新 COM 设备的连接状态
            if device.connection is not None and self._platform == "windows" and self._com_available:
                try:
                    device.status = STATUS_CONNECTED if getattr(device.connection, "Connected", False) else STATUS_DISCONNECTED
                except Exception:
                    pass

            return device.to_dict()

    def list_devices(self) -> list[dict[str, Any]]:
        """列出所有 ASCOM 设备。

        Returns:
            所有已注册设备的状态信息列表。
        """
        with self._lock:
            return [device.to_dict() for device in self._devices.values()]

    def get_capabilities(self, device_id: str) -> dict[str, Any]:
        """获取设备能力。

        Args:
            device_id: 设备 ProgID。

        Returns:
            设备能力字典。设备不存在或未连接时返回空字典。
        """
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                log.warning(f"设备能力查询失败，设备不存在: {device_id}")
                return {}

            if device.status != STATUS_CONNECTED:
                log.warning(f"设备未连接，无法获取能力: {device_id}")
                return {}

            try:
                return self._get_capabilities_internal(device)
            except Exception as e:
                log.error(f"获取设备能力异常 [{device_id}]: {e}")
                return {}

    def _get_capabilities_internal(self, device: ASCOMDevice) -> dict[str, Any]:
        """内部获取设备能力实现。

        Args:
            device: ASCOMDevice 实例。

        Returns:
            设备能力字典。
        """
        capabilities: dict[str, Any] = {}

        if device.connection is None:
            return capabilities

        try:
            if self._platform == "windows" and self._com_available:
                conn = device.connection

                # 通用能力
                for prop in [
                    "Name",
                    "Description",
                    "DriverInfo",
                    "DriverVersion",
                    "Connected",
                ]:
                    try:
                        capabilities[prop.lower()] = getattr(conn, prop, None)
                    except Exception:
                        pass

                # 望远镜特定能力
                if device.device_type == DEVICE_TYPE_TELESCOPE:
                    for prop in [
                        "CanSetTrack",
                        "CanSlew",
                        "CanSlewAsync",
                        "CanPark",
                        "CanFindHome",
                        "CanSetDEC",
                        "CanSetRA",
                        "CanSetPierSide",
                        "EquatorialSystem",
                        "SiteElevation",
                        "SiteLatitude",
                        "SiteLongitude",
                    ]:
                        try:
                            capabilities[prop] = getattr(conn, prop, None)
                        except Exception:
                            pass

                # 圆顶特定能力
                elif device.device_type == DEVICE_TYPE_DOME:
                    for prop in ["CanFindHome", "CanPark", "CanSetAltitude", "CanSetAzimuth", "CanSlave", "CanSetShutter"]:
                        try:
                            capabilities[prop] = getattr(conn, prop, None)
                        except Exception:
                            pass

                # 调焦器特定能力
                elif device.device_type == DEVICE_TYPE_FOCUSER:
                    for prop in [
                        "CanSetTemperature",
                        "CanAbort",
                        "MaxIncrement",
                        "MaxStep",
                        "StepSize",
                        "TempComp",
                        "TempCompAvailable",
                    ]:
                        try:
                            capabilities[prop] = getattr(conn, prop, None)
                        except Exception:
                            pass

                # 滤镜轮特定能力
                elif device.device_type == DEVICE_TYPE_FILTER_WHEEL:
                    try:
                        capabilities["num_positions"] = getattr(conn, "NumPositions", None)
                        capabilities["can_set_offset"] = getattr(conn, "CanSetOffset", None)
                    except Exception:
                        pass

                # 气象站特定能力
                elif device.device_type == DEVICE_TYPE_WEATHER:
                    for prop in [
                        "AscomCloudCon",
                        "AscomDewCon",
                        "AscomHumidity",
                        "AscomPressure",
                        "AscomRainRate",
                        "AscomSkyBrightness",
                        "AscomSkyQuality",
                        "AscomSkyTemperature",
                        "AscomStarFWHM",
                        "AscomTemperature",
                        "AscomWindDirection",
                        "AscomWindGust",
                        "AscomWindSpeed",
                    ]:
                        try:
                            capabilities[prop] = getattr(conn, prop, None)
                        except Exception:
                            pass

            elif self._alpaca_available:
                # Alpaca 通过元数据获取能力
                import requests  # type: ignore[import-not-found]

                device_number = device.connection.get("device_number", 0) if device.connection else 0
                type_endpoint = device.connection.get("type_endpoint", "telescope") if device.connection else "telescope"

                metadata_url = f"{self._alpaca_base_url}/{type_endpoint}s/{device_number}/metadata"
                resp = requests.get(metadata_url, timeout=10)
                if resp.status_code == 200:
                    capabilities["metadata"] = resp.json().get("Value", {})

        except Exception as e:
            log.warning(f"获取内部能力失败 [{device.device_id}]: {e}")

        return capabilities

    # ============================================================
    # Disconnect
    # ============================================================

    def disconnect(self, device_id: str) -> bool:
        """断开设备连接。

        Args:
            device_id: 设备 ProgID。

        Returns:
            True 断开成功，False 设备不存在或断开失败。
        """
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                log.warning(f"断开设备失败，设备不存在: {device_id}")
                return False

            if device.status == STATUS_DISCONNECTED:
                log.info(f"设备已断开: {device_id}")
                return True

            try:
                if device.connection is not None:
                    if self._platform == "windows" and self._com_available:
                        setattr(device.connection, "Connected", False)

                    elif self._alpaca_available:
                        import requests  # type: ignore[import-not-found]

                        device_number = device.connection.get("device_number", 0)
                        type_endpoint = device.connection.get("type_endpoint", "telescope")
                        url = f"{self._alpaca_base_url}/{type_endpoint}s/{device_number}/connected"
                        requests.put(url, json={"ClientID": 0, "ClientTransactionID": 1, "Connected": False}, timeout=10)

                device.status = STATUS_DISCONNECTED
                device.connection = None
                log.info(f"设备已断开: {device.device_type} - {device.name} ({device_id})")
                return True

            except Exception as e:
                log.error(f"断开设备失败 [{device_id}]: {e}")
                device.error_message = str(e)
                return False

    def disconnect_all(self) -> None:
        """断开所有已连接的设备。"""
        with self._lock:
            device_ids = list(self._devices.keys())

        for device_id in device_ids:
            self.disconnect(device_id)

        log.info("所有 ASCOM 设备已断开")

    # ============================================================
    # Platform Info
    # ============================================================

    @property
    def platform(self) -> str:
        """当前 ASCOM 平台类型。

        Returns:
            平台类型字符串 (windows/linux)。
        """
        return self._platform

    @property
    def is_initialized(self) -> bool:
        """ASCOM 平台是否初始化成功。

        Returns:
            True 已初始化，False 未初始化。
        """
        return self._initialized
