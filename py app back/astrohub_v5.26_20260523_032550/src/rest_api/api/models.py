"""
M7 REST API v1.0 - Pydantic 请求/响应模型 (Wave 4)

实现:
- 所有请求有严格的类型校验
- 返回响应有标准格式
- 422错误返回详细字段信息

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Any, Generic, TypeVar
from enum import Enum


# ================================================================== #
#  通用分页模型
# ================================================================== #

class PaginationRequest(BaseModel):
    """分页请求通用参数。"""
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class PaginationResponse(BaseModel):
    """分页响应。"""
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    page_size: int = Field(..., ge=1, description="每页数量")
    has_next: bool = False
    has_prev: bool = False


class PaginatedResponse(BaseModel):
    """通用分页响应。"""
    success: bool = True
    data: list[Any] = []
    pagination: PaginationResponse


# ================================================================== #
#  统一响应格式
# ================================================================== #

class SuccessResponse(BaseModel):
    """标准成功响应。"""
    success: bool = True
    message: str = ""
    data: Any = None


class ErrorResponse(BaseModel):
    """标准错误响应。"""
    success: bool = False
    error: str = ""
    code: str = ""
    details: dict[str, Any] | None = None


class ValidationError(BaseModel):
    """字段验证错误。"""
    field: str
    message: str
    code: str = "validation_error"


class ValidationErrorResponse(BaseModel):
    """422 验证错误响应。"""
    success: bool = False
    error: str = "请求参数验证失败"
    code: str = "VALIDATION_ERROR"
    details: list[ValidationError] = []


# ================================================================== #
#  设备管理模型 (P1)
# ================================================================== #

class DeviceCreateRequest(BaseModel):
    """创建设备请求。"""
    mac: str = Field(..., min_length=11, max_length=17, description="MAC地址")
    model: str = Field(..., min_length=1, max_length=255, description="设备型号")
    ip: str = Field(..., min_length=7, description="IP地址")
    port: int = Field(default=80, ge=1, le=65535)
    username: str = Field(default="admin")
    password: str = Field(..., min_length=1)
    name: str = Field(default="", max_length=255)

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        v_normalized = v.replace("-", ":").upper()
        import re
        if not re.match(r"^([0-9A-F]{2}[:-]){5}([0-9A-F]{2})$", v_normalized):
            raise ValueError(f"MAC地址格式无效: {v}")
        return v_normalized

    @field_validator("ip")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        import re
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", v):
            raise ValueError(f"IP地址格式无效: {v}")
        parts = v.split(".")
        for p in parts:
            if not 0 <= int(p) <= 255:
                raise ValueError(f"IP地址段无效: {p}")
        return v


class DeviceUpdateRequest(BaseModel):
    """更新设备请求。"""
    name: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    ip: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)


class DeviceStatusResponse(BaseModel):
    """设备状态响应。"""
    mac: str
    status: str
    last_heartbeat: str | None = None
    ip: str | None = None
    model: str | None = None


# ================================================================== #
#  流控制模型 (P2)
# ================================================================== #

class StreamStartRequest(BaseModel):
    """启动视频流请求。"""
    device_mac: str = Field(..., min_length=11)
    channel: int = Field(default=101, description="通道号")

    @field_validator("device_mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        return v.replace("-", ":").upper()


class SnapshotResponse(BaseModel):
    """截图响应。"""
    success: bool = True
    filepath: str
    file_size: int
    elapsed_ms: int
    format: str = "JPEG"
    verified: bool = True


# ================================================================== #
#  校准模型 (P3)
# ================================================================== #

class CalibrationStartRequest(BaseModel):
    """启动校准请求。"""
    device_mac: str = Field(..., min_length=11)
    calibration_type: str = Field(..., min_length=1, max_length=100)

    @field_validator("device_mac")
    @classmethod
    def validate_mac(cls, v: str) -> str:
        return v.replace("-", ":").upper()


# ================================================================== #
#  认证模型 (P5)
# ================================================================== #

class LoginRequest(BaseModel):
    """登录请求。"""
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """登录响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


class RefreshTokenRequest(BaseModel):
    """刷新Token请求。"""
    refresh_token: str = Field(..., min_length=1)


# ================================================================== #
#  SADP 模型
# ================================================================== #

class SadpScanRequest(BaseModel):
    """SADP扫描请求。"""
    bind_ip: str = Field(default="0.0.0.0")


class SadpModifyIpRequest(BaseModel):
    """SADP修改IP请求。"""
    mac: str = Field(..., min_length=11)
    password: str = Field(..., min_length=1)
    new_ip: str = Field(..., min_length=7)
    original_ip: str = Field(default="")
    subnet_mask: str = Field(default="255.255.255.0")
    gateway: str = Field(default="")


# ================================================================== #
#  PTZ 控制模型
# ================================================================== #

class PTZMoveRequest(BaseModel):
    """PTZ移动请求。"""
    direction: str = Field(..., min_length=1, max_length=20)
    speed: int = Field(default=50, ge=1, le=100)

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        allowed = {"left", "right", "up", "down", "left-up", "left-down", "right-up", "right-down", "stop"}
        v_lower = v.lower()
        if v_lower not in allowed:
            raise ValueError(f"无效的方向: {v}。允许的值为: {sorted(allowed)}")
        return v_lower


class PTZAbsoluteRequest(BaseModel):
    """PTZ绝对位置请求。"""
    pan: float = Field(..., ge=-180, le=360)
    tilt: float = Field(..., ge=-90, le=90)
    zoom: float | None = Field(default=None, ge=0, le=1)
    speed: int = Field(default=50, ge=1, le=100)


class PTZPresetRequest(BaseModel):
    """PTZ预置位请求。"""
    preset_id: int = Field(..., ge=0, le=255)


# ================================================================== #
#  望远镜控制模型 (ASCOM)
# ================================================================== #

class TelescopeSlewRequest(BaseModel):
    """望远镜Slew请求。"""
    ra: float = Field(..., ge=0, le=24, description="赤经 (小时)")
    dec: float = Field(..., ge=-90, le=90, description="赤纬 (度)")


class TelescopeTrackingRequest(BaseModel):
    """望远镜跟踪模式请求。"""
    mode: str = Field(..., description="跟踪模式")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        allowed = {"trackSidereal", "trackLunar", "trackSolar", "trackOff"}
        if v not in allowed:
            raise ValueError(f"无效的模式: {v}。允许的值为: {sorted(allowed)}")
        return v


# ================================================================== #
#  高级功能模型
# ================================================================== #

class AdvancedFunctionRunRequest(BaseModel):
    """功能探测运行请求。"""
    device_ip: str = Field(..., min_length=7)
    username: str = Field(default="admin")
    password: str = Field(default="")
    port: int = Field(default=80, ge=1, le=65535)
    item: str = Field(default="", description="留空=全部探测")


class AdvancedLimitRunRequest(BaseModel):
    """限位测试运行请求。"""
    device_ip: str = Field(..., min_length=7)
    username: str = Field(default="admin")
    password: str = Field(default="")
    port: int = Field(default=80, ge=1, le=65535)


class AdvancedSpeedRunRequest(BaseModel):
    """速度测试运行请求。"""
    device_ip: str = Field(..., min_length=7)
    username: str = Field(default="admin")
    password: str = Field(default="")
    port: int = Field(default=80, ge=1, le=65535)


class AdvancedConfigWriteRequest(BaseModel):
    """配置写入请求。"""
    mac: str = Field(..., min_length=11)
    ip: str = Field(default="")
    model: str = Field(default="")
    capabilities: dict | None = None
    limits: dict | None = None
    speed: dict | None = None


class AdvancedOnboardingStartRequest(BaseModel):
    """引导开始请求。"""
    mac: str = Field(..., min_length=11)
