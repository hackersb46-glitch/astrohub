"""
M2 Device Manager v1.0 - 全局常量定义

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "DEVICE"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "log"
BACKUP_DIR = BASE_DIR / "backup"

# === 数据文件 ===
DEVICES_FILE = DATA_DIR / "devices.json"
GROUPS_FILE = DATA_DIR / "groups.json"
STATUS_HISTORY_FILE = DATA_DIR / "status_history.json"
OPERATIONS_LOG_INDEX = DATA_DIR / "ops_log_index.json"

# === MAC 格式 ===
MAC_PATTERN = r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$|^[0-9A-Fa-f]{12}$"
MAC_NORMALIZED_FORMAT = "XX:XX:XX:XX:XX:XX"

# === 心跳参数 (P1.3) ===
HEARTBEAT_DEFAULT_INTERVAL = 30  # 秒
HEARTBEAT_MIN_INTERVAL = 5       # 秒
HEARTBEAT_MAX_INTERVAL = 300     # 秒
HEARTBEAT_CONSECUTIVE_THRESHOLD = 3  # 连续N次确认状态变更

# === 在线检测 (P1.1) ===
ONLINE_CHECK_TIMEOUT = 5  # 秒
ONLINE_CHECK_ENDPOINT = "/ISAPI/System/deviceInfo"

# === 设备状态流转 (P5) ===
class DeviceStatus(Enum):
    NEW = "new"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"

# 有效的状态流转
VALID_TRANSITIONS = {
    "new": ["active"],
    "active": ["inactive"],
    "inactive": ["active", "deleted"],
}

# === 心跳状态 (P1) ===
class HeartbeatStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"

# === 日志级别 (P4.1) ===
ACCEPTED_LOG_LEVELS = {"info", "warning", "error", "done", "failed"}

# === 告警级别 (P1.5) ===
class AlertLevel(Enum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

# === 异常类型 (P1.5) ===
class AnomalyType(Enum):
    AUTH_FAILED = "auth_failed"
    CONNECTION_TIMEOUT = "connection_timeout"
    DEVICE_FAULT = "device_fault"
    NETWORK_UNREACHABLE = "network_unreachable"

# === HTTP 状态码映射 ===
HTTP_STATUS_DESCRIPTION = {
    200: "设备在线",
    401: "认证失败",
    500: "设备故障",
    0: "网络不可达或超时",
}

# === 配置版本管理 (P2.6) ===
CONFIG_VERSION_MAX_COUNT = 10  # 最多保留版本数
CONFIG_VERSION_FILENAME = "config_{mac}_{version}_{timestamp}.json"
CONFIG_BACKUP_FILENAME = "config_{mac}_{timestamp}.json"

# === 日志轮转 (P4.1) ===
LOG_RETENTION_DAYS = 30  # 默认保留天数

# === 设备模型默认值 ===
DEFAULT_DEVICE_PORT = 80
DEFAULT_HEARTBEAT_INTERVAL = HEARTBEAT_DEFAULT_INTERVAL

# === 分页默认值 (P4.2) ===
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500
