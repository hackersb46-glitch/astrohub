"""
M10 Integration v1.0 - 全局常量定义

系统集成: 全模块集成测试、端到端流程验证、性能优化、异常恢复。

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum


# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "INTEGRATION"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "log"

# === 服务配置 ===
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8010

# === 集成超时 (P0) ===
INTEGRATION_STARTUP_TIMEOUT = 60     # 秒, 全模块启动超时
MODULE_HEALTH_CHECK_TIMEOUT = 10     # 秒, 单模块健康检查超时
E2E_FLOW_TIMEOUT = 120               # 秒, 端到端流程超时

# === 性能测试阈值 (P2) ===
MAX_MANAGED_DEVICES = 10             # 最大可管理设备数
STREAM_LATENCY_LAN_TARGET = 1.0      # 秒, 局域网延迟目标
STREAM_LATENCY_WAN_TARGET = 3.0      # 秒, 广域网延迟目标
API_P95_RESPONSE_MS = 500            # ms, P95 响应时间目标
API_P99_RESPONSE_MS = 2000           # ms, P99 并发响应目标
API_CONCURRENT_REQUESTS = 100        # 并发请求数

# === 异常恢复 (P3) ===
STREAM_RECONNECT_TIMEOUT = 30        # 秒, 断流恢复超时
DEVICE_OFFLINE_DETECTION = 15        # 秒, 设备离线检测间隔
SERVICE_RECOVERY_TIMEOUT = 30        # 秒, 服务重启恢复超时

# === 重试配置 ===
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 2               # 指数退避基数 (秒)

# === 任务优先级 ===
TASK_PRIORITY_CRITICAL = 0
TASK_PRIORITY_HIGH = 1
TASK_PRIORITY_NORMAL = 2
TASK_PRIORITY_LOW = 3


# ================================================================== #
#  集成状态枚举
# ================================================================== #

class IntegrationStatus(Enum):
    """集成系统全局状态。"""
    INITIALIZING = "initializing"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ================================================================== #
#  模块状态
# ================================================================== #

class ModuleStatus(Enum):
    """子模块健康状态。"""
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


# ================================================================== #
#  端到端流程阶段
# ================================================================== #

class E2EStage(Enum):
    """端到端流程阶段。"""
    DEVICE_DISCOVERY = "device_discovery"
    AUTHENTICATION = "authentication"
    STREAM_PREVIEW = "stream_preview"
    CALIBRATION = "calibration"


# ================================================================== #
#  错误码
# ================================================================== #

class ErrorCode(Enum):
    """集成服务错误码。"""
    # 通用
    SUCCESS = "INTEGRATION_SUCCESS"
    INTERNAL_ERROR = "INTEGRATION_INTERNAL_ERROR"

    # 集成
    MODULE_NOT_AVAILABLE = "INTEGRATION_MODULE_NOT_AVAILABLE"
    MODULE_COMMUNICATION_FAILED = "INTEGRATION_MODULE_COMMUNICATION_FAILED"
    INTEGRATION_TIMEOUT = "INTEGRATION_TIMEOUT"

    # E2E 流程
    E2E_FLOW_FAILED = "INTEGRATION_E2E_FLOW_FAILED"
    E2E_STAGE_FAILED = "INTEGRATION_E2E_STAGE_FAILED"

    # 性能
    PERFORMANCE_THRESHOLD_EXCEEDED = "INTEGRATION_PERFORMANCE_THRESHOLD_EXCEEDED"
    DEVICE_LIMIT_REACHED = "INTEGRATION_DEVICE_LIMIT_REACHED"

    # 恢复
    RECOVERY_FAILED = "INTEGRATION_RECOVERY_FAILED"
    RECONNECT_TIMEOUT = "INTEGRATION_RECONNECT_TIMEOUT"


# 错误码描述
ERROR_CODE_DESCRIPTION = {
    ErrorCode.SUCCESS: "操作成功",
    ErrorCode.INTERNAL_ERROR: "集成服务内部错误",
    ErrorCode.MODULE_NOT_AVAILABLE: "子模块不可用",
    ErrorCode.MODULE_COMMUNICATION_FAILED: "模块间通信失败",
    ErrorCode.INTEGRATION_TIMEOUT: "集成操作超时",
    ErrorCode.E2E_FLOW_FAILED: "端到端流程失败",
    ErrorCode.E2E_STAGE_FAILED: "端到端流程阶段失败",
    ErrorCode.PERFORMANCE_THRESHOLD_EXCEEDED: "性能阈值超出",
    ErrorCode.DEVICE_LIMIT_REACHED: "达到设备管理上限",
    ErrorCode.RECOVERY_FAILED: "异常恢复失败",
    ErrorCode.RECONNECT_TIMEOUT: "重连超时",
}


# ================================================================== #
#  事件类型
# ================================================================== #

class EventType(Enum):
    """集成事件类型。"""
    MODULE_STATUS_CHANGED = "module_status_changed"
    E2E_FLOW_STARTED = "e2e_flow_started"
    E2E_FLOW_COMPLETED = "e2e_flow_completed"
    E2E_FLOW_FAILED = "e2e_flow_failed"
    DEVICE_ONLINE = "device_online"
    DEVICE_OFFLINE = "device_offline"
    STREAM_DISCONNECTED = "stream_disconnected"
    STREAM_RECONNECTED = "stream_reconnected"
    HEALTH_DEGRADED = "health_degraded"
    HEALTH_RECOVERED = "health_recovered"
