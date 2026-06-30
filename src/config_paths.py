"""
src/config_paths.py - Portable 动态路径管理

所有路径相对于主程序目录 (APP_DIR)，支持 PyInstaller 打包。
Portable 应用规范：整个程序是 Portable 应用，所有路径相对于主程序目录。
"""

from __future__ import annotations

import warnings
warnings.warn(
    "src/config_paths.py is deprecated. Use 'src/main/core/config_merger.py' instead. "
    "Will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """获取主程序所在目录（支持 PyInstaller 打包）。

    开发模式: 返回 src/ 的父目录（即项目根目录）
    PyInstaller 模式: 返回可执行文件所在目录 (dist/AstroHub/)
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_meipass_dir() -> Path | None:
    """获取 PyInstaller 运行时临时目录（仅打包模式可用）。"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return None


def get_sdk_root() -> Path:
    """获取 SDK 根目录（SDK/，程序匹配下一层品牌目录如 SDK/HIK/）。"""
    return get_app_dir() / 'SDK'


# ============================================================
# 应用根目录
# ============================================================
APP_DIR = get_app_dir()

# ============================================================
# 数据目录 (全部基于 APP_DIR/data/)
# ============================================================
DATA_DIR = APP_DIR / 'data'
LOG_DIR = APP_DIR / 'log'
CONFIG_DIR = DATA_DIR / 'config'
DB_DIR = DATA_DIR / 'db'
RECORD_DIR = DATA_DIR / 'records'
REPORT_DIR = DATA_DIR / 'reports'
DOWNLOAD_DIR = DATA_DIR / 'downloads'
HLS_DIR = DATA_DIR / 'hls'
CALIBRATION_DIR = DATA_DIR / 'calibration'

# v6.03: 新数据结构路径
SYSTEM_FILE = DATA_DIR / 'system.json'       # 本机系统信息
REGISTRY_FILE = DATA_DIR / 'registry.json'   # 设备注册表
DEVICES_DIR = DATA_DIR / 'devices'           # 设备数据目录

# ============================================================
# DLL 路径 (SADP)
# ============================================================
# 开发模式下 SDK libs 目录
SDK_LIBS_DIR = get_sdk_root()

# ============================================================
# 所有需要创建的目录列表
# ============================================================
ALL_DATA_DIRS = [
    DATA_DIR,
    LOG_DIR,
    CONFIG_DIR,
    DB_DIR,
    RECORD_DIR,
    REPORT_DIR,
    DOWNLOAD_DIR,
    HLS_DIR,
    CALIBRATION_DIR,
    DEVICES_DIR,
]


def ensure_directories() -> None:
    """确保所有运行时目录存在（首次运行自动创建）。"""
    for directory in ALL_DATA_DIRS:
        directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# PyInstaller 静态资源路径
# ============================================================

def get_web_dir() -> Path:
    """获取 web 静态资源目录。"""
    meipass = get_meipass_dir()
    if meipass:
        return meipass / 'src' / 'web'
    return Path(__file__).resolve().parent / 'web'


def get_index_html() -> Path:
    """获取 index.html 路径。"""
    return get_web_dir() / 'index.html'
