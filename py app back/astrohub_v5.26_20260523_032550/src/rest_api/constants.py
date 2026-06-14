"""
M7 REST API v1.0 - 全局常量定义

API 网关限流、认证、错误码、路由前缀等配置。

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "REST_API"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "log"

# === API 配置 ===
API_PREFIX = "/api"
API_V1_PREFIX = f"{API_PREFIX}/v1"
DOCS_URL = "/docs"
REDOC_URL = "/redoc"
OPENAPI_URL = "/openapi.json"

# === 服务默认值 ===
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

# === CORS 配置 (P0.1) ===
CORS_ALLOW_ORIGINS = ["*"]  # 生产环境应配置具体域名
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["*"]
CORS_ALLOW_CREDENTIALS = True

# === JWT 认证 (P5.1) ===
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60
JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30
JWT_DEFAULT_SECRET = "changeme-in-production"  # 生产环境必须修改

# === API Key 认证 ===
API_KEY_HEADER = "X-API-Key"
API_KEY_LENGTH = 32

# === 角色权限 (P5.2) ===
class Role(Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

# 角色权限矩阵: {endpoint_pattern: {最小角色}}
ROLE_PERMISSIONS = {
    "admin": {Role.ADMIN, Role.OPERATOR, Role.VIEWER},  # admin全权限
    "operator": {Role.ADMIN, Role.OPERATOR},              # operator可读+操作
    "viewer": {Role.ADMIN},                                # viewer只读
}

# 路由到角色的映射
ROUTE_ROLE_MAP = {
    # 只读端点 (viewer可访问)
    "GET:/devices": Role.VIEWER,
    "GET:/devices/{mac}": Role.VIEWER,
    "GET:/devices/{mac}/status": Role.VIEWER,
    "GET:/devices/{mac}/config": Role.VIEWER,
    "GET:/devices/{mac}/history": Role.VIEWER,
    "GET:/streams/{device_mac}": Role.VIEWER,
    "GET:/calibration/{id}": Role.VIEWER,
    "GET:/calibration/{id}/result": Role.VIEWER,
    "GET:/observations": Role.VIEWER,
    "GET:/stats": Role.VIEWER,
    # 操作端点 (operator可访问)
    "POST:/devices": Role.ADMIN,
    "PUT:/devices/{mac}": Role.ADMIN,
    "DELETE:/devices/{mac}": Role.ADMIN,
    "POST:/streams/{device_mac}/start": Role.ADMIN,
    "POST:/streams/{device_mac}/stop": Role.ADMIN,
    "POST:/streams/{device_mac}/snapshot": Role.OPERATOR,
    "POST:/calibration/{device_mac}/{type}": Role.OPERATOR,
    "POST:/calibration/{id}/stop": Role.OPERATOR,
    "PUT:/devices/{mac}/config": Role.ADMIN,
}

# === 限流配置 (P5.3) ===
class RateLimitTier(Enum):
    FREE = "free"          # 100次/分钟
    STANDARD = "standard"  # 500次/分钟
    PREMIUM = "premium"    # 2000次/分钟

RATE_LIMIT_DEFAULT_REQUESTS = 100    # 默认每分钟请求数
RATE_LIMIT_DEFAULT_WINDOW = 60       # 默认窗口(秒)
RATE_LIMIT_MAX_REQUESTS = 2000       # 最大每分钟请求数
RATE_LIMIT_CLEANUP_INTERVAL = 300    # 清理过期记录的间隔(秒)

# === 错误码定义 (P6.1) ===
class ErrorCode(Enum):
    # 通用错误
    SUCCESS = "SUCCESS"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"

    # 设备相关
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"
    DEVICE_ALREADY_EXISTS = "DEVICE_ALREADY_EXISTS"
    DEVICE_ONLINE_CANNOT_DELETE = "DEVICE_ONLINE_CANNOT_DELETE"

    # 流相关
    STREAM_NOT_FOUND = "STREAM_NOT_FOUND"
    STREAM_ALREADY_ACTIVE = "STREAM_ALREADY_ACTIVE"
    STREAM_NOT_ACTIVE = "STREAM_NOT_ACTIVE"
    STREAM_ERROR = "STREAM_ERROR"

    # 校准相关
    CALIBRATION_NOT_FOUND = "CALIBRATION_NOT_FOUND"
    CALIBRATION_IN_PROGRESS = "CALIBRATION_IN_PROGRESS"
    CALIBRATION_ALREADY_COMPLETED = "CALIBRATION_ALREADY_COMPLETED"

    # 认证相关
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    INVALID_API_KEY = "INVALID_API_KEY"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"

# 错误码到HTTP状态码的映射
ERROR_CODE_TO_HTTP = {
    ErrorCode.SUCCESS: 200,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.DEVICE_NOT_FOUND: 404,
    ErrorCode.DEVICE_OFFLINE: 409,
    ErrorCode.DEVICE_ALREADY_EXISTS: 409,
    ErrorCode.DEVICE_ONLINE_CANNOT_DELETE: 409,
    ErrorCode.STREAM_NOT_FOUND: 404,
    ErrorCode.STREAM_ALREADY_ACTIVE: 409,
    ErrorCode.STREAM_NOT_ACTIVE: 404,
    ErrorCode.STREAM_ERROR: 500,
    ErrorCode.CALIBRATION_NOT_FOUND: 404,
    ErrorCode.CALIBRATION_IN_PROGRESS: 409,
    ErrorCode.CALIBRATION_ALREADY_COMPLETED: 404,
    ErrorCode.INVALID_TOKEN: 401,
    ErrorCode.TOKEN_EXPIRED: 401,
    ErrorCode.INVALID_API_KEY: 401,
    ErrorCode.INVALID_CREDENTIALS: 401,
}

# 错误码到中文描述的映射
ERROR_CODE_DESCRIPTION = {
    ErrorCode.SUCCESS: "操作成功",
    ErrorCode.INTERNAL_ERROR: "服务器内部错误",
    ErrorCode.VALIDATION_ERROR: "请求参数验证失败",
    ErrorCode.NOT_FOUND: "资源不存在",
    ErrorCode.UNAUTHORIZED: "未授权访问",
    ErrorCode.FORBIDDEN: "无权限访问",
    ErrorCode.RATE_LIMITED: "请求频率超限",
    ErrorCode.DEVICE_NOT_FOUND: "设备不存在",
    ErrorCode.DEVICE_OFFLINE: "设备离线",
    ErrorCode.DEVICE_ALREADY_EXISTS: "设备已存在(重复MAC)",
    ErrorCode.DEVICE_ONLINE_CANNOT_DELETE: "在线设备无法删除",
    ErrorCode.STREAM_NOT_FOUND: "流不存在",
    ErrorCode.STREAM_ALREADY_ACTIVE: "流已处于活跃状态",
    ErrorCode.STREAM_NOT_ACTIVE: "流未启动",
    ErrorCode.STREAM_ERROR: "流处理错误",
    ErrorCode.CALIBRATION_NOT_FOUND: "校准任务不存在",
    ErrorCode.CALIBRATION_IN_PROGRESS: "校准正在进行中",
    ErrorCode.CALIBRATION_ALREADY_COMPLETED: "校准已完成",
    ErrorCode.INVALID_TOKEN: "无效的认证Token",
    ErrorCode.TOKEN_EXPIRED: "Token已过期",
    ErrorCode.INVALID_API_KEY: "无效的API Key",
    ErrorCode.INVALID_CREDENTIALS: "账号或密码错误",
}

# === MAC地址格式 ===
MAC_PATTERN = r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$"
MAC_NORMALIZED_LENGTH = 17  # "XX:XX:XX:XX:XX:XX"

# === 分页默认值 ===
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# === 日志级别 ===
ACCEPTED_LOG_LEVELS = {"info", "warning", "error", "done", "failed"}
