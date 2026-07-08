"""
M9 ASCOM v1.0 - 全局常量定义

ASCOM 天文设备集成: 望远镜连接、Slew 控制、位置查询、跟踪模式、
相机控制、曝光、焦点器步进、温度补偿。

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "ASCOM"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "log"

# === 服务配置 ===
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8009

# === ASCOM 平台检测 (P0) ===
ASCOM_PLATFORM_REG_KEY = r"SOFTWARE\ASCOM"
ASCOM_PLATFORM_MIN_VERSION = "6.5"

# === 连接超时 (P0.3) ===
CONNECT_TIMEOUT_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 30

# === 望远镜默认值 (P1) ===
DEFAULT_TRACKING_MODE = "trackSidereal"
SLEW_TIMEOUT_SECONDS = 120
MAX_SLEW_RATE_DEG_PER_SEC = 4.0  # 最大旋转速率

# === 焦点器默认值 (P3) ===
FOCUSER_DEFAULT_POSITION = 0
FOCUSER_TEMP_COMPENSATION_ENABLED = False
FOCUSER_TEMP_STEP_PER_DEGREE = 10  # 每度温度补偿步数

# === 气象站阈值 ===
WEATHER_SAFE_WIND_SPEED = 25.0  # m/s, 安全风速上限
WEATHER_SAFE_HUMIDITY = 85.0   # %, 安全湿度上限
WEATHER_POLL_INTERVAL = 5      # 秒, 数据轮询间隔


# ================================================================== #
#  设备类型枚举
# ================================================================== #

class DeviceType(Enum):
    """ASCOM 设备类型。"""
    TELESCOPE = "telescope"
    CAMERA = "camera"
    FOCUSER = "focuser"
    DOME = "dome"
    FILTER_WHEEL = "filter_wheel"
    WEATHER_STATION = "weather_station"


# ================================================================== #
#  跟踪模式 (P1.4)
# ================================================================== #

class TrackingMode(Enum):
    """望远镜跟踪模式。"""
    SIDEREAL = "trackSidereal"
    LUNAR = "trackLunar"
    SOLAR = "trackSolar"
    OFF = "trackOff"


# ================================================================== #
#  望远镜状态 (P1.1)
# ================================================================== #

class TelescopeStatus(Enum):
    """望远镜运行状态。"""
    IDLE = "idle"
    SLEWING = "slewing"
    TRACKING = "tracking"
    HOMING = "homing"
    PARKED = "parked"
    ERROR = "error"


# ================================================================== #
#  圆顶设备方向
# ================================================================== #

class DomeDirection(Enum):
    """圆顶旋转方向。"""
    CLOCKWISE = 1
    COUNTERCLOCKWISE = 0


# ================================================================== #
#  错误码 (P0.3)
# ================================================================== #

class ErrorCode(Enum):
    """ASCOM 错误码。"""
    # 通用
    SUCCESS = "ASCOM_SUCCESS"
    INTERNAL_ERROR = "ASCOM_INTERNAL_ERROR"
    NOT_CONNECTED = "ASCOM_NOT_CONNECTED"
    INVALID_DEVICE_ID = "ASCOM_INVALID_DEVICE_ID"

    # ASCOM 平台
    PLATFORM_NOT_INSTALLED = "ASCOM_PLATFORM_NOT_INSTALLED"
    PLATFORM_VERSION_TOO_LOW = "ASCOM_PLATFORM_VERSION_TOO_LOW"

    # 连接
    CONNECTION_FAILED = "ASCOM_CONNECTION_FAILED"
    CONNECTION_TIMEOUT = "ASCOM_CONNECTION_TIMEOUT"
    DISCONNECT_FAILED = "ASCOM_DISCONNECT_FAILED"

    # 望远镜 (P1)
    TELESCOPE_SLEW_FAILED = "ASCOM_TELESCOPE_SLEW_FAILED"
    TELESCOPE_SLEW_TIMEOUT = "ASCOM_TELESCOPE_SLEW_TIMEOUT"
    TELESCOPE_ABORT_FAILED = "ASCOM_TELESCOPE_ABORT_FAILED"
    TELESCOPE_PARK_FAILED = "ASCOM_TELESCOPE_PARK_FAILED"
    TELESCOPE_UNPARK_FAILED = "ASCOM_TELESCOPE_UNPARK_FAILED"
    TELESCOPE_INVALID_COORDS = "ASCOM_TELESCOPE_INVALID_COORDS"
    TELESCOPE_NOT_HOMED = "ASCOM_TELESCOPE_NOT_HOMED"

    # 相机 (P2)
    CAMERA_EXPOSURE_FAILED = "ASCOM_CAMERA_EXPOSURE_FAILED"
    CAMERA_NOT_READY = "ASCOM_CAMERA_NOT_READY"
    CAMERA_TEMPERATURE_ERROR = "ASCOM_CAMERA_TEMPERATURE_ERROR"

    # 焦点器 (P3)
    FOCUSER_MOVE_FAILED = "ASCOM_FOCUSER_MOVE_FAILED"
    FOCUSER_NOT_SUPPORTED = "ASCOM_FOCUSER_NOT_SUPPORTED"
    FOCUSER_TEMPERATURE_ERROR = "ASCOM_FOCUSER_TEMPERATURE_ERROR"

    # 数据无效
    INVALID_COORDINATES = "ASCOM_INVALID_COORDINATES"
    INVALID_PARAMETER = "ASCOM_INVALID_PARAMETER"


# 错误码描述
ERROR_CODE_DESCRIPTION = {
    ErrorCode.SUCCESS: "操作成功",
    ErrorCode.INTERNAL_ERROR: "ASCOM 服务器内部错误",
    ErrorCode.NOT_CONNECTED: "设备未连接",
    ErrorCode.INVALID_DEVICE_ID: "无效的驱动 ID",
    ErrorCode.PLATFORM_NOT_INSTALLED: "ASCOM Platform 未安装",
    ErrorCode.PLATFORM_VERSION_TOO_LOW: "ASCOM Platform 版本过低",
    ErrorCode.CONNECTION_FAILED: "连接失败",
    ErrorCode.CONNECTION_TIMEOUT: "连接超时",
    ErrorCode.DISCONNECT_FAILED: "断开连接失败",
    ErrorCode.TELESCOPE_SLEW_FAILED: "望远镜 Slew 失败",
    ErrorCode.TELESCOPE_SLEW_TIMEOUT: "望远镜 Slew 超时",
    ErrorCode.TELESCOPE_ABORT_FAILED: "取消 Slew 失败",
    ErrorCode.TELESCOPE_PARK_FAILED: "望远镜归位失败",
    ErrorCode.TELESCOPE_UNPARK_FAILED: "望远镜解除归位失败",
    ErrorCode.TELESCOPE_INVALID_COORDS: "无效的赤经/赤纬坐标",
    ErrorCode.TELESCOPE_NOT_HOMED: "望远镜未归位",
    ErrorCode.CAMERA_EXPOSURE_FAILED: "相机曝光失败",
    ErrorCode.CAMERA_NOT_READY: "相机未就绪",
    ErrorCode.CAMERA_TEMPERATURE_ERROR: "相机温度异常",
    ErrorCode.FOCUSER_MOVE_FAILED: "焦点器移动失败",
    ErrorCode.FOCUSER_NOT_SUPPORTED: "焦点器功能不支持",
    ErrorCode.FOCUSER_TEMPERATURE_ERROR: "焦点器温度读取失败",
    ErrorCode.INVALID_COORDINATES: "坐标格式无效",
    ErrorCode.INVALID_PARAMETER: "参数无效",
}


# ================================================================== #
#  连接状态枚举
# ================================================================== #

class ConnectionStatus(Enum):
    """设备连接状态。"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
