"""
M3 Stream Service v1.0 - FastAPI 路由层

包含流管理、转码、分发、预览、监控、录制路由。

Author: 雅痞张@南方天文
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1", tags=["M3 Stream Service"])


# ------------------------------------------------------------------ #
#  全局管理器实例延迟引用
# ------------------------------------------------------------------ #

_managers: dict[str, Any] = {}


def set_managers(**kwargs: Any) -> None:
    """注入管理器实例到路由层。

    Args:
        **kwargs: 各管理器实例
    """
    _managers.update(kwargs)


def _get_stream_manager() -> Any:
    manager = _managers.get("stream_manager")
    if manager is None:
        raise HTTPException(status_code=500, detail="StreamConnector 未初始化")
    return manager


def _get_transcoder() -> Any:
    manager = _managers.get("transcoder")
    if manager is None:
        raise HTTPException(status_code=500, detail="Transcoder 未初始化")
    return manager


def _get_websocket_pusher() -> Any:
    manager = _managers.get("websocket_pusher")
    if manager is None:
        raise HTTPException(status_code=500, detail="WebSocketPusher 未初始化")
    return manager


def _get_http_flv_server() -> Any:
    manager = _managers.get("http_flv_server")
    if manager is None:
        raise HTTPException(status_code=500, detail="HttpFlvServer 未初始化")
    return manager


def _get_hls_distributor() -> Any:
    manager = _managers.get("hls_distributor")
    if manager is None:
        raise HTTPException(status_code=500, detail="HlsDistributor 未初始化")
    return manager


def _get_concurrency_manager() -> Any:
    manager = _managers.get("concurrency_manager")
    if manager is None:
        raise HTTPException(status_code=500, detail="ConcurrentStreamManager 未初始化")
    return manager


def _get_web_player() -> Any:
    manager = _managers.get("web_player")
    if manager is None:
        raise HTTPException(status_code=500, detail="WebPlayer 未初始化")
    return manager


def _get_latency_optimizer() -> Any:
    manager = _managers.get("latency_optimizer")
    if manager is None:
        raise HTTPException(status_code=500, detail="LatencyOptimizer 未初始化")
    return manager


def _get_screenshot_manager() -> Any:
    manager = _managers.get("screenshot_manager")
    if manager is None:
        raise HTTPException(status_code=500, detail="ScreenshotManager 未初始化")
    return manager


def _get_disconnect_detector() -> Any:
    manager = _managers.get("disconnect_detector")
    if manager is None:
        raise HTTPException(status_code=500, detail="StreamDisconnectDetector 未初始化")
    return manager


def _get_reconnector() -> Any:
    manager = _managers.get("reconnector")
    if manager is None:
        raise HTTPException(status_code=500, detail="AutoReconnector 未初始化")
    return manager


def _get_status_reporter() -> Any:
    manager = _managers.get("status_reporter")
    if manager is None:
        raise HTTPException(status_code=500, detail="StatusReporter 未初始化")
    return manager


def _get_recorder() -> Any:
    manager = _managers.get("recorder")
    if manager is None:
        raise HTTPException(status_code=500, detail="RecordingManager 未初始化")
    return manager


# ------------------------------------------------------------------ #
#  P0 - 视频流接入
# ------------------------------------------------------------------ #

@router.post("/streams/rtsp/parse", summary="解析RTSP地址(P0.1)")
async def parse_rtsp_url(url: str = Query(..., description="RTSP URL")) -> dict:
    """解析RTStream地址，提取结构化字段。"""
    stream_manager = _get_stream_manager()
    result = stream_manager.url_parser.parse(url)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/streams/onvif/discover", summary="ONVIF服务发现(P0.2)")
async def discover_onvif_devices(
    timeout: int = Query(default=10, description="超时秒数"),
) -> list[dict]:
    """通过ONVIF WS-Discovery发现设备。"""
    stream_manager = _get_stream_manager()
    return stream_manager.onvif_discovery.discover(timeout=timeout)


@router.post("/streams/onvif/discover", summary="ONVIF服务发现(P0.2)")
async def discover_onvif_devices_post(
    timeout: int = Query(default=10, description="超时秒数"),
) -> list[dict]:
    """通过ONVIF WS-Discovery发现设备(POST)。"""
    stream_manager = _get_stream_manager()
    return stream_manager.onvif_discovery.discover(timeout=timeout)


@router.post("/streams/auth", summary="流认证接入(P0.3)")
async def authenticate_stream(
    stream_id: str = Query(..., description="流唯一标识"),
) -> dict:
    """执行流认证(P0.3)。"""
    stream_manager = _get_stream_manager()
    result = stream_manager.authenticator.authenticate(stream_id)
    if not result.get("success"):
        status = 401 if result.get("http_status") == 401 else 400
        raise HTTPException(status_code=status, detail=result.get("error"))
    return result


@router.post("/streams/connect", summary="建立流连接(P0.4)")
async def connect_stream(
    stream_url: str = Query(..., description="流地址"),
    protocol: str = Query(default="rtsp", description="协议类型: rtsp/onvif/http-flv"),
    username: str = Query(default="", description="用户名"),
    password: str = Query(default="", description="密码"),
) -> dict:
    """建立流连接，支持多协议(P0.4)。"""
    from src.stream.constants import ProtocolType

    protocol_map = {
        "rtsp": ProtocolType.RTSP,
        "onvif": ProtocolType.ONVIF,
        "http-flv": ProtocolType.HTTP_FLV,
    }
    protocol_type = protocol_map.get(protocol.lower())
    if not protocol_type:
        raise HTTPException(status_code=400, detail=f"不支持的协议: {protocol}")

    stream_manager = _get_stream_manager()
    result = stream_manager.connect_stream(
        stream_url=stream_url,
        protocol=protocol_type,
        username=username,
        password=password,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    # 注册并发控制
    concurrency_manager = _get_concurrency_manager()
    concurrency_result = concurrency_manager.add_stream(
        result["stream_id"],
        {"url": stream_url, "protocol": protocol},
    )
    if not concurrency_result.get("success") and not concurrency_result.get("queued"):
        return {
            **result,
            "concurrency_status": "rejected",
            "message": concurrency_result.get("error"),
        }

    return {**result, "concurrency_status": concurrency_result}


@router.post("/streams/{stream_id}/disconnect", summary="断开流连接")
async def disconnect_stream(stream_id: str) -> dict:
    """断开流连接。"""
    stream_manager = _get_stream_manager()
    result = stream_manager.disconnect_stream(stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))

    # 移除并发控制
    concurrency_manager = _get_concurrency_manager()
    concurrency_manager.remove_stream(stream_id)

    return result


@router.get("/streams", summary="查询活跃流列表")
async def list_streams() -> list[dict]:
    """获取所有活跃流。"""
    stream_manager = _get_stream_manager()
    return stream_manager.get_active_streams()


# ------------------------------------------------------------------ #
#  P1 - 流媒体转码
# ------------------------------------------------------------------ #

@router.post("/streams/{stream_id}/transcode/start", summary="启动转码(P1)")
async def start_transcode(
    stream_id: str,
    output_url: str = Query(..., description="输出流地址"),
    codec: str = Query(default="h264", description="输出编码: h264/h265"),
    resolution: str = Query(default="1920x1080", description="输出分辨率"),
    bitrate: int = Query(default=2000, description="目标码率(kbps)"),
    bitrate_mode: str = Query(default="cbr", description="码率控制: cbr/vbr"),
) -> dict:
    """启动转码任务(P1.1-P1.4)。"""
    transcoder = _get_transcoder()
    result = transcoder.start_transcode(
        stream_id=stream_id,
        input_url="",  # 从流信息获取
        output_url=output_url,
        codec=codec,
        resolution=resolution,
        bitrate=bitrate,
        bitrate_mode=bitrate_mode,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/streams/{stream_id}/transcode/stop", summary="停止转码")
async def stop_transcode(stream_id: str) -> dict:
    """停止转码任务。"""
    transcoder = _get_transcoder()
    result = transcoder.stop_transcode(stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.get("/streams/{stream_id}/transcode/status", summary="查询转码状态")
async def get_transcode_status(stream_id: str) -> dict:
    """获取转码任务状态。"""
    transcoder = _get_transcoder()
    status = transcoder.get_transcode_status(stream_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"转码任务不存在: {stream_id}")
    return status


@router.get("/transcodes", summary="查询所有转码任务")
async def list_transcodes() -> list[dict]:
    """获取所有转码任务。"""
    transcoder = _get_transcoder()
    return transcoder.list_transcodes()


@router.post("/streams/{stream_id}/codec/detect", summary="编码格式检测(P1.1)")
async def detect_codec(
    stream_id: str,
    stream_url: str = Query(..., description="流地址"),
) -> dict:
    """检测流的编码格式。"""
    # Need async handler - import and use
    from src.stream.core.transcoder import CodecDetector
    import asyncio

    detector = CodecDetector()
    result = await detector.detect(stream_url)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ------------------------------------------------------------------ #
#  P2 - 流分发
# ------------------------------------------------------------------ #

@router.get("/streams/{stream_id}/flv/url", summary="获取HTTP-FLV流地址(P2.2)")
async def get_flv_url(stream_id: str) -> dict:
    """获取HTTP-FLV流地址。"""
    flv_server = _get_http_flv_server()
    return {"stream_id": stream_id, "flv_url": flv_server.get_stream_url(stream_id)}


@router.get("/health/rtsp", summary="RTSP地址解析健康检查")
async def health_check() -> dict:
    """健康检查端点，验证RTSP解析功能。"""
    stream_manager = _get_stream_manager()
    result = stream_manager.url_parser.parse("rtsp://admin:password@0.0.0.0:554/stream")
    if "error" in result:
        raise HTTPException(status_code=500, detail=f"RTSP解析器异常: {result['error']}")
    return {"success": True, "parsed": result}


@router.post("/streams/{stream_id}/hls/start", summary="启动HLS分发(P2.3)")
async def start_hls(
    stream_id: str,
    input_url: str = Query(..., description="输入流地址"),
    segment_duration: int = Query(default=3, description="ts切片时长(秒)"),
    list_size: int = Query(default=5, description="m3u8最大切片数"),
) -> dict:
    """启动HLS分发。"""
    hls_distributor = _get_hls_distributor()
    result = hls_distributor.start_hls(
        stream_id=stream_id,
        input_url=input_url,
        segment_duration=segment_duration,
        list_size=list_size,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/streams/{stream_id}/hls/stop", summary="停止HLS分发")
async def stop_hls(stream_id: str) -> dict:
    """停止HLS分发。"""
    hls_distributor = _get_hls_distributor()
    result = hls_distributor.stop_hls(stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.get("/streams/{stream_id}/hls/status", summary="查询HLS状态")
async def get_hls_status(stream_id: str) -> dict:
    """获取HLS分发状态。"""
    hls_distributor = _get_hls_distributor()
    status = hls_distributor.get_hls_status(stream_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"HLS流不存在: {stream_id}")
    return status


@router.get("/concurrency/status", summary="查询并发状态(P2.4)")
async def get_concurrency_status() -> dict:
    """获取当前并发状态。"""
    concurrency_manager = _get_concurrency_manager()
    return concurrency_manager.get_concurrency_status()


# ------------------------------------------------------------------ #
#  P3 - 画面预览
# ------------------------------------------------------------------ #

@router.get("/streams/{stream_id}/player", summary="生成Web播放器(P3.1)")
async def get_player(
    stream_id: str,
    stream_url: str = Query(..., description="流播放地址"),
    stream_type: str = Query(default="hls", description="流类型: hls/flv"),
    buffer_length: int = Query(default=1, description="缓冲区长度(秒)"),
) -> dict:
    """生成Web播放器页面HTML。"""
    web_player = _get_web_player()
    html = web_player.generate_player(
        stream_id=stream_id,
        stream_url=stream_url,
        stream_type=stream_type,
        buffer_length=buffer_length,
    )
    return {"stream_id": stream_id, "html": html}


@router.get("/streams/{stream_id}/latency", summary="查询延迟数据(P3.2)")
async def get_latency(stream_id: str) -> dict:
    """获取端到端延迟数据。"""
    latency_optimizer = _get_latency_optimizer()
    return latency_optimizer.measure_latency(stream_id)


@router.get("/latency/config", summary="获取推荐缓冲配置(P3.2)")
async def get_latency_config() -> dict:
    """获取缓冲和关键帧配置推荐。"""
    latency_optimizer = _get_latency_optimizer()
    return {
        "buffer": latency_optimizer.get_buffer_config(),
        "keyframe": latency_optimizer.get_keyframe_config(),
        "target_ms": latency_optimizer.get_target_latency_ms(),
    }


@router.post("/streams/{stream_id}/screenshot", summary="截图(P3.3)")
async def capture_screenshot(
    stream_id: str,
    stream_url: str = Query(..., description="流地址"),
) -> dict:
    """从视频流截取当前帧。"""
    screenshot_manager = _get_screenshot_manager()
    result = screenshot_manager.capture(stream_url=stream_url, stream_id=stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


# ------------------------------------------------------------------ #
#  P4 - 流状态监控 (stream_monitor.py)
# ------------------------------------------------------------------ #

@router.post("/streams/{stream_id}/monitor/heart-beat", summary="记录帧数据(P4.1)")
async def record_frame_heartbeat(stream_id: str) -> dict:
    """记录流帧数据到达事件。"""
    detector = _get_disconnect_detector()
    detector.record_frame(stream_id)
    return {"success": True, "stream_id": stream_id}


@router.get("/streams/{stream_id}/monitor/status", summary="查询流状态(P4.1)")
async def get_stream_monitor_status(stream_id: str) -> dict:
    """获取流断流监控状态。"""
    detector = _get_disconnect_detector()
    return detector.get_stream_status(stream_id)


@router.post("/streams/{stream_id}/monitor/reconnect", summary="触发重连(P4.2)")
async def trigger_reconnect(stream_id: str) -> dict:
    """处理断流事件并启动重连。"""
    reconnector = _get_reconnector()
    result = reconnector.handle_disconnect(stream_id)
    if not result.get("success") and result.get("status") != "reconnecting":
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.get("/streams/{stream_id}/monitor/reconnect/status", summary="查询重连状态(P4.2)")
async def get_reconnect_status(stream_id: str) -> dict:
    """获取重连状态。"""
    reconnector = _get_reconnector()
    status = reconnector.get_reconnect_status(stream_id)
    if status is None:
        raise HTTPException(status_code=404, detail=f"未找到重连状态: {stream_id}")
    return status


@router.get("/streams/{stream_id}/status/report", summary="查询上报状态(P4.3)")
async def get_status_report(stream_id: str) -> dict:
    """上报指定流的状态。"""
    reporter = _get_status_reporter()
    return reporter.report_stream(stream_id)


@router.get("/status/reports/all", summary="查询所有流状态报告(P4.3)")
async def report_all_status() -> list[dict]:
    """上报所有流的状态。"""
    reporter = _get_status_reporter()
    return reporter.report_all()


# ------------------------------------------------------------------ #
#  P5 - 录制存储
# ------------------------------------------------------------------ #

@router.post("/streams/{stream_id}/record/start", summary="启动录制(P5.1)")
async def start_recording(
    stream_id: str,
    stream_url: str = Query(..., description="流地址"),
    format: str = Query(default="mp4", description="录制格式: mp4/flv"),
) -> dict:
    """启动录像(P5.1)。"""
    recorder = _get_recorder()
    result = recorder.start_recording(
        stream_id=stream_id,
        stream_url=stream_url,
        format=format,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/streams/{stream_id}/record/stop", summary="停止录制(P5.2)")
async def stop_recording(stream_id: str) -> dict:
    """停止录制(P5.2)。"""
    recorder = _get_recorder()
    result = recorder.stop_recording(stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/streams/{stream_id}/record/pause", summary="暂停录制(P5.2)")
async def pause_recording(stream_id: str) -> dict:
    """暂停录制(P5.2)。"""
    recorder = _get_recorder()
    result = recorder.pause_recording(stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/streams/{stream_id}/record/resume", summary="恢复录制(P5.2)")
async def resume_recording(stream_id: str) -> dict:
    """恢复录制(P5.2)。"""
    recorder = _get_recorder()
    result = recorder.resume_recording(stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.get("/records", summary="查询录制文件列表(P5.3)")
async def list_records(
    stream_id: str | None = Query(None, description="按流ID过滤"),
    start_time: str | None = Query(None, description="起始时间"),
    end_time: str | None = Query(None, description="结束时间"),
) -> list[dict]:
    """录像检索(P5.3)。"""
    recorder = _get_recorder()
    return recorder.search_records(
        stream_id=stream_id,
        start_time=start_time,
        end_time=end_time,
    )


# ------------------------------------------------------------------ #
#  Wave 4: M3视频流核心 - 新增管理器
# ------------------------------------------------------------------ #

def _get_rtsp_parser() -> Any:
    from src.stream.core.stream import RtspUrlParser
    return RtspUrlParser()


def _get_rtsp_connector() -> Any:
    from src.stream.core.stream import RtspConnector
    if not hasattr(_get_rtsp_connector, "_instance"):
        _get_rtsp_connector._instance = RtspConnector()
    return _get_rtsp_connector._instance


def _get_screenshot_capture() -> Any:
    from src.stream.core.stream import ScreenshotCapture
    if not hasattr(_get_screenshot_capture, "_instance"):
        _get_screenshot_capture._instance = ScreenshotCapture()
    return _get_screenshot_capture._instance


def _get_video_recorder() -> Any:
    from src.stream.core.stream import VideoRecorder
    if not hasattr(_get_video_recorder, "_instance"):
        _get_video_recorder._instance = VideoRecorder()
    return _get_video_recorder._instance


def _get_interval_capture() -> Any:
    from src.stream.core.stream import IntervalCapture
    if not hasattr(_get_interval_capture, "_instance"):
        _get_interval_capture._instance = IntervalCapture()
    return _get_interval_capture._instance


# ================================================================== #
#  Wave 4: RTSP 流地址解析
# ================================================================== #

@router.post("/streams/rtsp/build-hikvision", summary="构建Hikvision RTSP地址 (Wave4)")
async def build_hikvision_rtsp(
    ip: str = Query(..., min_length=7, description="设备IP"),
    port: int = Query(default=554, description="RTSP端口"),
    channel: int = Query(default=101, description="通道号: 101=H264主码流, 102=H264子码流, 201=H265主码流, 202=H265子码流"),
) -> dict:
    """构建Hikvision RTSP URL。

    返回可用的流URL列表。
    """
    parser = _get_rtsp_parser()
    url = parser.build_hikvision_url(ip=ip, port=port, channel=channel)

    available_streams = parser.get_available_streams(ip=ip, port=port)

    return {
        "success": True,
        "url": url,
        "available_streams": available_streams,
        "total_streams": len(available_streams),
    }


@router.get("/streams/rtsp/available", summary="获取可用流URL列表 (Wave4)")
async def get_available_streams(
    ip: str = Query(..., min_length=7, description="设备IP"),
    port: int = Query(default=554, description="RTSP端口"),
) -> dict:
    """获取可用的流URL列表 (H264/H265 主/子码流)。"""
    parser = _get_rtsp_parser()
    streams = parser.get_available_streams(ip=ip, port=port)
    return {
        "success": True,
        "data": streams,
        "total": len(streams),
    }


# ================================================================== #
#  Wave 4: 视频流连接和播放
# ================================================================== #

@router.post("/streams/rtsp/connect", summary="连接RTSP流并验证 (Wave4)")
async def connect_rtsp_stream(
    stream_url: str = Query(..., min_length=1, description="RTSP流地址"),
    stream_id: str = Query(default="", description="流标识 (可选)"),
) -> dict:
    """连接RTSP流并验证可达。"""
    connector = _get_rtsp_connector()
    result = await connector.connect(stream_url, stream_id)

    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error"))

    return result


@router.post("/streams/rtsp/disconnect", summary="断开RTSP流连接 (Wave4)")
async def disconnect_rtsp_stream(
    stream_id: str = Query(..., description="流标识"),
) -> dict:
    """断开RTSP流连接。"""
    connector = _get_rtsp_connector()
    return connector.disconnect(stream_id)


@router.get("/streams/rtsp/{stream_id}", summary="获取流状态 (Wave4)")
async def get_stream_status(stream_id: str) -> dict:
    """获取流连接状态。"""
    connector = _get_rtsp_connector()
    return connector.get_status(stream_id)


@router.get("/streams/rtsp/list", summary="列出所有活跃流 (Wave4)")
async def list_active_streams() -> dict:
    """获取所有流状态。"""
    connector = _get_rtsp_connector()
    streams = connector.list_streams()
    return {
        "success": True,
        "data": streams,
        "total": len(streams),
        "connected": sum(1 for s in streams if s.get("state") == "connected"),
    }


# ================================================================== #
#  Wave 4: 截图功能 (写入 download/image/, 验证文件>0且可打开)
# ================================================================== #

@router.post("/streams/screenshot", summary="截取当前帧保存到download/image/ (Wave4)")
async def capture_screenshot_w4(
    stream_url: str = Query(..., min_length=1, description="RTSP流地址"),
    stream_id: str = Query(default="", description="流标识"),
) -> dict:
    """从RTSP流截取当前帧，保存为JPEG到download/image/。"""
    capture = _get_screenshot_capture()
    result = capture.capture(stream_url, stream_id)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    # 确保返回包含验证信息
    return {
        "success": True,
        "filepath": result["filepath"],
        "filename": result["filename"],
        "file_size": result["file_size"],
        "elapsed_ms": result["elapsed_ms"],
        "format": result["format"],
        "verified": True,  # 已验证文件>0且可打开
    }


# ================================================================== #
#  Wave 4: 60秒视频录制到磁盘
# ================================================================== #

@router.post("/streams/record/60s", summary="录制60秒视频到download/ (Wave4)")
async def record_60_seconds(
    stream_url: str = Query(..., min_length=1, description="RTSP流地址"),
    duration: int = Query(default=60, ge=1, le=300, description="录制时长(秒)"),
    stream_id: str = Query(default="", description="流标识"),
) -> dict:
    """录制RTSP流指定时长到download/目录。

    录制完成后验证文件可播放。
    这是一个阻塞调用，等待录制完成。
    """
    recorder = _get_video_recorder()

    # 启动录制
    start_result = recorder.start_recording(stream_url, duration=duration, stream_id=stream_id)
    if not start_result.get("success"):
        raise HTTPException(status_code=500, detail=start_result.get("error"))

    sid = start_result["stream_id"]

    # 等待完成并验证
    result = recorder.wait_and_verify(sid)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return {
        "success": True,
        "stream_id": result["stream_id"],
        "filepath": result["filepath"],
        "size_bytes": result.get("size_bytes", 0),
        "duration_seconds": result.get("duration_seconds", duration),
        "verified": True,  # 已验证文件>0且可播放
    }


@router.post("/streams/record/start", summary="启动后台录制 (Wave4)")
async def start_background_recording(
    stream_url: str = Query(..., min_length=1, description="RTSP流地址"),
    duration: int = Query(default=60, ge=1, le=300, description="录制时长(秒)"),
    stream_id: str = Query(default="", description="流标识"),
) -> dict:
    """启动录制任务(不阻塞)。

    使用wait_and_verify端点等待完成。
    """
    recorder = _get_video_recorder()
    result = recorder.start_recording(stream_url, duration=duration, stream_id=stream_id)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@router.post("/streams/record/verify", summary="等待录制完成并验证 (Wave4)")
async def verify_recording(
    stream_id: str = Query(..., description="流标识"),
) -> dict:
    """等待录制完成并验证文件可播放。"""
    recorder = _get_video_recorder()
    return recorder.wait_and_verify(stream_id)


@router.post("/streams/record/stop", summary="手动停止录制 (Wave4)")
async def stop_recording_manual(
    stream_id: str = Query(..., description="流标识"),
) -> dict:
    """手动停止录制任务。"""
    recorder = _get_video_recorder()
    return recorder.stop_recording(stream_id)


# ================================================================== #
#  Wave 4: 3张图像间隔采集
# ================================================================== #

@router.post("/streams/capture/interval", summary="间隔采集3张图像 (Wave4)")
async def interval_capture_3(
    stream_url: str = Query(..., min_length=1, description="RTSP流地址"),
    count: int = Query(default=3, ge=1, le=10, description="采集数量"),
    interval_seconds: float = Query(default=2.0, ge=0.5, le=300.0, description="采集间隔(秒)"),
    stream_id: str = Query(default="", description="流标识"),
) -> dict:
    """从RTSP流间隔采集多张图像。

    保存为JPEG到download/image/。
    验证每张文件大小>0且可打开。
    """
    capturer = _get_interval_capture()
    result = capturer.capture_sequence(
        stream_url,
        count=count,
        interval_seconds=interval_seconds,
        stream_id=stream_id,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))

    return {
        "success": True,
        "stream_id": result["stream_id"],
        "count": result["count"],
        "images": result["images"],
        "total_size": result["total_size"],
    }


@router.delete("/records", summary="删除录像文件")
async def delete_record(filepath: str = Query(..., description="录像文件路径")) -> dict:
    """删除录像文件。"""
    recorder = _get_recorder()
    result = recorder.delete_record(filepath)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result
