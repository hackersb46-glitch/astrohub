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
from fastapi.responses import HTMLResponse, Response
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
    from src.core.ptz_manager import PTZManager
    from src.core.device_manager import DeviceManager
    from src.core.stream_manager import StreamManager
    from src.core.calibration_manager import CalibrationManager
    
    ptz_mgr = PTZManager()
    device_mgr = DeviceManager()
    stream_mgr = StreamManager()
    calib_mgr = CalibrationManager()
    
    set_managers(
        ptz_manager=ptz_mgr,
        device_manager=device_mgr,
        stream_manager=stream_mgr,
        calibration_manager=calib_mgr
    )
    log.info("Managers registered")
    
    # v6.01: 启动时执行一次 SADP 发现，合并网关信息到 ptz_config
    try:
        log.info("启动时 SADP 设备发现...")
        from src.core.sadp_discovery import SADPManager
        sadp_mgr = SADPManager()
        raw_devices = sadp_mgr.discover_devices(timeout=10)
        if raw_devices and ptz_mgr:
            log.info(f"SADP 发现 {len(raw_devices)} 台设备")
            ptz_cfg = ptz_mgr.config.load_ptz_config()
            for d in raw_devices:
                # 统一 MAC 格式为无分隔符小写
                mac = d.get("mac", "").replace(":", "").replace("-", "").lower()
                if mac and mac in ptz_cfg.get("devices", {}):
                    ptz_cfg["devices"][mac]["gateway"] = d.get("gateway", "")
                    ptz_cfg["devices"][mac]["subnet_mask"] = d.get("subnet_mask", "")
            ptz_mgr.config.save_ptz_config(ptz_cfg)
            log.info("网关信息已合并到设备配置")
        else:
            log.info("SADP 未发现新设备")
    except Exception as e:
        log.warning(f"启动时 SADP 发现失败: {e}")
    
    _isapi_session = aiohttp.ClientSession()
    log.info("ISAPI session initialized")
    
    yield
    
    if _isapi_session:
        await _isapi_session.close()
    if _orchestrator:
        await _orchestrator.stop()
    log.info(f"{PROJECT_NAME} stopped.")

app = FastAPI(title=PROJECT_NAME, version=VERSION, lifespan=lifespan)

web_dir = get_web_dir()
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")

app.include_router(api_router)
app.include_router(health_router)
# app.include_router(calibrate_router)  # v7.12: 模块已删除
# app.include_router(stack_router)      # v7.12: 模块已删除

# ISAPI Proxy
@app.api_route("/ISAPI/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def isapi_proxy(request: Request, path: str):
    global _isapi_session
    camera_ip = "192.168.5.72"
    camera_port = 80
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

# Handle jsPlugin internal WebSocket - proxy to camera (v6.41 fix)
# WASM SDK uses this path for streaming control
@app.websocket("/ws")
async def ws_internal(websocket: WebSocket):
    """WebSocket proxy for WASM SDK internal control channel."""
    log.info(f"WS /ws: ENTER, path={websocket.url.path}, qs={str(websocket.query_params)[:80]}")
    
    # Get cookies to find target camera
    ws_cookie = websocket.headers.get("cookie", "")
    camera_ip = "192.168.5.72"
    camera_ws_port = 7681
    
    for ck in ws_cookie.split(";"):
        ck = ck.strip()
        if ck.startswith("webVideoCtrlProxyWs="):
            target = ck.split("=")[1]
            parts = target.split(":")
            if len(parts) == 2:
                camera_ip = parts[0]
                camera_ws_port = int(parts[1])
    
    ws_query = str(websocket.query_params)
    camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/?{ws_query}" if ws_query else f"ws://{camera_ip}:{camera_ws_port}/"
    
    log.info(f"WS /ws: proxying to {camera_ws_url[:60]}...")
    
    try:
        await websocket.accept()
    except Exception as e:
        log.error(f"WS /ws: accept failed: {e}")
        return
    
    import websockets
    import websockets.exceptions
    
    try:
        async with websockets.connect(camera_ws_url) as cam_ws:
            log.info("WS /ws: connected to camera")
            
            async def browser_to_camera():
                try:
                    while True:
                        data = await websocket.receive()
                        if data["type"] == "websocket.receive":
                            if "text" in data:
                                await cam_ws.send(data["text"])
                            elif "bytes" in data:
                                await cam_ws.send(data["bytes"])
                        elif data["type"] == "websocket.disconnect":
                            break
                except (websockets.exceptions.ConnectionClosed, WebSocketDisconnect):
                    pass
            
            async def camera_to_browser():
                try:
                    async for msg in cam_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except (websockets.exceptions.ConnectionClosed, WebSocketDisconnect):
                    pass
            
            await asyncio.gather(browser_to_camera(), camera_to_browser())
    except websockets.exceptions.InvalidStatus as e:
        log.error(f"WS /ws: camera rejected: {e}")
    except Exception as e:
        log.error(f"WS /ws: proxy failed: {e}")
    
    log.info("WS /ws: closed")

# WebSocket proxy for SDK path / (used when SDK sends /?version=... format)
@app.websocket("/")
async def ws_proxy_root(websocket: WebSocket):
    """WebSocket proxy for root path - SDK may send ws://localhost:8000/?version=..."""
    log.info(f"WS proxy root: ENTER, path={websocket.url.path}, qs={str(websocket.query_params)[:80]}")
    
    # Get cookies
    ws_cookie = websocket.headers.get("cookie", "")
    camera_ip = "192.168.5.72"
    camera_ws_port = 7681
    channel = "101"
    
    for ck in ws_cookie.split(";"):
        ck = ck.strip()
        if ck.startswith("webVideoCtrlProxyWs="):
            target = ck.split("=")[1]
            parts = target.split(":")
            if len(parts) == 2:
                camera_ip = parts[0]
                camera_ws_port = int(parts[1])
        elif ck.startswith("webVideoCtrlProxyWsChannel="):
            channel = ck.split("=")[1]
    
    ws_query = str(websocket.query_params)
    camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/{channel}?{ws_query}" if ws_query else f"ws://{camera_ip}:{camera_ws_port}/{channel}"
    
    # Get fresh token
    import requests as req_lib
    from requests.auth import HTTPDigestAuth
    try:
        fresh_token_resp = req_lib.get(f'http://{camera_ip}:80/ISAPI/Security/token?format=json',
                                        auth=HTTPDigestAuth('admin','Nftw1357'), timeout=10)
        if fresh_token_resp.status_code == 200:
            import json
            fresh_token = json.loads(fresh_token_resp.text).get('Token',{}).get('value','')
            log.info(f"WS proxy root: fresh token={fresh_token[:10]}...")
            if 'token=' in camera_ws_url:
                import re
                camera_ws_url = re.sub(r'token=[^&]+', f'token={fresh_token}', camera_ws_url)
            else:
                camera_ws_url += f'&token={fresh_token}'
        else:
            log.warning(f"WS proxy root: token fetch failed: {fresh_token_resp.status_code}")
    except Exception as e:
        log.warning(f"WS proxy root: token fetch error: {e}")
    
    log.info(f"WS proxy root: target={camera_ws_url[:80]}...")
    
    try:
        await websocket.accept()
    except Exception as e:
        log.error(f"WS proxy root: accept failed: {e}")
        return
    
    import websockets
    import websockets.exceptions
    
    try:
        async with websockets.connect(camera_ws_url) as cam_ws:
            log.info("WS proxy root: connected to camera")
            
            async def browser_to_camera():
                try:
                    while True:
                        data = await websocket.receive()
                        if data["type"] == "websocket.receive":
                            if "text" in data:
                                await cam_ws.send(data["text"])
                            elif "bytes" in data:
                                await cam_ws.send(data["bytes"])
                        elif data["type"] == "websocket.disconnect":
                            break
                except (websockets.exceptions.ConnectionClosed, WebSocketDisconnect):
                    pass
            
            async def camera_to_browser():
                try:
                    async for msg in cam_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except (websockets.exceptions.ConnectionClosed, WebSocketDisconnect):
                    pass
            
            await asyncio.gather(browser_to_camera(), camera_to_browser())
    except websockets.exceptions.InvalidStatus as e:
        log.error(f"WS proxy root: camera rejected: {e}")
    except Exception as e:
        log.error(f"WS proxy root: failed: {e}")
    
    log.info("WS proxy root: closed")

# WebSocket proxy - SDK uses /webSocketVideoCtrlProxy path
@app.websocket("/{channel}/webSocketVideoCtrlProxy")
async def websocket_proxy(websocket: WebSocket, channel: str):

    # Get cookies from client headers
    client_headers = dict(websocket.headers)
    ws_cookie = client_headers.get("cookie", "")
    log.info(f"WS proxy: channel={channel}, cookies={ws_cookie[:80]}...")
    
    # SDK sets cookies:
    # - webVideoCtrlProxyWs = ip:port (for ws://)
    # - webVideoCtrlProxyWsChannel = channel number
    
    ws_target = None
    ws_channel = "101"
    
    for cookie in ws_cookie.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("webVideoCtrlProxyWs="):
            ws_target = cookie.split("=")[1]
        elif cookie.startswith("webVideoCtrlProxyWss="):
            ws_target = cookie.split("=")[1]
        elif cookie.startswith("webVideoCtrlProxyWsChannel="):
            ws_channel = cookie.split("=")[1]
    
    if ws_target:
        camera_ip, camera_ws_port = ws_target.split(":")
        camera_ws_port = int(camera_ws_port)
    else:
        device_identify = websocket.query_params.get("deviceIdentify", "192.168.5.72:80")
        camera_ip = device_identify.split(":")[0] if ":" in device_identify else device_identify
        camera_ws_port = 7681
    
    channel = ws_channel
    ws_query = str(websocket.query_params)
    if ws_query:
        camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/{channel}?{ws_query}"
    else:
        camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/{channel}"
    
    # Forward WebSession auth cookie to camera for WebSocket auth
    ws_auth_headers = {"Cookie": ws_cookie} if ws_cookie else {}
    
    # Get fresh token for WebSocket authentication
    # SDK's szAuth may not work for WS; need ISAPI /Security/token
    import requests as req_lib
    from requests.auth import HTTPDigestAuth
    try:
        fresh_token_resp = req_lib.get(f'http://{camera_ip}:80/ISAPI/Security/token?format=json',
                                        auth=HTTPDigestAuth('admin','Nftw1357'), timeout=10)
        if fresh_token_resp.status_code == 200:
            import json
            fresh_token = json.loads(fresh_token_resp.text).get('Token',{}).get('value','')
            log.info(f"WS proxy: fresh token={fresh_token[:10]}...")
            # Replace token in URL with fresh token
            if 'token=' in camera_ws_url:
                # Replace existing token
                import re
                camera_ws_url = re.sub(r'token=[^&]+', f'token={fresh_token}', camera_ws_url)
            else:
                # Add token
                camera_ws_url += f'&token={fresh_token}'
        else:
            log.warning(f"WS proxy: token fetch failed: {fresh_token_resp.status_code}")
    except Exception as e:
        log.warning(f"WS proxy: token fetch error: {e}")
    
    log.info(f"WS proxy: final target={camera_ws_url[:80]}...")
    
    try:
        await websocket.accept()
    except Exception as e:
        log.error(f"WS proxy: accept failed: {e}")
        return
    
    import websockets
    import websockets.exceptions
    
    try:
        async with websockets.connect(camera_ws_url, additional_headers=ws_auth_headers) as cam_ws:
            log.info(f"WS proxy: connected to camera")
            
            async def browser_to_camera():
                try:
                    while True:
                        data = await websocket.receive()
                        if data["type"] == "websocket.receive":
                            if "text" in data:
                                await cam_ws.send(data["text"])
                            elif "bytes" in data:
                                await cam_ws.send(data["bytes"])
                        elif data["type"] == "websocket.disconnect":
                            break
                except (websockets.exceptions.ConnectionClosed, WebSocketDisconnect):
                    pass
            
            async def camera_to_browser():
                try:
                    async for msg in cam_ws:
                        if isinstance(msg, str):
                            await websocket.send_text(msg)
                        else:
                            await websocket.send_bytes(msg)
                except (websockets.exceptions.ConnectionClosed, WebSocketDisconnect):
                    pass
            
            await asyncio.gather(browser_to_camera(), camera_to_browser())
    except websockets.exceptions.InvalidStatus as e:
        log.error(f"WS proxy: camera rejected connection: {e}")
    except Exception as e:
        log.error(f"WS proxy: connection failed: {e}")
    
    log.info("WS proxy: connection closed")

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









