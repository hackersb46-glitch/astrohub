"""
M8 WebSocket v1.0 - 全局常量定义

WebSocket 服务器配置: 连接管理、心跳、认证、广播、监控。

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "WEBSOCKET"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "log"

# === WS 服务器配置 ===
WS_HOST = "0.0.0.0"
WS_PORT = 8765
WS_PATH = "/ws"

# === P0.3 心跳机制 ===
HEARTBEAT_INTERVAL_SECONDS = 30      # 心跳发送间隔 (秒)
HEARTBEAT_TIMEOUT_COUNT = 3          # 超时容忍次数 (连续N次无pong则断开)
HEARTBEAT_PING_MSG = "ping"
HEARTBEAT_PONG_MSG = "pong"

# === P0.4 连接认证 ===
WS_AUTH_PARAM = "token"              # URL query参数名 (ws://host/ws?token=xxx)
WS_TOKEN_EXPIRE_MINUTES = 60

# === P4.1 连接管理 ===
MAX_CONNECTIONS_PER_TOKEN = 5        # 单token最大连接数 (P4.2)
MAX_CONNECTIONS_TOTAL = 1000         # 全局最大连接数
CONNECTION_TIMEOUT_SECONDS = 300     # 连接超时清理 (秒, 5分钟, P4.4)
MAX_RECONNECT_ATTEMPTS = 5           # 最大重连次数 (P4.1)

# === P0.2 消息格式 ===
MSG_TYPE_KEY = "type"
MSG_PAYLOAD_KEY = "payload"
MSG_ID_KEY = "id"                    # 消息唯一标识


# ================================================================== #
#  消息类型枚举 (P0.2)
# ================================================================== #

class MessageType(Enum):
    """WebSocket 消息类型。"""
    # 心跳
    PING = "ping"
    PONG = "pong"
    # 认证
    AUTH = "auth"
    AUTH_ACK = "auth_ack"
    # 设备状态
    DEVICE_STATUS = "device_status"
    DEVICE_ONLINE_BROADCAST = "device_online_broadcast"
    DEVICE_ALERT = "device_alert"
    # 流数据
    STREAM_FRAME = "stream_frame"
    STREAM_AUDIO = "stream_audio"
    STREAM_START = "stream_start"
    STREAM_STOP = "stream_stop"
    # 命令下发
    PTZ_COMMAND = "ptz_command"
    PARAM_SET = "param_set"
    BATCH_COMMAND = "batch_command"
    # 订阅
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    # 系统
    ERROR = "error"
    UNKNOWN = "unknown"


# ================================================================== #
#  错误码 (P0.2)
# ================================================================== #

class ErrorCode(Enum):
    """WebSocket 错误码。"""
    # 通用
    SUCCESS = "WS_SUCCESS"
    INTERNAL_ERROR = "WS_INTERNAL_ERROR"
    INVALID_MESSAGE = "WS_INVALID_MESSAGE"
    UNKNOWN_MESSAGE_TYPE = "WS_UNKNOWN_MESSAGE_TYPE"

    # 认证
    AUTH_FAILED = "WS_AUTH_FAILED"
    TOKEN_EXPIRED = "WS_TOKEN_EXPIRED"
    TOKEN_INVALID = "WS_TOKEN_INVALID"

    # 连接
    CONNECTION_LIMIT_REACHED = "WS_CONNECTION_LIMIT_REACHED"
    CONNECTION_TIMEOUT = "WS_CONNECTION_TIMEOUT"
    MAX_RECONNECT_EXCEEDED = "WS_MAX_RECONNECT_EXCEEDED"

    # 订阅
    SUBSCRIPTION_FAILED = "WS_SUBSCRIPTION_FAILED"
    SUBSCRIPTION_NOT_FOUND = "WS_SUBSCRIPTION_NOT_FOUND"

    # 流
    STREAM_NOT_FOUND = "WS_STREAM_NOT_FOUND"
    STREAM_ERROR = "WS_STREAM_ERROR"

    # 命令
    COMMAND_FAILED = "WS_COMMAND_FAILED"
    DEVICE_NOT_FOUND = "WS_DEVICE_NOT_FOUND"
    DEVICE_OFFLINE = "WS_DEVICE_OFFLINE"


# 错误码描述
ERROR_CODE_DESCRIPTION = {
    ErrorCode.SUCCESS: "操作成功",
    ErrorCode.INTERNAL_ERROR: "WebSocket 服务器内部错误",
    ErrorCode.INVALID_MESSAGE: "消息格式无效",
    ErrorCode.UNKNOWN_MESSAGE_TYPE: "未知消息类型",
    ErrorCode.AUTH_FAILED: "认证失败",
    ErrorCode.TOKEN_EXPIRED: "Token 已过期",
    ErrorCode.TOKEN_INVALID: "无效的 Token",
    ErrorCode.CONNECTION_LIMIT_REACHED: "连接数已达上限",
    ErrorCode.CONNECTION_TIMEOUT: "连接超时",
    ErrorCode.MAX_RECONNECT_EXCEEDED: "重连次数已达上限",
    ErrorCode.SUBSCRIPTION_FAILED: "订阅失败",
    ErrorCode.SUBSCRIPTION_NOT_FOUND: "订阅不存在",
    ErrorCode.STREAM_NOT_FOUND: "流不存在",
    ErrorCode.STREAM_ERROR: "流处理错误",
    ErrorCode.COMMAND_FAILED: "命令执行失败",
    ErrorCode.DEVICE_NOT_FOUND: "设备不存在",
    ErrorCode.DEVICE_OFFLINE: "设备离线",
}


# ================================================================== #
#  连接状态枚举
# ================================================================== #

class ConnectionStatus(Enum):
    """WebSocket 连接状态。"""
    CONNECTING = "connecting"
    AUTHENTICATED = "authenticated"
    ACTIVE = "active"
    CLOSING = "closing"
    CLOSED = "closed"
