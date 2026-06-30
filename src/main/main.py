#!/usr/bin/env python
"""M12 Integration - WebSocket proxy port 7682"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import asyncio
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import aiohttp

from src.main.core.orchestrator import Orchestrator
from src.main.constants import VERSION, PROJECT_NAME, AUTHOR
from src.api.router import api_router, health_router, set_managers
from src.config_paths import ensure_directories, get_web_dir, get_index_html
from src.config import HOST, PORT
from src.logger import get_logger

# 校准路由 (v7.12: 模块已删除)
# from calibrate.router import router as calibrate_router

# Live Stack 路由 (v7.12: 模块已删除)
# from stack.router import router as stack_router

log = get_logger(__name__)

templates = Jinja2Templates(directory=str(get_web_dir()))
_orchestrator = None
_isapi_session = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator, _isapi_session
    ensure_directories()
    log.info(f"{PROJECT_NAME} v{VERSION} starting...")
    
    _orchestrator = Orchestrator()
    await _orchestrator.start()
    
    # v6.10: 直接创建管理器实例
    from src.core.ptz_controller import PTZDeviceController
    from src.core.device_manager import DeviceManager
    from src.core.calibration_manager import CalibrationManager
    
    ptz_mgr = PTZDeviceController()
    device_mgr = DeviceManager()
    calib_mgr = CalibrationManager()
    
    # 存储到 app.state 供 ISAPI 代理使用
    app.state.ptz_controller = ptz_mgr
    
    # StreamIn: 注入 app.state，WebSocket 代理需要访问 ptz_controller
    set_app_state(app.state)
    
    set_managers(
        ptz_controller=ptz_mgr,
        device_manager=device_mgr,
        calibration_manager=calib_mgr
    )
    log.info("Managers registered")
    
    # v6.01: 启动时执行一次 SADP 发现，合并网关信息到 ptz_config
    try:
        log.info("Discovery devices with SADP...")
        from src.core.sadp_discovery import SADPManager
        sadp_mgr = SADPManager()
        raw_devices = sadp_mgr.discover_devices(timeout=10)
        if raw_devices and ptz_mgr:
            log.info(f"SADP found {len(raw_devices)} devices")
            ptz_cfg = ptz_mgr.config.load_ptz_config()
            for d in raw_devices:
                # 统一 MAC 格式为无分隔符小写
                mac = d.get("mac", "").replace(":", "").replace("-", "").lower()
                if mac and mac in ptz_cfg.get("devices", {}):
                    ptz_cfg["devices"][mac]["gateway"] = d.get("gateway", "")
                    ptz_cfg["devices"][mac]["subnet_mask"] = d.get("subnet_mask", "")
            ptz_mgr.config.save_ptz_config(ptz_cfg)
            log.info("Gateway info merged to device config")
        else:
            log.info("SADP no new devices found")
    except Exception as e:
        log.warning(f"Discovery SADP devices failed: {e}")
    
    _isapi_session = aiohttp.ClientSession()
    log.info("ISAPI session initialized")
    
    yield
    
    if _isapi_session:
        await _isapi_session.close()
    if _orchestrator:
        await _orchestrator.stop()
    log.info(f"{PROJECT_NAME} stopped.")

app = FastAPI(title=PROJECT_NAME, version=VERSION, lifespan=lifespan)


# StreamIn: WASM 播放器控制模块（WebSocket 代理已剥离到 src/stream_in/）
from src.stream_in.api.router import stream_in_router, set_app_state
from src.stream_in.api.router import COOP_COEP_PATHS

app.include_router(stream_in_router)


# COOP/COEP 中间件（WASM 播放器需要 SharedArrayBuffer，路径常量由 stream_in 模块提供）
@app.middleware("http")
async def add_coop_coep_headers(request: Request, call_next):
    response = await call_next(request)
    # 检查请求路径是否匹配 COOP/COEP 需要的路径
    url_str = str(request.url)
    for path in COOP_COEP_PATHS:
        if path in url_str:
            response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
            break
    return response

web_dir = get_web_dir()
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")

app.include_router(api_router)
app.include_router(health_router)
# app.include_router(calibrate_router)  # v7.12: 模块已删除
# app.include_router(stack_router)      # v7.12: 模块已删除

# ISAPI Proxy（动态获取设备IP，从 ptz_controller 读取）
@app.api_route("/ISAPI/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def isapi_proxy(request: Request, path: str):
    global _isapi_session

    # 从 ptz_controller 读取当前连接的设备
    ptz_mgr = getattr(app.state, 'ptz_controller', None)
    if not ptz_mgr:
        return Response(content=b"PTZ controller not initialized", status_code=503)
    
    device = ptz_mgr.get_connected_device()
    if not device:
        return Response(content=b"No device connected", status_code=503)
    camera_ip = device.get("ip", "")
    camera_port = device.get("port", 80)
    if not camera_ip:
        return Response(content=b"No device IP", status_code=503)
    
    target_url = f"http://{camera_ip}:{camera_port}/ISAPI/{path}"
    query_string = str(request.query_params)
    if query_string:
        target_url += f"?{query_string}"

    # Forward all headers including cookies and deviceIdentify
    headers = {}
    for k, v in request.headers.items():
        if k.lower() not in ["host", "content-length", "transfer-encoding"]:
            headers[k] = v

    # Forward cookies explicitly
    cookie_header = request.headers.get("cookie", "")
    if cookie_header:
        headers["cookie"] = cookie_header

    # Add sessionTag if device has one
    device = None
    for d in app.state.device_set if hasattr(app.state, 'device_set') else []:
        if d.szIP == camera_ip:
            device = d
            break
    if device and hasattr(device, 'sessionTag') and device.sessionTag:
        headers['sessionTag'] = device.sessionTag
    try:
        body = await request.body()
        # Rewrite sessionLogin response to disable sessionTag requirement
        if 'sessionLogin' in path and request.method == 'POST':
            async with _isapi_session.request(
                method=request.method, url=target_url, headers=headers,
                data=body, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp_body = await resp.read()
                # Fix sessionTag bug
                if 'isNeedSessionTag>true' in resp_body.decode('utf-8', errors='ignore'):
                    resp_body = resp_body.decode('utf-8').replace('isNeedSessionTag>true', 'isNeedSessionTag>false').encode()
                    log.info("Fixed sessionLogin: isNeedSessionTag=false")
                return Response(content=resp_body, status_code=resp.status, headers=dict(resp.headers))
        else:
            async with _isapi_session.request(
                method=request.method, url=target_url, headers=headers,
                data=body, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp_body = await resp.read()
                return Response(content=resp_body, status_code=resp.status, headers=dict(resp.headers))
    except Exception as e:
        log.error(f"ISAPI proxy error: {e}")
        return Response(content=f"Proxy error: {e}".encode(), status_code=502)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        log.error(f"Template error: {e}")
        index_html = get_index_html()
        if index_html.exists():
            return HTMLResponse(content=index_html.read_text(encoding="utf-8"))
        return HTMLResponse(content=f"<h1>{PROJECT_NAME}</h1><p>Web UI not found</p>")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=PROJECT_NAME)
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    print(f"Starting on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")









