"""
M4 Calibration Service v1.0 - 全局常量定义

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "CALIBRATION"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "log"

# === 校准数据文件 ===
CALIBRATION_DATA_FILE = DATA_DIR / "calibration_data.json"

# === 校准状态机 (P0.2) ===
class CalibrationState(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    CALIBRATING = "calibrating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"

# 有效的状态流转
VALID_CALIBRATION_TRANSITIONS = {
    "idle": ["preparing"],
    "preparing": ["calibrating", "failed"],
    "calibrating": ["verifying", "failed"],
    "verifying": ["completed", "failed"],
}

# === 校准步骤 (P0.1) ===
class CalibrationStep(Enum):
    AUTO_FOCUS = "auto_focus"
    COLOR_BALANCE = "color_balance"
    SPEED_MAPPING = "speed_mapping"
    POSITION_CALIBRATION = "position_calibration"

# === 校准结果状态 ===
class CalibrationResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"

# === 自动对焦 (P1) ===
FOCUS_RANGE_MIN = 1
FOCUS_RANGE_MAX = 100
FOCUS_TEST_POINTS = 5
FOCUS_ACCURACY_THRESHOLD = 0.05  # 5%
FOCUS_RESTORE_THRESHOLD = 0.01   # 1%
FOCUS_MAX_TIME = 10  # 秒

# === 色彩平衡 (P2) ===
TEMP_MIN = 2800   # K
TEMP_MAX = 6500   # K
DELTA_E_THRESHOLD = 10

# 标准色卡 (简化版 - 8色)
STANDARD_COLOR_BLOCKS = [
    {"name": "white", "r": 255, "g": 255, "b": 255},
    {"name": "black", "r": 0, "g": 0, "b": 0},
    {"name": "red", "r": 255, "g": 0, "b": 0},
    {"name": "green", "r": 0, "g": 255, "b": 0},
    {"name": "blue", "r": 0, "g": 0, "b": 255},
    {"name": "yellow", "r": 255, "g": 255, "b": 0},
    {"name": "cyan", "r": 0, "g": 255, "b": 255},
    {"name": "magenta", "r": 255, "g": 0, "b": 255},
]

# === 速度映射 (P3) ===
SPEED_TEST_LEVELS = [1, 50, 100]
SPEED_TEST_DURATION_SECONDS = 2  # 每档移动2秒
SPEED_CURVE_R2_THRESHOLD = 0.9
SPEED_ACCURACY_THRESHOLD = 0.05  # 5%

# === 位置校准 (P4) ===
POSITION_DEVIATION_THRESHOLD = 10  # P/T偏差
POSITION_COMPENSATED_THRESHOLD = 5  # 补偿后偏差
POSITION_TEST_POINTS = 10
POSITION_PASS_RATE = 0.90  # 90%

# === 日志级别 ===
ACCEPTED_LOG_LEVELS = {"info", "warning", "error", "done", "failed"}

# === 分页默认值 ===
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
