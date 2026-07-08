"""
M3 Stream Service v1.0 - Pydantic 请求/响应模型

Wave 4 新增: 所有端点的严格类型校验和标准响应格式。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field, field_validator


# ================================================================== #
#  RTSP 流相关模型
# ================================================================== #

class RtspUrlParseRequest(BaseModel):
    """RTSP URL 解析请求。"""
    url: str = Field(..., min_length=1, description="RTSP URL")

    @field_validator("url")
    @classmethod
    def validate_rtsp_url(cls, v: str) -> str:
        if not v.lower().startswith(("rtsp://", "rtsps://")):
            raise ValueError("必须是 rtsp:// 或 rtsps:// 开头的 URL")
        return v


class RtspUrlParseResponse(BaseModel):
    """RTSP URL 解析响应。"""
    success: bool
    protocol: str = ""
    username: str = ""
    password: str = ""
    host: str = ""
    port: int = 554
    path: str = "/"
    error: str | None = None


class StreamConnectRequest(BaseModel):
    """流连接请求。"""
    stream_url: str = Field(..., min_length=1)
    protocol: str = Field(default="rtsp", pattern=r"^(rtsp|onvif|http-flv)$")
    username: str = Field(default="")
    password: str = Field(default="")


class StreamConnectResponse(BaseModel):
    """流连接响应。"""
    success: bool
    stream_id: str | None = None
    status_code: int = 200
    error: str | None = None
    parsed_url: dict[str, Any] | None = None


# ================================================================== #
#  截图相关模型
# ================================================================== #

class ScreenshotRequest(BaseModel):
    """截图请求。"""
    stream_url: str = Field(..., min_length=1)
    stream_id: str = Field(default="", description="流标识")


class ScreenshotResponse(BaseModel):
    """截图响应。"""
    success: bool
    filepath: str = ""
    file_size: int = 0
    elapsed_ms: int = 0
    format: str = "JPEG"
    error: str | None = None
    verified: bool = False  # 文件是否验证过


class MultiScreenshotRequest(BaseModel):
    """多张截图请求。"""
    stream_url: str = Field(..., min_length=1)
    stream_id: str = Field(default="")
    count: int = Field(default=3, ge=1, le=10)
    interval_seconds: float = Field(default=2.0, ge=0.5, le=300.0)


# ================================================================== #
#  录制相关模型
# ================================================================== #

class RecordingStartRequest(BaseModel):
    """录制启动请求。"""
    stream_url: str = Field(..., min_length=1)
    stream_id: str = Field(..., min_length=1)
    format: str = Field(default="mp4", pattern=r"^(mp4|flv)$")
    duration_seconds: int = Field(default=60, ge=1, le=7200)


class RecordingStartResponse(BaseModel):
    """录制启动响应。"""
    success: bool
    record_id: str | None = None
    filepath: str = ""
    duration_seconds: int = 0
    status: str = ""
    error: str | None = None


class RecordingStopRequest(BaseModel):
    """录制停止请求。"""
    stream_id: str = Field(..., min_length=1)


class RecordingStopResponse(BaseModel):
    """录制停止响应。"""
    success: bool
    stream_id: str = ""
    filepath: str = ""
    size_bytes: int = 0
    duration_seconds: float = 0.0
    error: str | None = None
    verified: bool = False  # 文件是否验证过


# ================================================================== #
#  ONVIF 发现模型
# ================================================================== #

class OnvifDiscoverRequest(BaseModel):
    """ONVIF 发现请求。"""
    timeout: int = Field(default=10, ge=1, le=60)


# ================================================================== #
#  通用响应包装
# ================================================================== #

class ApiResponse(BaseModel):
    """统一 API 响应。"""
    success: bool
    message: str = ""
    data: Any = None
    error: str | None = None
