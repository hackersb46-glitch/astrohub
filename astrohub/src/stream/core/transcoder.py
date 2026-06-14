"""
M3 Stream Service v1.0 - 流媒体转码器 (P1)

H264/H265转码、分辨率适配、码率控制。

P1.1: 编码格式检测
P1.2: H264/H265转码
P1.3: 分辨率适配
P1.4: 码率控制

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from src.stream.constants import (
    BITRATE_TOLERANCE_PCT,
    BitrateMode,
    CodecFormat,
    DEFAULT_BITRATE,
    FFMPEG_LOW_LATENCY_FLAGS,
    MAX_BITRATE,
    MIN_BITRATE,
    Resolution,
)
from src.stream.core.logger import LOG


# ------------------------------------------------------------------ #
#  P1.1 - 编码格式检测
# ------------------------------------------------------------------ #

class CodecDetector:
    """编码格式检测器。

    通过FFprobe解析流头部信息，识别H264/H265/MJPEG等编码格式。
    正确识别编码格式，未知编码返回明确错误。
    """

    def __init__(self, ffprobe_path: str = "ffprobe") -> None:
        self._ffprobe_path = ffprobe_path

    async def detect(self, stream_url: str, timeout: int = 10) -> dict:
        """检测流的编码格式。

        Args:
            stream_url: 流地址
            timeout: 超时秒数

        Returns:
            检测结果: {"codec": "h264", "format": "...", "width": 1920, "height": 1080, "fps": 25.0}
            未知编码: {"error": "未知编码格式", "raw_codec_id": "..."}
        """
        probe_cmd = [
            self._ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            "-analyzeduration", "5000000",
            "-probesize", "5000000",
            stream_url,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode != 0:
                return {"error": f"FFprobe执行失败: {stderr.decode('utf-8', errors='ignore')}"}

            data = json.loads(stdout.decode("utf-8"))
            return self._parse_probe_result(data)

        except asyncio.TimeoutError:
            return {"error": f"编码检测超时({timeout}秒)"}
        except FileNotFoundError:
            return {"error": "ffprobe未安装或不在PATH中"}
        except Exception as e:
            return {"error": f"编码检测异常: {e}"}

    def _parse_probe_result(self, data: dict) -> dict:
        """解析FFprobe输出结果。

        Args:
            data: FFprobe输出的JSON数据

        Returns:
            编码检测结果
        """
        streams = data.get("streams", [])
        if not streams:
            return {"error": "未找到视频流"}

        video_stream = None
        for stream in streams:
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            return {"error": "未找到视频流"}

        codec_name = video_stream.get("codec_name", "").lower()
        raw_codec_id = video_stream.get("codec_long_name", "")

        # 映射到CodecFormat
        if "h264" in codec_name:
            codec = CodecFormat.H264.value
        elif "h265" in codec_name or "hevc" in codec_name:
            codec = CodecFormat.H265.value
        elif "mjpeg" in codec_name:
            codec = CodecFormat.MJPEG.value
        else:
            return {"error": f"未知编码格式", "raw_codec_id": raw_codec_id}

        return {
            "codec": codec,
            "raw_codec_id": raw_codec_id,
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "fps": self._extract_fps(video_stream),
            "bitrate": int(video_stream.get("bit_rate", 0)),
            "profile": video_stream.get("profile", "unknown"),
        }

    @staticmethod
    def _extract_fps(stream: dict) -> float:
        """从FFprobe输出中提取帧率。"""
        r_frame_rate = stream.get("r_frame_rate", "0/0")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            try:
                return round(float(num) / float(den), 2) if float(den) != 0 else 0.0
            except ValueError:
                return 0.0
        try:
            return float(r_frame_rate)
        except ValueError:
            return 0.0


# ------------------------------------------------------------------ #
#  P1.2 + P1.3 + P1.4 - FFmpeg转码引擎
# ------------------------------------------------------------------ #

class Transcoder:
    """FFmpeg实时转码引擎。

    支持H264/H265转码、分辨率适配(1080p/720p/480p)、码率控制(CBR/VBR)。
    转码延迟<2秒，CPU占用在可接受范围。
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        self._ffmpeg_path = ffmpeg_path
        self._active_transcodes: dict[str, asyncio.subprocess.Process] = {}
        self._transcode_configs: dict[str, dict] = {}

    def start_transcode(self, stream_id: str, input_url: str, output_url: str,
                        codec: str = CodecFormat.H264.value,
                        resolution: str = Resolution.HD_1080.value,
                        bitrate: int = DEFAULT_BITRATE,
                        bitrate_mode: str = BitrateMode.CBR.value) -> dict:
        """启动转码任务。

        Args:
            stream_id: 流唯一标识
            input_url: 输入流地址
            output_url: 输出流地址
            codec: 输出编码格式 (h264/h265)
            resolution: 输出分辨率 (1920x1080/1280x720/854x480)
            bitrate: 目标码率(kbps)
            bitrate_mode: 码率控制模式 (cbr/vbr)

        Returns:
            启动结果: {"success": True/False, "stream_id": "...", "error": "..."}
        """
        if stream_id in self._active_transcodes:
            return {"success": False, "error": f"转码任务已存在: {stream_id}"}

        # 码率范围校验
        bitrate = min(max(bitrate, MIN_BITRATE), MAX_BITRATE)

        cmd = self._build_ffmpeg_cmd(input_url, output_url, codec, resolution, bitrate, bitrate_mode)

        try:
            # 启动FFmpeg子进程
            import subprocess as _subprocess
            proc = _subprocess.Popen(
                cmd,
                stdout=_subprocess.PIPE,
                stderr=_subprocess.PIPE,
                stdin=_subprocess.DEVNULL,
            )
            self._active_transcodes[stream_id] = proc
            self._transcode_configs[stream_id] = {
                "input_url": input_url,
                "output_url": output_url,
                "codec": codec,
                "resolution": resolution,
                "bitrate": bitrate,
                "bitrate_mode": bitrate_mode,
            }
            LOG.done(f"转码已启动: stream_id={stream_id}, codec={codec}, "
                     f"res={resolution}, bitrate={bitrate}kbps ({bitrate_mode})")
            return {"success": True, "stream_id": stream_id, "pid": proc.pid}
        except FileNotFoundError:
            return {"success": False, "error": "ffmpeg未安装或不在PATH中"}
        except Exception as e:
            return {"success": False, "error": f"转码启动异常: {e}"}

    def stop_transcode(self, stream_id: str) -> dict:
        """停止转码任务。

        Args:
            stream_id: 流唯一标识

        Returns:
            停止结果
        """
        proc = self._active_transcodes.pop(stream_id, None)
        if proc is None:
            return {"success": False, "error": f"转码任务不存在: {stream_id}"}

        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass
            LOG.warning(f"转码停止异常: stream_id={stream_id}, {e}")

        self._transcode_configs.pop(stream_id, None)
        LOG.info(f"转码已停止: stream_id={stream_id}")
        return {"success": True, "stream_id": stream_id}

    def get_transcode_status(self, stream_id: str) -> dict | None:
        """获取转码任务状态。

        Args:
            stream_id: 流唯一标识

        Returns:
            转码配置信息，不存在返回None
        """
        config = self._transcode_configs.get(stream_id)
        if not config:
            return None

        proc = self._active_transcodes.get(stream_id)
        is_running = proc is not None and proc.poll() is None

        return {
            "stream_id": stream_id,
            "is_running": is_running,
            "pid": proc.pid if proc else None,
            **config,
        }

    def list_transcodes(self) -> list[dict]:
        """获取所有转码任务。

        Returns:
            转码任务列表
        """
        results = []
        for stream_id in list(self._transcode_configs.keys()):
            status = self.get_transcode_status(stream_id)
            if status:
                results.append(status)
        return results

    def _build_ffmpeg_cmd(self, input_url: str, output_url: str, codec: str,
                          resolution: str, bitrate: int, bitrate_mode: str) -> list[str]:
        """构建FFmpeg命令。

        P1.2: 编码转码 (H264/H265)
        P1.3: 分辨率适配
        P1.4: 码率控制 (CBR/VBR)
        """
        cmd = [
            self._ffmpeg_path,
            # 低延迟优化 (P3.2)
            *FFMPEG_LOW_LATENCY_FLAGS,
            "-i", input_url,
        ]

        # P1.2 - 编码格式转码
        if codec == CodecFormat.H264.value:
            cmd.extend(["-c:v", "libx264"])
        elif codec == CodecFormat.H265.value:
            cmd.extend(["-c:v", "libx265"])

        # P1.3 - 分辨率适配
        width, height = resolution.split("x")
        cmd.extend(["-s", f"{width}x{height}"])

        # P1.4 - 码率控制
        if bitrate_mode == BitrateMode.CBR.value:
            # CBR模式: 固定码率
            cmd.extend([
                "-b:v", f"{bitrate}k",
                "-maxrate", f"{bitrate}k",
                "-bufsize", f"{bitrate * 2}k",
                "-minrate", f"{bitrate}k",
                "-x264-params", "nal-hrd=cbr:force-cfr=1",
            ])
        else:
            # VBR模式: 可变码率 (±BITRATE_TOLERANCE_PCT)
            cmd.extend([
                "-b:v", f"{bitrate}k",
                "-maxrate", f"{int(bitrate * (1 + BITRATE_TOLERANCE_PCT))}k",
                "-bufsize", f"{int(bitrate * 2)}k",
            ])

        # 输出格式
        cmd.extend([
            "-c:a", "aac",
            "-f", "flv",
            "-movflags", "+faststart",
            output_url,
        ])

        return cmd
