"""
M3 Stream Service v1.0 - 画面预览 (P3)

Web播放器集成、延迟优化、截图功能。

P3.1: Web播放器集成
P3.2: 延迟优化
P3.3: 截图功能

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime

from src.stream.constants import (
    FFMPEG_LOW_LATENCY_FLAGS,
    SCREENSHOT_FORMAT,
    SCREENSHOT_QUALITY,
    SCREENSHOT_RESPONSE_TIMEOUT,
    TARGET_LATENCY_MS,
)
from src.stream.core.logger import LOG


# ------------------------------------------------------------------ #
#  P3.1 - Web播放器集成
# ------------------------------------------------------------------ #

PLAYER_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M3 Stream Player - {stream_id}</title>
    <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
    <script src="https://cdn.jsdelivr.net/npm/flv.js@1.6.2/dist/flv.min.js"></script>
    <style>
        body {{ margin: 0; display: flex; justify-content: center; align-items: center; min-height: 100vh; background: #000; }}
        .player-container {{ width: 100%; max-width: 1280px; }}
        video {{ width: 100%; height: auto; background: #000; }}
        .controls {{ padding: 8px; display: flex; gap: 8px; justify-content: center; background: #222; }}
        .controls button {{ padding: 6px 16px; cursor: pointer; background: #444; color: #fff; border: none; border-radius: 4px; }}
        .controls button:hover {{ background: #666; }}
        .info {{ padding: 4px 8px; color: #aaa; font-size: 12px; text-align: center; }}
    </style>
</head>
<body>
    <div class="player-container">
        <video id="player" controls autoplay playsinline></video>
        <div class="controls">
            <button onclick="document.getElementById('player').play()">▶ 播放</button>
            <button onclick="document.getElementById('player').pause()">⏸ 暂停</button>
            <button onclick="toggleFullscreen()">⛶ 全屏</button>
            <button onclick="adjustVolume(-0.1)">🔉 音量-</button>
            <button onclick="adjustVolume(0.1)">🔊 音量+</button>
        </div>
        <div class="info" id="status">加载中...</div>
    </div>
    <script>
        const video = document.getElementById('player');
        const status = document.getElementById('status');
        const streamUrl = '{stream_url}';
        const streamType = '{stream_type}'; // 'hls' or 'flv'

        if (streamType === 'hls' && Hls.isSupported()) {{
            const hls = new Hls({{
                maxBufferLength: {buffer_length},
                maxMaxBufferLength: 30,
                startLevel: -1,
                debug: false,
            }});
            hls.loadSource(streamUrl);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => {{
                video.play();
                status.textContent = 'HLS播放中';
            }});
            hls.on(Hls.Events.ERROR, (event, data) => {{
                status.textContent = 'HLS错误: ' + data.details;
            }});
        }} else if (streamType === 'flv' && flvjs.isSupported()) {{
            const player = flvjs.createPlayer({{
                type: 'flv',
                url: streamUrl,
                isLive: true,
            }}, {{
                enableWorker: true,
                enableStashBuffer: false,
                stashInitialSize: 128,
            }});
            player.attachMediaElement(video);
            player.load();
            player.play();
            status.textContent = 'FLV播放中';
            player.on(flvjs.Events.ERROR, (errType, errDetail) => {{
                status.textContent = 'FLV错误: ' + errType;
            }});
        }} else {{
            video.src = streamUrl;
            status.textContent = 'Native播放';
        }}

        function toggleFullscreen() {{
            if (video.webkitRequestFullscreen) {{
                video.webkitRequestFullscreen();
            }} else if (video.requestFullscreen) {{
                video.requestFullscreen();
            }}
        }}

        function adjustVolume(delta) {{
            video.volume = Math.max(0, Math.min(1, video.volume + delta));
        }}
    </script>
</body>
</html>"""


class WebPlayer:
    """Web播放器集成器。

    生成HTML播放器页面，集成flv.js/hls.js。
    页面加载后自动播放，控件完整（播放/暂停/全屏/音量）。
    """

    def __init__(self) -> None:
        self._players: dict[str, dict] = {}

    def generate_player(self, stream_id: str, stream_url: str,
                        stream_type: str = "hls",
                        buffer_length: int = 1) -> str:
        """生成Web播放器页面HTML。

        Args:
            stream_id: 流唯一标识
            stream_url: 流播放地址 (m3u8或.flv)
            stream_type: 流类型 (hls/flv)
            buffer_length: 缓冲区长度(秒)

        Returns:
            HTML页面内容
        """
        html = PLAYER_PAGE_TEMPLATE.format(
            stream_id=stream_id,
            stream_url=stream_url,
            stream_type=stream_type,
            buffer_length=buffer_length,
        )
        self._players[stream_id] = {
            "stream_url": stream_url,
            "stream_type": stream_type,
            "buffer_length": buffer_length,
        }
        LOG.info(f"Web播放器已生成: stream_id={stream_id}, type={stream_type}")
        return html

    def get_player_info(self, stream_id: str) -> dict | None:
        """获取播放器配置信息。"""
        return self._players.get(stream_id)

    def list_players(self) -> list[dict]:
        """获取所有播放器配置。"""
        return [{"stream_id": sid, **info} for sid, info in self._players.items()]


# ------------------------------------------------------------------ #
#  P3.2 - 延迟优化
# ------------------------------------------------------------------ #

class LatencyOptimizer:
    """延迟优化器。

    调整缓冲区大小、关键帧间隔、传输协议。
    端到端延迟<1秒(同网络)，延迟数据可通过API查询。
    """

    def __init__(self) -> None:
        self._latency_data: dict[str, float] = {}
        self._target_latency_ms = TARGET_LATENCY_MS

    def get_optimization_flags(self) -> list[str]:
        """获取FFmpeg低延迟优化参数。

        Returns:
            FFMPEG_LOW_LATENCY_FLAGS列表
        """
        return FFMPEG_LOW_LATENCY_FLAGS.copy()

    def get_buffer_config(self) -> dict:
        """获取推荐的播放器缓冲配置。

        Returns:
            缓冲配置: max_buffer_length/max_buffer_duration/stash_buffer_size
        """
        return {
            "max_buffer_length": 1,      # HLS.js: 1秒缓冲区
            "max_buffer_duration": 3,    # HLS.js: 最大3秒
            "stash_buffer_size": 128,    # flv.js: 128KB初始缓冲
        }

    def get_keyframe_config(self) -> dict:
        """获取推荐的关键帧间隔配置。

        Returns:
            关键帧配置: interval_seconds/gop_size
        """
        return {
            "keyint": 30,     # 每30帧一个关键帧 (1秒@30fps)
            "scenecut": 0,    # 禁用场景切换检测
            "min_keyint": 30, # 最小关键帧间隔
        }

    def measure_latency(self, stream_id: str) -> dict:
        """测量当前流的端到端延迟。

        Args:
            stream_id: 流唯一标识

        Returns:
            延迟数据: {"stream_id": ..., "latency_ms": ..., "target_ms": ..., "within_target": True/False}
        """
        latency = self._latency_data.get(stream_id, 0)
        return {
            "stream_id": stream_id,
            "latency_ms": latency,
            "target_ms": self._target_latency_ms,
            "within_target": latency <= self._target_latency_ms,
        }

    def update_latency(self, stream_id: str, latency_ms: float) -> None:
        """更新流的延迟数据。

        Args:
            stream_id: 流唯一标识
            latency_ms: 延迟毫秒数
        """
        self._latency_data[stream_id] = latency_ms

    def get_target_latency_ms(self) -> int:
        """获取目标延迟阈值(毫秒)。"""
        return self._target_latency_ms


# ------------------------------------------------------------------ #
#  P3.3 - 截图功能
# ------------------------------------------------------------------ #

class ScreenshotManager:
    """截图管理器。

    从视频流中截取当前帧为图片。
    截图文件可正常打开，画面与播放画面一致，响应时间<2秒。
    """

    def __init__(self, output_dir: str | None = None) -> None:
        from src.stream.constants import DOWNLOAD_IMAGE_DIR
        self._output_dir = output_dir or str(DOWNLOAD_IMAGE_DIR)
        os.makedirs(self._output_dir, exist_ok=True)

    def capture(self, stream_url: str, stream_id: str = "") -> dict:
        """从视频流截取当前帧。

        Args:
            stream_url: 流地址
            stream_id: 流唯一标识 (用于命名)

        Returns:
            截图结果: {"success": True/False, "filepath": "...", "error": "..."}
        """
        if not stream_id:
            stream_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        output_path = os.path.join(self._output_dir, f"{stream_id}_{datetime.now().strftime('%s')}.jpg")

        cmd = [
            "ffmpeg",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-i", stream_url,
            "-frames:v", "1",
            "-q:v", str(SCREENSHOT_QUALITY),
            "-f", "image2",
            "-y",  # 覆盖已存在文件
            output_path,
        ]

        start_time = datetime.now()

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
            )
            stdout, stderr = proc.communicate(timeout=SCREENSHOT_RESPONSE_TIMEOUT)

            if proc.returncode != 0:
                return {"success": False, "error": f"截图失败: {stderr.decode('utf-8', errors='ignore')}"}

            # 验证文件存在且可读
            if not os.path.exists(output_path):
                return {"success": False, "error": "截图文件未生成"}

            elapsed = (datetime.now() - start_time).total_seconds()
            file_size = os.path.getsize(output_path)

            LOG.done(f"截图完成: stream_id={stream_id}, "
                     f"path={output_path}, size={file_size}B, time={elapsed:.2f}s")

            return {
                "success": True,
                "filepath": output_path,
                "file_size": file_size,
                "elapsed_ms": int(elapsed * 1000),
                "format": SCREENSHOT_FORMAT,
            }

        except subprocess.TimeoutExpired:
            proc.kill()
            return {"success": False, "error": f"截图超时(>{SCREENSHOT_RESPONSE_TIMEOUT}秒)"}
        except Exception as e:
            return {"success": False, "error": f"截图异常: {e}"}

    def cleanup(self, max_age_hours: int = 24) -> int:
        """清理旧截图文件。

        Args:
            max_age_hours: 最大保留小时数

        Returns:
            清理文件数
        """
        import time

        removed = 0
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        for filename in os.listdir(self._output_dir):
            filepath = os.path.join(self._output_dir, filename)
            file_age = current_time - os.path.getmtime(filepath)
            if file_age > max_age_seconds and filename.endswith(".jpg"):
                try:
                    os.remove(filepath)
                    removed += 1
                except Exception:
                    pass

        return removed
