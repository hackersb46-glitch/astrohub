"""
AstroHub v2.0 - 视频流管理器（简化版）

每个设备只维持一个子码流（102），不泄漏ffmpeg进程。
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.config import DATA_DIR
from src.logger import get_logger

logger = get_logger("stream_manager")


@dataclass
class StreamConfig:
    """视频流配置。"""
    device_id: str
    stream_name: str
    rtsp_url: str
    status: str = "stopped"
    started_at: Optional[datetime] = None
    error_message: Optional[str] = None
    ffmpeg_pid: Optional[int] = None


class StreamManager:
    """视频流管理器。

    每个设备只维持一个流。重复start返回已有流。
    """

    def __init__(self) -> None:
        self._streams: dict[str, StreamConfig] = {}  # device_id -> StreamConfig
        self._lock = threading.Lock()
        logger.info("StreamManager 初始化完成")

    def start_stream(self, device_id: str, rtsp_url: str, stream_name: str) -> dict:
        """启动视频流。如果设备已有活跃流，直接返回。

        Args:
            device_id: 设备IP
            rtsp_url: RTSP地址
            stream_name: 流名称

        Returns:
            流信息字典
        """
        with self._lock:
            # 如果已有活跃流，直接返回
            existing = self._streams.get(device_id)
            if existing and existing.status == "active":
                logger.info("设备已有活跃流，复用 | device_id=%s", device_id)
                return {
                    "success": True,
                    "stream_id": device_id,
                    "device_id": device_id,
                    "stream_name": existing.stream_name,
                    "status": "active",
                    "rtsp_url": existing.rtsp_url,
                }

            # 停止旧流（如果有）
            if existing and existing.ffmpeg_pid:
                try:
                    os.kill(existing.ffmpeg_pid, signal.SIGTERM)
                    logger.info("已停止旧ffmpeg进程 PID=%d", existing.ffmpeg_pid)
                except Exception:
                    pass

            # 创建新流
            config = StreamConfig(
                device_id=device_id,
                stream_name=stream_name,
                rtsp_url=rtsp_url,
                status="active",
                started_at=datetime.now(),
            )
            self._streams[device_id] = config
            logger.info("视频流已启动 | device_id=%s", device_id)

            return {
                "success": True,
                "stream_id": device_id,
                "device_id": device_id,
                "stream_name": stream_name,
                "status": "active",
                "rtsp_url": rtsp_url,
            }

    def stop_stream(self, device_id: str) -> dict:
        """停止设备的视频流。"""
        with self._lock:
            config = self._streams.get(device_id)
            if not config:
                return {"success": False, "message": "设备无活跃流"}

            if config.ffmpeg_pid:
                try:
                    os.kill(config.ffmpeg_pid, signal.SIGTERM)
                    logger.info("已停止ffmpeg进程 PID=%d", config.ffmpeg_pid)
                except Exception:
                    pass

            config.status = "stopped"
            config.ffmpeg_pid = None
            return {"success": True, "message": "流已停止"}

    def get_stream(self, device_id: str) -> Optional[dict]:
        """获取设备流信息。"""
        config = self._streams.get(device_id)
        if not config:
            return None
        return {
            "stream_id": device_id,
            "device_id": device_id,
            "stream_name": config.stream_name,
            "status": config.status,
            "rtsp_url": config.rtsp_url,
        }

    def list_streams(self) -> list[dict]:
        """列出所有流。"""
        result = []
        for config in self._streams.values():
            result.append({
                "stream_id": config.device_id,
                "device_id": config.device_id,
                "stream_name": config.stream_name,
                "status": config.status,
                "rtsp_url": config.rtsp_url,
                "started_at": config.started_at.isoformat() if config.started_at else None,
            })
        return result
