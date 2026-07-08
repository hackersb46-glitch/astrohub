"""
M3 Stream Service - 视频流管理 (Wave 4)

实现:
1. RTSP流地址解析 - ISAPI获取RTSP URL, 支持H264/H265编码
2. 视频流连接和播放 - 连接验证, 状态跟踪, 多路流并发
3. 截图功能 - 从RTSP流截取当前帧, 保存JPEG到download/image/
4. 60秒视频录制 - 录制到download/
5. 3张图像间隔采集

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import os
import re
import socket
import subprocess
import time
import uuid
from datetime import datetime
from typing import Any

from src.stream.constants import (
    DOWNLOAD_DIR,
    DOWNLOAD_IMAGE_DIR,
    RTSP_DEFAULT_PORT,
    RTSP_HIKVISION_CHANNELS,
    RTSP_HIKVISION_TEMPLATE,
    RTSP_URL_PATTERN,
    SCREENSHOT_FORMAT,
    SCREENSHOT_QUALITY,
    SCREENSHOT_RESPONSE_TIMEOUT,
)

from src.stream.core.logger import LOG


# ================================================================== #
#  1. RTSP流地址解析
# ================================================================== #

class RtspUrlParser:
    """RTSP URL解析器。

    解析标准RTSP URL格式:
    - rtsp://ip:port/Streaming/Channels/{channel}
    - rtsp://user:pass@ip:port/path

    支持Hikvision格式URL模板生成。
    """

    def __init__(self) -> None:
        self._pattern = re.compile(RTSP_URL_PATTERN, re.IGNORECASE)

    def parse(self, url: str) -> dict[str, Any]:
        """解析RTSP URL，返回结构化字段。

        Args:
            url: 完整RTSP URL字符串

        Returns:
            结构化字典: protocol/username/password/host/port/path
            非法格式返回 {"error": "解析错误"}
        """
        match = self._pattern.match(url.strip())
        if not match:
            return {"error": "非法RTSP URL格式", "url": url}

        groups = match.groupdict()

        protocol = url.split("://")[0].lower() if "://" in url else "rtsp"
        host = groups.get("host", "")
        port = int(groups["port"]) if groups.get("port") else RTSP_DEFAULT_PORT
        path = groups.get("path", "/")
        username = groups.get("username", "")
        password = groups.get("password", "")

        if not host:
            return {"error": "缺少host字段", "url": url}

        # 检测编码类型
        codec = self._detect_codec_from_path(path)

        return {
            "protocol": protocol,
            "username": username,
            "password": password,
            "host": host,
            "port": port,
            "path": path,
            "codec": codec,
        }

    @staticmethod
    def _detect_codec_from_path(path: str) -> str:
        """从URL路径检测编码类型 (H264 vs H265)。"""
        # Hikvision: 101/102 = H264, 201/202 = H265
        channel_match = re.search(r"/Channels/(\d)", path)
        if channel_match:
            series = channel_match.group(1)
            return "h264" if series == "1" else "h265" if series == "2" else "unknown"
        return "unknown"

    def build_hikvision_url(
        self,
        ip: str,
        port: int = RTSP_DEFAULT_PORT,
        channel: int = 101,
    ) -> str:
        """构建Hikvision RTSP URL。

        Args:
            ip: 设备IP地址
            port: RTSP端口 (默认554)
            channel: 通道号 (101=H264主码流, 102=H264子码流, 201=H265主码流, 202=H265子码流)

        Returns:
            完整RTSP URL
        """
        return RTSP_HIKVISION_TEMPLATE.format(
            ip=ip,
            port=port,
            channel=channel,
        )

    def get_available_streams(self, ip: str, port: int = RTSP_DEFAULT_PORT) -> list[dict]:
        """获取可用的流URL列表。

        Args:
            ip: 设备IP地址
            port: RTSP端口

        Returns:
            可用的流URL列表
        """
        streams = []
        for channel_num, channel_path in RTSP_HIKVISION_CHANNELS.items():
            url = f"rtsp://{ip}:{port}/{channel_path}"
            codec = self._detect_codec_from_path(f"/{channel_path}")
            stream_type = "main" if str(channel_num).endswith("1") else "sub"
            streams.append({
                "url": url,
                "channel": channel_num,
                "codec": codec,
                "stream_type": stream_type,
                "path": f"/{channel_path}",
            })
        return streams


# ================================================================== #
#  2. 视频流连接和播放
# ================================================================== #

class StreamConnectionState:
    """流连接状态枚举。"""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class StreamSession:
    """单个RTSP流会话。"""

    def __init__(self, stream_url: str, stream_id: str = "") -> None:
        self.stream_id = stream_id or str(uuid.uuid4())[:8]
        self.stream_url = stream_url
        self.state = StreamConnectionState.DISCONNECTED
        self.connected_at: float = 0
        self.error: str = ""
        self.metadata: dict[str, Any] = {}

    def mark_connected(self) -> None:
        self.state = StreamConnectionState.CONNECTED
        self.connected_at = time.time()
        self.error = ""

    def mark_disconnected(self) -> None:
        self.state = StreamConnectionState.DISCONNECTED
        self.connected_at = 0

    def mark_error(self, error: str) -> None:
        self.state = StreamConnectionState.ERROR
        self.error = error

    def to_dict(self) -> dict:
        return {
            "stream_id": self.stream_id,
            "stream_url": self.stream_url,
            "state": self.state,
            "connected_at": datetime.fromtimestamp(self.connected_at).isoformat() if self.connected_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }


class StreamPool:
    """RTSP流连接池 - 支持多路流并发。"""

    def __init__(self, max_streams: int = 16) -> None:
        self._streams: dict[str, StreamSession] = {}
        self._max_streams = max_streams

    @property
    def active_count(self) -> int:
        return sum(
            1 for s in self._streams.values()
            if s.state == StreamConnectionState.CONNECTED
        )

    def add(self, stream_url: str, stream_id: str = "") -> StreamSession:
        """添加新流会话。"""
        if len(self._streams) >= self._max_streams:
            raise RuntimeError(f"流连接数已达上限: {self._max_streams}")

        session = StreamSession(stream_url, stream_id)
        self._streams[session.stream_id] = session
        return session

    def get(self, stream_id: str) -> StreamSession | None:
        return self._streams.get(stream_id)

    def remove(self, stream_id: str) -> bool:
        session = self._streams.pop(stream_id, None)
        if session:
            session.mark_disconnected()
            return True
        return False

    def list_all(self) -> list[dict]:
        return [s.to_dict() for s in self._streams.values()]


class RtspConnector:
    """RTSP流连接器。

    连接RTSP流并验证可达性。
    获取流状态（连接/断开/错误）。
    支持多路流并发。
    """

    def __init__(self, timeout: int = 10) -> None:
        self._pool = StreamPool()
        self._timeout = timeout

    @property
    def pool(self) -> StreamPool:
        return self._pool

    async def connect(self, stream_url: str, stream_id: str = "") -> dict:
        """连接RTSP流并验证可达。

        Args:
            stream_url: RTSP流地址
            stream_id: 流标识 (可选，自动生成)

        Returns:
            {"success": True, "stream_id": "...", "state": "connected"}
            {"success": False, "error": "..."}
        """
        session = self._pool.add(stream_url, stream_id)
        session.state = StreamConnectionState.CONNECTING

        try:
            # 使用ffmpeg探测流是否可达
            loop = asyncio.get_event_loop()
            reachable = await loop.run_in_executor(
                None,
                self._probe_stream,
                stream_url,
                self._timeout,
            )

            if reachable:
                session.mark_connected()
                session.metadata = self._get_stream_info(stream_url)
                LOG.done(f"RTSP流已连接: {session.stream_id} | {stream_url}")
                return {
                    "success": True,
                    "stream_id": session.stream_id,
                    "state": StreamConnectionState.CONNECTED,
                    "metadata": session.metadata,
                }
            else:
                session.mark_error("流不可达")
                self._pool.remove(session.stream_id)
                return {
                    "success": False,
                    "error": f"RTSP流不可达: {stream_url}",
                }

        except Exception as e:
            session.mark_error(str(e))
            self._pool.remove(session.stream_id)
            return {"success": False, "error": f"连接异常: {e}"}

    def disconnect(self, stream_id: str) -> dict:
        """断开流连接。"""
        if self._pool.remove(stream_id):
            LOG.info(f"流已断开: {stream_id}")
            return {"success": True, "stream_id": stream_id}
        return {"success": False, "error": f"流不存在: {stream_id}"}

    def get_status(self, stream_id: str) -> dict:
        """获取流状态。"""
        session = self._pool.get(stream_id)
        if session is None:
            return {"success": False, "error": f"流不存在: {stream_id}"}
        return {"success": True, **session.to_dict()}

    def list_streams(self) -> list[dict]:
        """获取所有流状态。"""
        return self._pool.list_all()

    @staticmethod
    def _probe_stream(url: str, timeout: int) -> bool:
        """探测RTSP流是否可达。

        使用ffmpeg快速探测流是否存在且可播放。
        不实际解码，仅探测流信息。
        """
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-timeout", str(timeout * 1000000),  # microseconds
            "-probesize", "32768",
            "-analyzeduration", "0",
            "-i", url,
            "-t", "0",  # 0秒: 只探测不解码
            "-f", "null",
            "-",
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            _stdout, stderr = proc.communicate(timeout=timeout + 5)
            # ffmpeg返回码0或1都有可能(取决于- t 0), 关键看stderr中是否有流信息
            stderr_text = stderr.decode("utf-8", errors="ignore").lower()
            # 如果有"could not"或"error"且没有"stream #"，通常不可达
            if "could not" in stderr_text and "stream" not in stderr_text:
                return False
            if "invalid data" in stderr_text:
                return False
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    @staticmethod
    def _get_stream_info(url: str) -> dict:
        """获取流元数据（编码、分辨率等）。"""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            url,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            stdout, _ = proc.communicate(timeout=10)
            import json
            info = json.loads(stdout.decode("utf-8"))

            streams = info.get("streams", [])
            result: dict[str, Any] = {"streams_count": len(streams)}

            for s in streams:
                if s.get("codec_type") == "video":
                    result["video_codec"] = s.get("codec_name", "unknown")
                    result["resolution"] = f"{s.get('width', 0)}x{s.get('height', 0)}"
                    result["fps"] = s.get("r_frame_rate", "unknown")
                elif s.get("codec_type") == "audio":
                    result["audio_codec"] = s.get("codec_name", "none")

            return result

        except Exception:
            return {"error": "无法获取流信息"}


# ================================================================== #
#  3. 截图功能
# ================================================================== #

class ScreenshotCapture:
    """从RTSP流截取当前帧。

    保存为JPEG到download/image/。
    验证文件大小>0且可打开。
    """

    def __init__(self, output_dir: str | None = None) -> None:
        self._output_dir = output_dir or str(DOWNLOAD_IMAGE_DIR)
        os.makedirs(self._output_dir, exist_ok=True)

    def capture(self, stream_url: str, stream_id: str = "") -> dict:
        """截图并验证文件。

        Args:
            stream_url: RTSP流地址
            stream_id: 流标识

        Returns:
            {"success": True, "filepath": "...", "file_size": 12345, "verified": True}
            {"success": False, "error": "..."}
        """
        if not stream_id:
            stream_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"{stream_id}_{int(time.time())}.jpg"
        output_path = os.path.join(self._output_dir, filename)

        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-timeout", "10000000",  # 10秒
            "-i", stream_url,
            "-frames:v", "1",
            "-q:v", str(SCREENSHOT_QUALITY),
            "-f", "image2",
            "-y",
            output_path,
        ]

        start_time = time.time()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            _stdout, stderr = proc.communicate(timeout=SCREENSHOT_RESPONSE_TIMEOUT + 5)

            if proc.returncode != 0:
                return {"success": False, "error": f"截图失败: {stderr.decode('utf-8', errors='ignore')[:200]}"}

            # === 验证: 文件存在且大小>0 ===
            if not os.path.exists(output_path):
                return {"success": False, "error": "截图文件未生成到磁盘"}

            file_size = os.path.getsize(output_path)
            if file_size <= 0:
                os.remove(output_path)  # 清理无效文件
                return {"success": False, "error": "截图文件为空 (0 bytes)"}

            # === 验证: JPEG文件可打开 ===
            verified = self._verify_jpeg(output_path)
            if not verified:
                os.remove(output_path)
                return {"success": False, "error": "截图文件不是有效的JPEG"}

            elapsed_ms = int((time.time() - start_time) * 1000)

            LOG.done(f"截图已保存并验证: {output_path} | {file_size}B | {elapsed_ms}ms")

            return {
                "success": True,
                "filepath": output_path,
                "filename": filename,
                "file_size": file_size,
                "elapsed_ms": elapsed_ms,
                "format": SCREENSHOT_FORMAT,
                "verified": True,
            }

        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "error": f"截图超时 (> {SCREENSHOT_RESPONSE_TIMEOUT}秒)"}
        except Exception as e:
            return {"success": False, "error": f"截图异常: {e}"}

    @staticmethod
    def _verify_jpeg(filepath: str) -> bool:
        """验证JPEG文件是否可正常打开。

        检查文件头是否为JPEG魔数 (FFD8FF)。
        """
        try:
            with open(filepath, "rb") as f:
                header = f.read(3)
            return header[:3] == b"\xff\xd8\xff"
        except Exception:
            return False


# ================================================================== #
#  4. 60秒视频录制
# ================================================================== #

class VideoRecorder:
    """录制RTSP流到磁盘文件。

    录制60秒为H264/H265文件。
    保存到download/目录。
    验证文件大小>0且可播放。
    """

    def __init__(self, output_dir: str | None = None) -> None:
        self._output_dir = output_dir or str(DOWNLOAD_DIR)
        os.makedirs(self._output_dir, exist_ok=True)
        self._active: dict[str, dict] = {}  # stream_id -> {"process": ..., "filepath": ..., ...}

    def start_recording(self, stream_url: str, duration: int = 60,
                        stream_id: str = "", codec: str = "copy") -> dict:
        """开始录制，指定时长。

        Args:
            stream_url: RTSP流地址
            duration: 录制时长(秒), 默认60秒
            stream_id: 流标识
            codec: 编码模式 (copy/h264/h265), 默认copy直接复制不转码

        Returns:
            {"success": True, "filepath": "...", "duration": 60}
            {"success": False, "error": "..."}
        """
        if not stream_id:
            stream_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stream_id}_{timestamp}.mp4"
        output_path = os.path.join(self._output_dir, filename)

        if codec == "copy":
            # 直接复制流, 不转码
            video_codec = "copy"
        else:
            video_codec = codec

        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-timeout", "10000000",
            "-i", stream_url,
            "-t", str(duration),
            "-c:v", video_codec,
            "-c:a", "copy",
            "-movflags", "+faststart",
            "-y",
            output_path,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )

            self._active[stream_id] = {
                "process": proc,
                "filepath": output_path,
                "stream_url": stream_url,
                "duration": duration,
                "start_time": time.time(),
            }

            LOG.done(f"录制已启动: {stream_id} | {duration}s | {output_path}")

            return {
                "success": True,
                "stream_id": stream_id,
                "filepath": output_path,
                "duration": duration,
            }

        except FileNotFoundError:
            return {"success": False, "error": "ffmpeg未安装或不在PATH中"}
        except Exception as e:
            return {"success": False, "error": f"录制启动异常: {e}"}

    def wait_and_verify(self, stream_id: str) -> dict:
        """等待录制完成并验证文件。

        Args:
            stream_id: 流标识

        Returns:
            {"success": True, "filepath": "...", "size": 123456, "verified": True}
            {"success": False, "error": "..."}
        """
        record = self._active.pop(stream_id, None)
        if record is None:
            return {"success": False, "error": f"录制任务不存在: {stream_id}"}

        proc = record["process"]
        filepath = record["filepath"]
        duration = record["duration"]

        try:
            _stdout, stderr = proc.communicate(timeout=duration + 30)

            # === 验证: 文件存在且大小>0 ===
            if not os.path.exists(filepath):
                return {"success": False, "error": "录制文件未生成到磁盘"}

            file_size = os.path.getsize(filepath)
            if file_size <= 0:
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                return {"success": False, "error": "录制文件为空 (0 bytes)"}

            # === 验证: 文件可播放 (ffprobe) ===
            verified = self._verify_video(filepath)

            LOG.done(f"录制完成并验证: {filepath} | {file_size}B | verified={verified}")

            return {
                "success": True,
                "stream_id": stream_id,
                "filepath": filepath,
                "size_bytes": file_size,
                "duration_seconds": duration,
                "verified": verified,
            }

        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "error": f"录制超时 (> {duration + 30}秒)"}
        except Exception as e:
            return {"success": False, "error": f"录制异常: {e}"}

    def stop_recording(self, stream_id: str) -> dict:
        """手动停止录制。"""
        record = self._active.pop(stream_id, None)
        if record is None:
            return {"success": False, "error": f"录制任务不存在: {stream_id}"}

        proc = record["process"]
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        filepath = record.get("filepath", "")
        file_size = 0
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)

        return {
            "success": True,
            "stream_id": stream_id,
            "filepath": filepath,
            "size_bytes": file_size,
        }

    @staticmethod
    def _verify_video(filepath: str) -> bool:
        """验证视频文件是否可播放 (使用ffprobe)。"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_format",
            "-show_streams",
            filepath,
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            _stdout, stderr = proc.communicate(timeout=10)
            # ffprobe返回0表示有效
            return proc.returncode == 0
        except Exception:
            return False


# ================================================================== #
#  5. 3张图像间隔采集
# ================================================================== #

class IntervalCapture:
    """间隔采集多张图像。

    从RTSP流间隔采集3张图像。
    保存为JPEG到download/image/。
    验证每张文件大小>0且可打开。
    """

    def __init__(self, output_dir: str | None = None) -> None:
        self._screenshot = ScreenshotCapture(output_dir)

    def capture_sequence(
        self,
        stream_url: str,
        count: int = 3,
        interval_seconds: float = 2.0,
        stream_id: str = "",
    ) -> dict:
        """间隔采集count张图像。

        Args:
            stream_url: RTSP流地址
            count: 采集数量 (默认3)
            interval_seconds: 采集间隔(秒, 默认2.0)
            stream_id: 流标识

        Returns:
            {
                "success": True,
                "count": 3,
                "images": [{"filepath": "...", "size": 12345, "verified": True}, ...],
                "total_size": 67890,
            }
        """
        if not stream_id:
            stream_id = f"seq_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        images: list[dict] = []
        total_size = 0

        for i in range(count):
            # 为每张图像生成唯一stream_id
            frame_id = f"{stream_id}_frame{i+1}"
            LOG.info(f"采集第 {i+1}/{count} 张图像...")

            result = self._screenshot.capture(stream_url, stream_id=frame_id)

            if result.get("success"):
                images.append({
                    "frame_number": i + 1,
                    "filepath": result["filepath"],
                    "file_size": result["file_size"],
                    "verified": result.get("verified", False),
                    "elapsed_ms": result.get("elapsed_ms", 0),
                })
                total_size += result["file_size"]
            else:
                return {
                    "success": False,
                    "error": f"第{i+1}张图像采集失败: {result.get('error')}",
                    "captured_count": len(images),
                    "images": images,
                }

            # 间隔等待 (最后一张不需要等待)
            if i < count - 1 and interval_seconds > 0:
                time.sleep(interval_seconds)

        LOG.done(f"间隔采集完成: {count}张 | 总大小={total_size}B | {stream_id}")

        return {
            "success": True,
            "stream_id": stream_id,
            "count": len(images),
            "images": images,
            "total_size": total_size,
        }
