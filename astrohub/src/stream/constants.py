"""
M3 Stream Service v1.0 - 全局常量定义

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "STREAM"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "log"
# Wave 4: 磁盘验证路径 (必须写入真实位置)
PROJECT_ROOT = BASE_DIR.parent.parent  # astro_hub/
DOWNLOAD_DIR = PROJECT_ROOT / "download"
RECORD_DIR = PROJECT_ROOT / "record"
DOWNLOAD_IMAGE_DIR = DOWNLOAD_DIR / "image"

# 确保目录存在
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
RECORD_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

# === RTSP 默认值 (P0.1) ===
RTSP_DEFAULT_PORT = 554
RTSP_URL_PATTERN = r"^(?:rtsp|rtsps)://(?:(?P<username>[^:]*):(?P<password>[^@]*)@)?(?P<host>[^:/]+)(?::(?P<port>\d+))?(?P<path>/[^?]*)"

# Hikvision ISAPI RTSP URL 模板
RTSP_HIKVISION_CHANNELS = {
    101: "Streaming/Channels/101",   # H264 主码流
    102: "Streaming/Channels/102",   # H264 子码流
    201: "Streaming/Channels/201",   # H265 主码流
    202: "Streaming/Channels/202",   # H265 子码流
}
RTSP_HIKVISION_TEMPLATE = "rtsp://{ip}:{port}/Streaming/Channels/{channel}"

# === ONVIF 默认值 (P0.2) ===
ONVIF_MULTICAST_ADDR = "239.255.255.250"
ONVIF_MULTICAST_PORT = 3702
ONVIF_DISCOVERY_TIMEOUT = 10  # 秒
ONVIF_MAX_PROFILE_COUNT = 4

# === 协议类型 (P0.4) ===
class ProtocolType(Enum):
    RTSP = "rtsp"
    ONVIF = "onvif"
    HTTP_FLV = "http-flv"

# === 编码格式 (P1.1) ===
class CodecFormat(Enum):
    H264 = "h264"
    H265 = "h265"
    MJPEG = "mjpeg"
    UNKNOWN = "unknown"

# === 输出分辨率预设 (P1.3) ===
class Resolution(Enum):
    HD_1080 = "1920x1080"
    HD_720 = "1280x720"
    SD_480 = "854x480"

# === 码率控制模式 (P1.4) ===
class BitrateMode(Enum):
    CBR = "cbr"
    VBR = "vbr"

DEFAULT_BITRATE = 2000  # kbps
MIN_BITRATE = 500       # kbps
MAX_BITRATE = 8000      # kbps
BITRATE_TOLERANCE_PCT = 0.10  # ±10%

# === 并发控制 (P2.4) ===
DEFAULT_CONCURRENT_STREAMS = 4
MAX_CONCURRENT_STREAMS = 16

# === HLS 配置 (P2.3) ===
HLS_SEGMENT_DURATION = 3     # 秒 per ts segment
HLS_LIST_SIZE = 5            # m3u8保留的最大切片数
HLS_SEGMENT_REMOVAL_DELAY = 30  # 秒, 旧切片清理延迟

# === WebSocket 配置 (P2.1) ===
WS_MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB
WS_PING_INTERVAL = 20              # 秒

# === 延迟优化 (P3.2) ===
TARGET_LATENCY_MS = 1000        # 端到端延迟目标：<1秒
FFMPEG_LOW_LATENCY_FLAGS = [
    "-fflags", "nobuffer",
    "-flags", "low_delay",
    "-strict", "experimental",
    "-analyzeduration", "0",
    "-probesize", "32",
    "-framedrop", "1",
]

# === 断流检测 (P4.1) ===
STREAM_DISCONNECT_THRESHOLD = 10  # 秒，数据未到达超过此值判定断流
STREAM_CHECK_INTERVAL = 2         # 秒，检查间隔
MISJUDGEMENT_THRESHOLD = 0.01     # 误判率 <1%

# === 重连策略 (P4.2) ===
RECONNECT_INITIAL_INTERVAL = 3    # 秒
RECONNECT_MAX_INTERVAL = 30       # 秒
RECONNECT_MAX_ATTEMPTS = 5
RECONNECT_BACKOFF_MULTIPLIER = 2

# === 状态上报 (P4.3) ===
STATUS_REPORT_INTERVAL = 30       # 秒
STATUS_FIELDS = ["stream_id", "status", "bitrate", "resolution", "fps", "latency_ms", "client_count"]

# === 流状态 ===
class StreamStatus(Enum):
    CONNECTING = "connecting"
    ACTIVE = "active"
    TRANSCODING = "transcoding"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    STOPPED = "stopped"

# === 录制格式 (P5.1) ===
class RecordFormat(Enum):
    MP4 = "mp4"
    FLV = "flv"

DEFAULT_RECORD_FORMAT = RecordFormat.MP4
RECORD_SEGMENT_DURATION = 3600     # 秒，按时间分段
RECORD_SEGMENT_SIZE = 1024 * 1024 * 1024  # 1GB, 按大小分段
MAX_RECORD_FILES = 1000

# === 录制状态 ===
class RecordStatus(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"

# === 截图配置 (P3.3) ===
SCREENSHOT_RESPONSE_TIMEOUT = 2   # 秒
SCREENSHOT_FORMAT = "JPEG"
SCREENSHOT_QUALITY = 85

# === 日志级别 ===
ACCEPTED_LOG_LEVELS = {"info", "warning", "error", "done", "failed"}

# === 分页默认值 ===
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100



