"""
AstroHub v2.0 - 统一配置管理

集中管理所有配置项，支持环境变量覆盖。
路径基于 config_paths 动态计算 (支持 PyInstaller 打包)。
"""

from __future__ import annotations

import warnings
warnings.warn(
    "src/config.py is deprecated. Use 'src/main/core/config_merger.py' instead. "
    "Will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

import os
import secrets
from typing import Any

from src.config_paths import (
    DATA_DIR,
    DB_DIR,
    LOG_DIR,
    CONFIG_DIR,
    ensure_directories as _ensure_dirs,
)

# === 服务端配置 ===
HOST = os.getenv("ASTROHUB_HOST", "0.0.0.0")
PORT = int(os.getenv("ASTROHUB_PORT", "10280"))

# === 数据库配置 ===
DATABASE_URL = os.getenv(
    "ASTROHUB_DATABASE_URL",
    f"sqlite+aiosqlite:///{DB_DIR / 'astrohub.db'}",
)
POOL_SIZE = int(os.getenv("ASTROHUB_DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("ASTROHUB_DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT = int(os.getenv("ASTROHUB_DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("ASTROHUB_DB_POOL_RECYCLE", "3600"))

# === 日志配置 ===
LOG_LEVEL = os.getenv("ASTROHUB_LOG_LEVEL", "INFO")
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# === 认证配置 ===
SECRET_KEY = os.getenv("ASTROHUB_SECRET_KEY", secrets.token_hex(32))
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ASTROHUB_TOKEN_EXPIRE", "1440"))

# === 桌面窗口配置 ===
WINDOW_TITLE = os.getenv("ASTROHUB_WINDOW_TITLE", "AstroHub")
WINDOW_WIDTH = int(os.getenv("ASTROHUB_WINDOW_WIDTH", "1600"))
WINDOW_HEIGHT = int(os.getenv("ASTROHUB_WINDOW_HEIGHT", "900"))

# === 应用元信息 ===
VERSION = "2.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "AstroHub"


def ensure_directories() -> None:
    """确保所有运行时目录存在。"""
    _ensure_dirs()


def get_config_dict() -> dict[str, Any]:
    """返回当前配置快照（用于调试/日志）。"""
    return {
        "host": HOST,
        "port": PORT,
        "database_url": DATABASE_URL,
        "secret_key_set": bool(SECRET_KEY),
        "window_size": f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}",
        "log_level": LOG_LEVEL,
    }
