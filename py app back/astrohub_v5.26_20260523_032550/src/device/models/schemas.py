"""
M2 Device Manager v1.0 - Pydantic 模型定义

定义设备、分组、状态、告警、日志等数据模型的输入验证与序列化。
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from device.constants import DeviceStatus, HeartbeatStatus
from device.core.mac_utils import normalize_mac, validate_mac


# === 设备模型 ===

class DeviceCreate(BaseModel):
    """创建设备的输入模型 (P0.1)。"""
    mac: str = Field(..., description="MAC地址 (12位十六进制，支持:-分隔)")
    ip: str = Field(..., description="设备IP地址")
    model: str = Field(..., description="设备型号")
    username: str = Field(..., description="登录用户名")
    password: str = Field(..., description="登录密码")
    port: int = Field(default=80, description="HTTP端口")
    notes: str = Field(default="", description="备注")

    @field_validator("mac")
    @classmethod
    def validate_mac_format(cls, v: str) -> str:
        is_valid, error = validate_mac(v)
        if not is_valid:
            raise ValueError(error)
        return normalize_mac(v)


class DeviceUpdate(BaseModel):
    """更新设备的输入模型 (P0.3)。"""
    ip: str | None = None
    username: str | None = None
    password: str | None = None
    port: int | None = None
    notes: str | None = None
    model: str | None = None


class DeviceResponse(BaseModel):
    """设备响应模型。"""
    mac: str
    ip: str
    model: str
    username: str
    port: int
    notes: str
    status: str  # new, active, inactive, deleted
    heartbeat_status: str  # online, offline
    created_at: str
    updated_at: str


# === 分组模型 ===

class GroupCreate(BaseModel):
    """创建分组的输入模型 (P3.1)。"""
    name: str = Field(..., min_length=1, max_length=100, description="分组名称")
    description: str = Field(default="", description="分组描述")


class GroupResponse(BaseModel):
    """分组响应模型。"""
    name: str
    description: str
    devices: list[str]  # MAC列表
    created_at: str
    updated_at: str


# === 状态监控模型 ===

class DeviceStatusResponse(BaseModel):
    """设备状态检测结果 (P1.1)。"""
    mac: str
    online: bool
    status_code: int
    response_time_ms: float
    details: str
    checked_at: str


class HeartbeatConfig(BaseModel):
    """心跳配置模型 (P1.3)。"""
    interval: int = Field(..., ge=5, le=300, description="心跳间隔(秒)，范围5-300")


class HeartbeatStatusResponse(BaseModel):
    """心跳状态模型 (P1.4)。"""
    mac: str
    status: str  # online/offline
    since: str  # 状态变更后时间
    last_check: str  # 上次心跳检查时间
    consecutive_checks: int  # 连续检测次数


# === 告警模型 ===

class AlertResponse(BaseModel):
    """告警信息模型 (P1.5)。"""
    mac: str
    level: str  # warning/error/critical
    anomaly_type: str  # auth_failed/connection_timeout/device_fault/network_unreachable
    timestamp: str
    description: str


# === 状态历史模型 ===

class StatusHistoryEntry(BaseModel):
    """状态历史记录条目 (P1.6)。"""
    mac: str
    old_status: str
    new_status: str
    reason: str
    timestamp: str


class StatusHistoryQuery(BaseModel):
    """状态历史查询参数。"""
    mac: str | None = None
    start_date: str | None = None
    end_date: str | None = None


# === 配置管理模型 ===

class ConfigBackupResponse(BaseModel):
    """配置备份响应模型 (P2.3)。"""
    mac: str
    backup_path: str
    timestamp: str
    version: str | None = None


class ConfigDiffItem(BaseModel):
    """配置差异项模型 (P2.5)。"""
    field: str
    old_value: Any
    new_value: Any


class ConfigDiffResponse(BaseModel):
    """配置差异对比响应 (P2.5)。"""
    mac: str
    has_diff: bool
    differences: list[ConfigDiffItem]


class ConfigVersionInfo(BaseModel):
    """配置版本信息 (P2.6)。"""
    version: str
    timestamp: str
    description: str


class ConfigRollbackRequest(BaseModel):
    """配置回滚请求 (P2.6)。"""
    version: str


# === 批量操作模型 ===

class BatchImportResult(BaseModel):
    """批量导入结果 (P0.5)。"""
    success_count: int
    failure_count: int
    failures: list[dict]  # [{mac, error}]


class BatchExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"


class BatchGroupOperation(BaseModel):
    """分组批量操作请求 (P3.5)。"""
    group_name: str
    operation: str  # status_check, config_read, config_write


# === 操作日志模型 ===

class OperationLogEntry(BaseModel):
    """操作日志条目 (P4.1)。"""
    level: str  # info/warning/error/done/failed
    timestamp: str
    operator: str
    device_mac: str | None = None
    operation: str
    details: str


class OperationLogQuery(BaseModel):
    """操作日志查询参数 (P4.2)。"""
    level: str | None = None
    device_mac: str | None = None
    operation: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=50, ge=1, le=500, description="每页条数")


class OperationLogPageResponse(BaseModel):
    """操作日志分页响应。"""
    total: int
    page: int
    page_size: int
    logs: list[OperationLogEntry]


# === 生命周期模型 ===

class DeviceLifecycleResponse(BaseModel):
    """设备生命周期状态响应。"""
    mac: str
    status: str  # new, active, inactive, deleted
    transition: str  # 如 new→active
    timestamp: str
    message: str
