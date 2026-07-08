"""
M3 Stream Service v1.0 - 流分发器 (P2)

WebSocket推流、HTTP-FLV、HLS、多路并发。

P2.1: WebSocket推流
P2.2: HTTP-FLV分发
P2.3: HLS分发
P2.4: 多路并发

Author: 雅痞张@南方天文
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from src.stream.constants import (
    DEFAULT_CONCURRENT_STREAMS,
    HLS_LIST_SIZE,
    HLS_SEGMENT_DURATION,
    HLS_SEGMENT_REMOVAL_DELAY,
    MAX_CONCURRENT_STREAMS,
    WS_MAX_MESSAGE_SIZE,
    WS_PING_INTERVAL,
)
from src.stream.core.logger import LOG


# ------------------------------------------------------------------ #
#  P2.1 - WebSocket推流
# ------------------------------------------------------------------ #

class WebSocketPusher:
    """WebSocket推流器。

    通过WebSocket向客户端推送视频帧。
    建立WebSocket连接后按帧推送H264/H265 NALU数据。
    连接断开后自动清理资源。
    """

    def __init__(self) -> None:
        self._clients: dict[str, list[Any]] = defaultdict(list)  # stream_id -> [ws_connections]
        self._frame_buffer: dict[str, bytes] = {}
        self._running: bool = False

    async def register_client(self, stream_id: str, websocket: Any) -> None:
        """注册WebSocket客户端。

        Args:
            stream_id: 流唯一标识
            websocket: WebSocket连接对象 (fastapi.WebSocket)
        """
        self._clients[stream_id].append(websocket)
        LOG.info(f"WebSocket客户端已连接: stream_id={stream_id}, clients={len(self._clients[stream_id])}")

        try:
            # 推送帧循环
            while True:
                frame = self._frame_buffer.get(stream_id)
                if frame:
                    await websocket.send_bytes(frame)
                await asyncio.sleep(0.01)  # 10ms推送间隔
        except Exception:
            pass  # 连接断开，清理资源
        finally:
            await self.unregister_client(stream_id, websocket)

    async def unregister_client(self, stream_id: str, websocket: Any) -> None:
        """取消注册WebSocket客户端，清理资源。

        Args:
            stream_id: 流唯一标识
            websocket: WebSocket连接对象
        """
        if stream_id in self._clients and websocket in self._clients[stream_id]:
            self._clients[stream_id].remove(websocket)
            LOG.info(f"WebSocket客户端已断开: stream_id={stream_id}, clients={len(self._clients[stream_id])}")

            # 连接数为0时清理
            if not self._clients[stream_id]:
                del self._clients[stream_id]

    async def push_frame(self, stream_id: str, frame_data: bytes) -> None:
        """推送视频帧到所有WebSocket客户端。

        Args:
            stream_id: 流唯一标识
            frame_data: NALU帧数据
        """
        self._frame_buffer[stream_id] = frame_data

        disconnected = []
        for ws in self._clients.get(stream_id, []):
            try:
                await ws.send_bytes(frame_data)
            except Exception:
                disconnected.append(ws)

        # 清理断开的连接
        for ws in disconnected:
            await self.unregister_client(stream_id, ws)

    def get_client_count(self, stream_id: str) -> int:
        """获取流已连接的WebSocket客户端数量。"""
        return len(self._clients.get(stream_id, []))

    @property
    def max_message_size(self) -> int:
        return WS_MAX_MESSAGE_SIZE

    @property
    def ping_interval(self) -> int:
        return WS_PING_INTERVAL


# ------------------------------------------------------------------ #
#  P2.2 - HTTP-FLV分发
# ------------------------------------------------------------------ #

class HttpFlvServer:
    """HTTP-FLV流分发服务器。

    启动HTTP-FLV服务器，监听指定端口，提供.flv流地址。
    多客户端同时拉取不冲突。
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        self._host = host
        self._port = port
        self._server: Any | None = None
        self._stream_data: dict[str, bytes] = {}
        self._flv_headers: dict[str, bytes] = {}

    async def start(self) -> dict:
        """启动HTTP-FLV服务器。

        Returns:
            启动结果
        """
        try:
            from fastapi import FastAPI, Response, Request
            from fastapi.responses import StreamingResponse
            import uvicorn

            app = FastAPI()

            async def flv_stream(request: Request, stream_id: str):
                """HTTP-FLV流处理。"""
                if stream_id not in self._stream_data:
                    return Response(status_code=404, content=f"流不存在: {stream_id}")

                async def generate():
                    flv_header = self._flv_headers.get(stream_id, b"")
                    if flv_header:
                        yield flv_header
                    while True:
                        chunk = self._stream_data.get(stream_id)
                        if chunk:
                            yield chunk
                        await asyncio.sleep(0.01)
                        if not request.is_connected():
                            break

                return StreamingResponse(
                    generate(),
                    media_type="video/x-flv",
                    headers={"Cache-Control": "no-cache"},
                )

            app.get("/stream/{stream_id}.flv")(flv_stream)

            def run_server():
                uvicorn.run(app, host=self._host, port=self._port, log_level="warning")

            self._server_thread = threading.Thread(target=run_server, daemon=True, name="m3-flv-server")
            self._server_thread.start()
            LOG.done(f"HTTP-FLV服务器已启动: http://{self._host}:{self._port}/stream/{{stream_id}}.flv")
            return {"success": True, "url": f"http://{self._host}:{self._port}/stream/{stream_id}.flv"}

        except Exception as e:
            return {"success": False, "error": f"HTTP-FLV服务器启动失败: {e}"}

    @staticmethod
    async def generate_flv_header(stream_id: str) -> bytes:
        """生成FLV文件头。"""
        # FLV header: "FLV" + version(1) + flags(1) + header_size(4)
        header = bytearray()
        header.extend(b"FLV")
        header.append(1)  # version
        header.append(0x05)  # audio+video flags
        header.extend(b"\x00\x00\x00\x09")  # header size
        return bytes(header)

    def get_stream_url(self, stream_id: str) -> str:
        """获取HTTP-FLV流地址。"""
        return f"http://{self._host}:{self._port}/stream/{stream_id}.flv"


# ------------------------------------------------------------------ #
#  P2.3 - HLS分发
# ------------------------------------------------------------------ #

class HlsDistributor:
    """HLS分发器。

    生成m3u8播放列表和ts切片文件，设置切片时长。
    浏览器可通过HLS播放器正常播放，切片生成延迟<3秒，旧切片自动清理。
    """

    def __init__(self, output_dir: str | None = None) -> None:
        self._output_dir = output_dir or "/tmp/hls"
        self._hls_streams: dict[str, dict] = {}
        os.makedirs(self._output_dir, exist_ok=True)

    def start_hls(self, stream_id: str, input_url: str, segment_duration: int = HLS_SEGMENT_DURATION,
                  list_size: int = HLS_LIST_SIZE) -> dict:
        """启动HLS分发。

        Args:
            stream_id: 流唯一标识
            input_url: 输入流地址
            segment_duration: ts切片时长(秒)
            list_size: m3u8最大切片数

        Returns:
            启动结果
        """
        import subprocess as _subprocess
        import os

        stream_dir = os.path.join(self._output_dir, stream_id)
        os.makedirs(stream_dir, exist_ok=True)

        m3u8_path = os.path.join(stream_dir, "playlist.m3u8")
        ts_pattern = os.path.join(stream_dir, f"segment_%03d.ts")

        cmd = [
            "ffmpeg",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-i", input_url,
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", "hls",
            "-hls_time", str(segment_duration),
            "-hls_list_size", str(list_size),
            "-hls_segment_filename", ts_pattern,
            "-hls_delete_threshold", str(list_size + 1),
            m3u8_path,
        ]

        try:
            proc = _subprocess.Popen(
                cmd,
                stdout=_subprocess.PIPE,
                stderr=_subprocess.PIPE,
                stdin=_subprocess.DEVNULL,
            )
            self._hls_streams[stream_id] = {
                "process": proc,
                "m3u8_path": m3u8_path,
                "stream_dir": stream_dir,
                "input_url": input_url,
                "segment_duration": segment_duration,
                "list_size": list_size,
                "started_at": self._now_iso(),
            }
            LOG.done(f"HLS分发已启动: stream_id={stream_id}, m3u8={m3u8_path}")
            return {"success": True, "stream_id": stream_id, "playlist_url": f"/hls/{stream_id}/playlist.m3u8"}
        except Exception as e:
            return {"success": False, "error": f"HLS启动失败: {e}"}

    def stop_hls(self, stream_id: str) -> dict:
        """停止HLS分发。

        Args:
            stream_id: 流唯一标识

        Returns:
            停止结果
        """
        stream_info = self._hls_streams.pop(stream_id, None)
        if not stream_info:
            return {"success": False, "error": f"HLS流不存在: {stream_id}"}

        proc = stream_info.get("process")
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # 旧切片自动清理 (P2.3)
        self._cleanup_old_segments(stream_info.get("stream_dir", ""), delay=HLS_SEGMENT_REMOVAL_DELAY)

        LOG.info(f"HLS分发已停止: stream_id={stream_id}")
        return {"success": True, "stream_id": stream_id}

    def get_hls_status(self, stream_id: str) -> dict | None:
        """获取HLS分发状态。"""
        stream_info = self._hls_streams.get(stream_id)
        if not stream_info:
            return None

        proc = stream_info.get("process")
        is_running = proc is not None and proc.poll() is None

        return {
            "stream_id": stream_id,
            "is_running": is_running,
            "m3u8_path": stream_info.get("m3u8_path"),
            "segment_duration": stream_info.get("segment_duration"),
            "list_size": stream_info.get("list_size"),
        }

    @staticmethod
    def _cleanup_old_segments(stream_dir: str, delay: int = HLS_SEGMENT_REMOVAL_DELAY) -> None:
        """清理超过保留周期的旧ts切片。"""
        import os
        import time

        if not os.path.exists(stream_dir):
            return

        current_time = time.time()
        for filename in os.listdir(stream_dir):
            if filename.endswith(".ts") or (filename.endswith(".m3u8") and "backup" in filename):
                filepath = os.path.join(stream_dir, filename)
                file_age = current_time - os.path.getmtime(filepath)
                if file_age > delay:
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()


# ------------------------------------------------------------------ #
#  P2.4 - 多路并发控制
# ------------------------------------------------------------------ #

class ConcurrentStreamManager:
    """多路并发管理器。

    同时处理多路视频流，配置并发路数(默认4路)。
    超过限制时排队或拒绝并返回明确提示。
    """

    def __init__(self, max_streams: int = DEFAULT_CONCURRENT_STREAMS) -> None:
        self._max_streams = min(max_streams, MAX_CONCURRENT_STREAMS)
        self._active_streams: dict[str, dict] = {}
        self._queue: list[dict] = []

    def can_accept_stream(self) -> bool:
        """检查是否可以接受新流。"""
        return len(self._active_streams) < self._max_streams

    def add_stream(self, stream_id: str, stream_config: dict) -> dict:
        """添加流到并发池。

        Args:
            stream_id: 流唯一标识
            stream_config: 流配置信息

        Returns:
            添加结果: {"success": True/False, "stream_id": "...", "queued": True/False, "error": "..."}
        """
        if stream_id in self._active_streams:
            return {"success": False, "error": f"流已存在: {stream_id}"}

        if len(self._active_streams) >= self._max_streams:
            # 超过限制，加入队列
            self._queue.append({"stream_id": stream_id, "config": stream_config})
            LOG.warning(f"并发已达上限({self._max_streams})，流已加入队列: stream_id={stream_id}")
            return {
                "success": False,
                "error": f"并发流数已达上限({self._max_streams})，流已加入队列等待",
                "queued": True,
                "queue_position": len(self._queue),
            }

        self._active_streams[stream_id] = {
            **stream_config,
            "started_at": datetime.now().isoformat(),
        }
        LOG.info(f"并发流已添加: stream_id={stream_id}, 当前={len(self._active_streams)}/{self._max_streams}")
        return {"success": True, "stream_id": stream_id}

    def remove_stream(self, stream_id: str) -> dict:
        """从并发池移除流。

        Args:
            stream_id: 流唯一标识

        Returns:
            移除结果
        """
        if stream_id not in self._active_streams:
            return {"success": False, "error": f"流不存在: {stream_id}"}

        del self._active_streams[stream_id]

        # 处理队列中的下一个
        self._process_queue()

        LOG.info(f"并发流已移除: stream_id={stream_id}, 当前={len(self._active_streams)}/{self._max_streams}")
        return {"success": True, "stream_id": stream_id}

    def get_concurrency_status(self) -> dict:
        """获取当前并发状态。

        Returns:
            并发状态: active_count/max_streams/queue/stream_ids
        """
        return {
            "active_count": len(self._active_streams),
            "max_streams": self._max_streams,
            "queue_count": len(self._queue),
            "stream_ids": list(self._active_streams.keys()),
            "queue": [q["stream_id"] for q in self._queue],
        }

    def _process_queue(self) -> None:
        """处理队列中的下一个流。"""
        if self._queue and len(self._active_streams) < self._max_streams:
            next_stream = self._queue.pop(0)
            stream_id = next_stream["stream_id"]
            self._active_streams[stream_id] = {
                **next_stream["config"],
                "started_at": datetime.now().isoformat(),
            }
            LOG.info(f"队列中的流已激活: stream_id={stream_id}")
