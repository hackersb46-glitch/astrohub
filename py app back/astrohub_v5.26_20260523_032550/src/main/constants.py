"""
M12 Unified Integration v1.0 - 全局常量定义

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "MAIN"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent

# === M1-M11 模块初始化顺序 ===
MODULE_ORDER = [
    "ptz",
    "device",
    "stream",
    "calibration",
    "database",
    "webui",
    "rest_api",
    "websocket",
    "ascom",
    "integration",
    "deployment",
]


# === 健康状态枚举 ===
class HealthStatus(Enum):
    """模块健康状态。"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
