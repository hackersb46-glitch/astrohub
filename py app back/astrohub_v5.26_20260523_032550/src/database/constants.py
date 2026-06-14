"""
Database Service v1.0 - 全局常量定义

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "DATABASE"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "log"

# === 数据库配置 ===
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'database.db'}"
DATABASE_BACKUP_DIR = DATA_DIR / "backups"

# === 连接池配置 ===
POOL_SIZE = 5
MAX_OVERFLOW = 10
POOL_TIMEOUT = 30
POOL_RECYCLE = 3600

# === 设备状态 (P1.5) ===
class DeviceStatus(Enum):
    NEW = "new"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"

# === 观测数据类型 ===
class ObservationType(Enum):
    EVENT = "event"
    CSV_IMPORT = "csv_import"
    MANUAL = "manual"

# === 操作日志级别 ===
class LogLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

# === 配置版本管理 (P2.6) ===
CONFIG_VERSION_MAX_COUNT = 10

# === 分页默认值 ===
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# === MAC 格式 ===
MAC_PATTERN = r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$|^[0-9A-Fa-f]{12}$"

# === 时序数据清理策略 ===
OBSERVATION_RETENTION_DAYS = 365
