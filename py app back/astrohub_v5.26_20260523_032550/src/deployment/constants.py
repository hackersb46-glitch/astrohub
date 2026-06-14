"""
M11 Deployment Service v1.0 - 全局常量定义

部署配置、Docker、健康检查、回滚、环境变量、日志轮转等配置。

Author: 雅痞张@南方天文
"""

from pathlib import Path
from enum import Enum

# === 版本与作者 ===
VERSION = "v1.0"
VERSION_NUM = "1.0"
AUTHOR = "雅痞张@南方天文"
PROJECT_NAME = "DEPLOYMENT"

# === 路径 ===
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "log"
CONFIG_DIR = BASE_DIR / "config"
BACKUP_DIR = BASE_DIR / "backup"

# === 服务配置 ===
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8011

# === Docker 配置 (P0.1) ===
DOCKER_DEFAULT_CONTEXT = "default"
DOCKER_BUILD_TIMEOUT = 600        # 秒, 镜像构建超时
DOCKER_MAX_IMAGE_SIZE_MB = 1024   # MB, 镜像最大体积
DOCKERFILE_NAME = "Dockerfile"
COMPOSE_FILE_NAME = "docker-compose.yml"

# === docker-compose (P0.2) ===
COMPOSE_UP_TIMEOUT = 120          # 秒, compose up 超时
COMPOSE_NETWORK_PREFIX = "astro"
COMPOSE_RESTART_POLICY = "unless-stopped"

# === 部署脚本 (P0.3) ===
DEPLOY_PULL_TIMEOUT = 300         # 秒, pull 超时
DEPLOY_BUILD_TIMEOUT = 600        # 秒, build 超时
DEPLOY_HEALTH_WAIT = 60           # 秒, 健康检查等待

# === 环境配置 (P1) ===
ENV_DEVELOPMENT = "development"
ENV_TEST = "test"
ENV_PRODUCTION = "production"

VALID_ENVIRONMENTS = {ENV_DEVELOPMENT, ENV_TEST, ENV_PRODUCTION}

# 环境变量文件
ENV_FILE_DEVELOPMENT = ".env.development"
ENV_FILE_TEST = ".env.test"
ENV_FILE_PRODUCTION = ".env.production"

# === 配置校验 (P1.3) ===
REQUIRED_CONFIG_KEYS = [
    "DEPLOY_ENV",
    "SERVICE_NAME",
    "DOCKER_REGISTRY",
    "LOG_LEVEL",
]

# === 服务状态 ===
class ServiceStatus(Enum):
    """服务运行状态。"""
    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# === 健康检查 (P2.2) ===
HEALTH_CHECK_INTERVAL = 30        # 秒, 健康检查间隔
HEALTH_CHECK_TIMEOUT = 10         # 秒, 单次检查超时
HEALTH_CHECK_RETRIES = 3          # 连续失败次数阈值
HEALTH_ENDPOINT = "/health"

# === 日志轮转 (P2.3) ===
LOG_ROTATE_MAX_SIZE_MB = 50       # MB, 单日志最大体积
LOG_ROTATE_BACKUP_COUNT = 7       # 保留天数
LOG_ROTATE_INTERVAL = "DAILY"     # 轮转频率

# === 备份恢复 (P3) ===
BACKUP_RETENTION_COUNT = 10       # 保留备份数量
BACKUP_COMPRESSION = True         # 默认压缩
DB_BACKUP_CRON = "0 2 * * *"      # 每天凌晨2点备份
DB_BACKUP_TIMEOUT = 300           # 秒

# === 监控告警 (P4) ===
MONITOR_INTERVAL = 60             # 秒, 监控采集间隔
METRICS_RETENTION_DAYS = 30       # 指标保留天数
ALERT_THRESHOLD_CPU = 80         # CPU 告警阈值 %
ALERT_THRESHOLD_MEMORY = 85       # 内存告警阈值 %
ALERT_THRESHOLD_DISK = 90         # 磁盘告警阈值 %

# === 回滚配置 ===
ROLLBACK_MAX_VERSIONS = 5         # 保留历史版本数
ROLLBACK_TIMEOUT = 120            # 秒, 回滚超时

# === 分页默认值 ===
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 100

# === 错误码 ===
class ErrorCode(Enum):
    """部署服务错误码。"""
    # 通用
    SUCCESS = "DEPLOY_SUCCESS"
    INTERNAL_ERROR = "DEPLOY_INTERNAL_ERROR"
    VALIDATION_ERROR = "DEPLOY_VALIDATION_ERROR"

    # Docker
    DOCKER_BUILD_FAILED = "DEPLOY_DOCKER_BUILD_FAILED"
    DOCKER_PULL_FAILED = "DEPLOY_DOCKER_PULL_FAILED"
    COMPOSE_UP_FAILED = "DEPLOY_COMPOSE_UP_FAILED"
    IMAGE_SIZE_EXCEEDED = "DEPLOY_IMAGE_SIZE_EXCEEDED"

    # 服务
    SERVICE_START_FAILED = "DEPLOY_SERVICE_START_FAILED"
    SERVICE_STOP_FAILED = "DEPLOY_SERVICE_STOP_FAILED"
    HEALTH_CHECK_FAILED = "DEPLOY_HEALTH_CHECK_FAILED"

    # 配置
    CONFIG_VALIDATION_FAILED = "DEPLOY_CONFIG_VALIDATION_FAILED"
    CONFIG_NOT_FOUND = "DEPLOY_CONFIG_NOT_FOUND"
    ENV_FILE_NOT_FOUND = "DEPLOY_ENV_FILE_NOT_FOUND"

    # 回滚
    ROLLBACK_FAILED = "DEPLOY_ROLLBACK_FAILED"
    NO_VERSION_TO_ROLLBACK = "DEPLOY_NO_VERSION_TO_ROLLBACK"

    # 备份
    BACKUP_FAILED = "DEPLOY_BACKUP_FAILED"
    RESTORE_FAILED = "DEPLOY_RESTORE_FAILED"

# 错误码描述
ERROR_CODE_DESCRIPTION = {
    ErrorCode.SUCCESS: "操作成功",
    ErrorCode.INTERNAL_ERROR: "部署服务内部错误",
    ErrorCode.DOCKER_BUILD_FAILED: "Docker 镜像构建失败",
    ErrorCode.DOCKER_PULL_FAILED: "Docker 镜像拉取失败",
    ErrorCode.COMPOSE_UP_FAILED: "docker-compose 启动失败",
    ErrorCode.IMAGE_SIZE_EXCEEDED: "镜像体积超出限制",
    ErrorCode.SERVICE_START_FAILED: "服务启动失败",
    ErrorCode.SERVICE_STOP_FAILED: "服务停止失败",
    ErrorCode.HEALTH_CHECK_FAILED: "健康检查失败",
    ErrorCode.CONFIG_VALIDATION_FAILED: "配置校验失败",
    ErrorCode.CONFIG_NOT_FOUND: "配置文件不存在",
    ErrorCode.ENV_FILE_NOT_FOUND: "环境变量文件不存在",
    ErrorCode.ROLLBACK_FAILED: "回滚失败",
    ErrorCode.NO_VERSION_TO_ROLLBACK: "无可回滚版本",
    ErrorCode.BACKUP_FAILED: "备份失败",
    ErrorCode.RESTORE_FAILED: "恢复失败",
}
