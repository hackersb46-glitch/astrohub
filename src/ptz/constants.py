"""
PTZ_ASTRO v1.1 - 全局常量定义
Author: 雅痞张@南方天文
"""

from pathlib import Path

# === 版本与作者 ===
VERSION = "v1.1"
VERSION_NUM = "1.1"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "PTZ_ASTRO"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 项目根目录 (ASTRO_PY/astro_hub)
LOG_DIR = BASE_DIR / "log"
RECORD_DIR = BASE_DIR / "record"
REPORT_DIR = BASE_DIR / "report"
DOWNLOAD_DIR = BASE_DIR / "download"
DOWNLOAD_IMAGE_DIR = DOWNLOAD_DIR / "image"
DOWNLOAD_H264_DIR = DOWNLOAD_DIR / "H264"
DOWNLOAD_H265_DIR = DOWNLOAD_DIR / "H265"

# === 配置文件 ===
LOCAL_CONFIG_PATH = BASE_DIR / "local.json"
PTZ_CONFIG_PATH = BASE_DIR / "PTZ_config.json"

# === SADP ===
SADP_MULTICAST_ADDR = "239.255.255.250"
SADP_PORT = 37020
SADP_TIMEOUT_MS = 10000  # 10秒扫描超时

# === ISAPI ===
ISAPI_CHANNEL = 1
DEFAULT_PTZ_PRESET = 10
HOME_COORDS = {"pan": 1800, "tilt": 450, "zoom": 10}
DEFAULT_IP_SUFFIX = 64

# === PTZ控制 ===
PTZ_MAX_SPEED = 100
PTZ_MIN_SPEED = 1
STABILIZATION_SECONDS = 2
STABLE_POINTS_REQUIRED = 20
STABLE_POINT_DEVIATION = 0  # 0偏差要求

# === 采样频率 ===
SAMPLE_INTERVAL = 0.1  # 0.1秒采样一次

# === 已知Hikvision MAC OUI前缀 ===
HIKVISION_MAC_OUI = {
    "28:57:BE",
    "4C:BD:8F",
    "54:C4:15",
    "C0:56:E3",
    "E0:50:8B",
}

# === 测试阶段默认凭据（不写死在代码中，由用户输入） ===
DEFAULT_USERNAME = "admin"

# === 打包目标路径 ===
PACKAGE_DEST = Path("D:/PY APP/TBD")
