"""
M6 Web UI Service v1.0 - 全局常量定义

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "WEBUI"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "log"
STATIC_DIR = BASE_DIR / "static"
BUILD_DIR = BASE_DIR / "build"

# === 服务配置 ===
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8002

# === 静态文件配置 ===
SPA_INDEX = "index.html"
STATIC_PATHS = ["/assets", "/images", "/fonts"]

# === 分页默认值 ===
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# === 健康状态 ===
class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

# === 通知等级 ===
class NotificationLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"

# === 仪表盘配置 ===
DASHBOARD_REFRESH_INTERVAL = 30  # 秒
MAX_NOTIFICATION_COUNT = 100

# === Database Service 连接 ===
DATABASE_URL = "http://localhost:8001"
