"""
M12 Unified Integration v1.0 - 全局常量定义

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

# === 版本与作者 ===
VERSION = "v7.40"
VERSION_NUM = "7.17"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "MAIN"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent

# === M1-M11 模块初始化顺序 ===
# v7.12: 精简后保留的模块
# 注意: device 模块已整合到 src/core/device_manager.py
MODULE_ORDER = [
    "ptz",
    "stream",
    "calibration",
    "database",
    "websocket",
    "ascom",
]


# === 健康状态枚举 ===
class HealthStatus(Enum):
    """模块健康状态。"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
