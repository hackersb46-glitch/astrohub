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
    
    set_managers(
        ptz_manager=_orchestrator.get_module("ptz"),
        device_manager=_orchestrator.get_module("device"),
        stream_manager=_orchestrator.get_module("stream"),
        calibration_manager=_orchestrator.get_module("calibration")
    )
    log.info("Managers registered")
    
    _isapi_session = aiohttp.ClientSession()
    log.info("ISAPI session initialized")
    
    yield
    
    if _isapi_session:
        await _isapi_session.close()
    if _orchestrator:
        await _orchestrator.stop()
    log.info(f"{PROJECT_NAME} stopped.")

app = FastAPI(title=PROJECT_NAME, version=VERSION, lifespan=lifespan)

# Handle SDK WebSocket on ANY path (catches both /ws and /?version=...)
# SDK may send: ws://proxy/ws?token=xxx or ws://proxy/?version=...&token=xxx
from fastapi import WebSocket, WebSocketDisconnect
from starlette.routing import Route, WebSocketRoute
from starlette.responses import JSONResponse

async def ws_handler(websocket: WebSocket):
    """Handle SDK WebSocket - any path with token query param."""
    token = websocket.query_params.get("token", "")
    path = websocket.url.path
    log.info(f"WS handler: path={path}, token={'yes' if token else 'no'}")
    
    if not token:
        # No token - health check
        await websocket.accept()
        await websocket.close(code=1000)
        return
    
    # Has token - SDK video streaming
    version = websocket.query_params.get("version", "0.1")
    
    # Get cookies
    client_headers = dict(websocket.headers)
    ws_cookie = client_headers.get("cookie", "")
    
    camera_ip = "192.168.5.72"
    camera_ws_port = 7681
    channel = "101"
    
    for cookie in ws_cookie.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("webVideoCtrlProxyWs="):
            target = cookie.split("=")[1]
            parts = target.split(":")
            if len(parts) == 2:
                camera_ip = parts[0]
                camera_ws_port = int(parts[1])
    
    # Build camera WebSocket URL
    camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/{channel}?version={version}&cipherSuites=0&token={token}"
    
    # Get WebSession cookie
    ws_session_cookie = ""
    for c in ws_cookie.split(";"):
        c = c.strip()
        if c.startswith("WebSession"):
            ws_session_cookie = c
            break
    
    ws_auth_headers = {"Cookie": ws_session_cookie} if ws_session_cookie else {}
    log.info(f"WS handler: connecting to {camera_ws_url}, cookie={ws_session_cookie[:30] if ws_session_cookie else 'NONE'}")
    
    try:
        await websocket.accept()
    except Exception as e:
        log.error(f"WS handler: accept failed: {e}")
        return
    
    import websockets
    import websockets.exceptions
    
    try:
        async with websockets.connect(camera_ws_url, additional_headers=ws_auth_headers) as cam_ws:
            log.info("WS handler: connected to camera")
            
            async def browser_to_camera():
                try:
                    async for msg in websocket.iter_text():
                        await cam_ws.send(msg)
                except: pass
            
            async def camera_to_browser():
                try:
                    async for msg in cam_ws:
                        await websocket.send_text(msg)
                except: pass
            
            await asyncio.gather(browser_to_camera(), camera_to_browser())
    except Exception as e:
        log.error(f"WS handler: failed: {e}")
    
    log.info("WS handler: closed")

# Add WebSocket route handling
app.add_websocket_route("/ws", ws_handler)
app.add_websocket_route("/", ws_handler)
app.add_websocket_route("/{path:path}", ws_handler)

web_dir = get_web_dir()
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")

app.include_router(api_router)
app.include_router(health_router)

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
        log.info(f"ISAPI proxy: forwarding cookie header: {cookie_header[:80]}")
    else:
        log.warning(f"ISAPI proxy: NO cookie header for {path}")
    
    # For capabilities requests, add default auth if no cookie
    # WASM SDK may not send auth cookie for initial capability checks
    if 'capabilities' in path and not cookie_header:
        # Use basic auth as fallback for capability requests
        headers['Authorization'] = 'Basic ' + 'YWRtaW46'  # admin: (empty password base64)
        log.info(f"ISAPI capabilities: added default auth")
    
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
        # AND get szAuth from token API
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
                
                # Create response and set cookie properly
                response = Response(content=resp_body, status_code=resp.status)
                
                # Forward Set-Cookie header properly
                set_cookie = resp.headers.get('Set-Cookie')
                web_session_value = None
                if set_cookie:
                    # Parse WebSession cookie
                    import re
                    match = re.search(r'WebSession_15edb5a7ff=([^;]+)', set_cookie)
                    if match:
                        web_session_value = match.group(1)
                        # Set cookie with correct path
                        response.set_cookie('WebSession_15edb5a7ff', web_session_value, path='/', httponly=False)
                        log.info(f"sessionLogin: Set WebSession_15edb5a7ff cookie (path=/)")
                
                # If login successful (status 200), get szAuth from token API
                if resp.status == 200 and 'OK' in resp_body.decode('utf-8', errors='ignore') and web_session_value:
                    try:
                        token_url = f"http://{camera_ip}:{camera_port}/ISAPI/Security/token?format=json"
                        token_headers = {'Cookie': f'WebSession_15edb5a7ff={web_session_value}'}
                        async with _isapi_session.get(token_url, headers=token_headers) as token_resp:
                            token_body = await token_resp.text()
                            log.info(f"Token API response: {token_body[:100]}")
                            # Add szAuth to response header for SDK to use
                            import json
                            try:
                                token_data = json.loads(token_body)
                                if 'Token' in token_data and 'value' in token_data['Token']:
                                    sz_auth = token_data['Token']['value']
                                    response.headers['X-SZAuth'] = sz_auth
                                    log.info(f"sessionLogin: Added X-SZAuth header: {sz_auth}")
                            except:
                                pass
                    except Exception as e:
                        log.error(f"Failed to get token: {e}")
                
                return response
        # Inject WebSocket support for System/capabilities - return fixed response
        elif 'System/capabilities' in path:
            # Return a fixed capabilities XML with WebSocket support
            # This ensures SDK detects WebSocket capability correctly
            capabilities_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<DeviceCap version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
    <NetworkCap>
        <isSupportWebsocket>true</isSupportWebsocket>
    </NetworkCap>
    <RacmCap>
        <isSupportMainAndSubRecord>true</isSupportMainAndSubRecord>
    </RacmCap>
</DeviceCap>''' 
            log.info("ISAPI System/capabilities: returned fixed XML with WebSocket support")
            return Response(content=capabilities_xml.encode('utf-8'), status_code=200, media_type="application/xml")
        else:
            # Forward all other ISAPI requests with cookies
            # Get WebSession cookie from browser request
            log.info(f"ISAPI proxy: handling {path}")
            browser_cookies = request.cookies.get('WebSession_15edb5a7ff') or request.cookies.get('WebSession')
            log.info(f"ISAPI proxy: browser_cookies = {browser_cookies[:40] if browser_cookies else 'NONE'}")
            if browser_cookies:
                headers['Cookie'] = f'WebSession_15edb5a7ff={browser_cookies}'
                log.info(f"ISAPI proxy: forwarding WebSession cookie for {path}")
            else:
                log.warning(f"ISAPI proxy: NO WebSession cookie for {path}")
            async with _isapi_session.request(
                method=request.method, url=target_url, headers=headers,
                data=body, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                resp_body = await resp.read()
                # Forward all headers including Set-Cookie
                resp_headers = {}
                for k, v in resp.headers.items():
                    # Skip hop-by-hop headers
                    if k.lower() not in ['transfer-encoding', 'connection', 'keep-alive']:
                        resp_headers[k] = v
                return Response(content=resp_body, status_code=resp.status, headers=resp_headers)
    except Exception as e:
        log.error(f"ISAPI proxy error: {e}")
        return Response(content=f"Proxy error: {e}".encode(), status_code=502)

# WebSocket proxy - handle SDK's actual URL format
# SDK sends: ws://proxy/ws?version=0.1&cipherSuites=0&token=xxx
# Note: SDK may also send ws://proxy/?version=... so we handle both
@app.websocket("/ws")
async def ws_sdk_proxy(websocket: WebSocket):
    """Handle SDK WebSocket connection with query params."""
    # Check if this is SDK WebSocket request (has token in query params)
    token = websocket.query_params.get("token", "")
    
    log.info(f"WS SDK proxy: query_params={dict(websocket.query_params)}")
    
    # If no token, it's internal health check - accept but close
    if not token:
        await websocket.accept()
        await websocket.close(code=1000, reason="No token - health check")
        return
    
    # Get token from query params
    token = websocket.query_params.get("token", "")
    version = websocket.query_params.get("version", "0.1")
    
    # Get cookies for camera IP and port
    client_headers = dict(websocket.headers)
    ws_cookie = client_headers.get("cookie", "")
    
    camera_ip = "192.168.5.72"
    camera_ws_port = 7681
    channel = "101"  # Default channel 1, stream 1
    
    for cookie in ws_cookie.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("webVideoCtrlProxyWs="):
            target = cookie.split("=")[1]
            parts = target.split(":")
            if len(parts) == 2:
                camera_ip = parts[0]
                camera_ws_port = int(parts[1])
        elif cookie.startswith("webVideoCtrlProxyWsChannel="):
            channel = cookie.split("=")[1]
    
    # Build camera WebSocket URL
    camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/{channel}?version={version}&cipherSuites=0&token={token}"
    log.info(f"WS SDK proxy: connecting to {camera_ws_url}")
    
    # Get WebSession cookie for auth
    ws_session_cookie = ""
    for c in ws_cookie.split(";"):
        c = c.strip()
        if c.startswith("WebSession"):
            ws_session_cookie = c
            break
    
    ws_auth_headers = {"Cookie": ws_session_cookie} if ws_session_cookie else {}
    log.info(f"WS SDK proxy: token={token}, channel={channel}, cookie={ws_session_cookie[:50] if ws_session_cookie else 'NONE'}")
    
    try:
        await websocket.accept()
    except Exception as e:
        log.error(f"WS SDK proxy: accept failed: {e}")
        return
    
    import websockets
    import websockets.exceptions
    
    try:
        async with websockets.connect(camera_ws_url, additional_headers=ws_auth_headers) as cam_ws:
            log.info(f"WS SDK proxy: connected to camera")
            
            async def browser_to_camera():
                try:
                    async for msg in websocket.iter_text():
                        await cam_ws.send(msg)
                except websockets.exceptions.ConnectionClosed:
                    pass
                except WebSocketDisconnect:
                    pass
            
            async def camera_to_browser():
                try:
                    async for msg in cam_ws:
                        await websocket.send_text(msg)
                except websockets.exceptions.ConnectionClosed:
                    pass
            
            await asyncio.gather(browser_to_camera(), camera_to_browser())
    except websockets.exceptions.InvalidStatus as e:
        log.error(f"WS SDK proxy: camera rejected: {e}")
    except Exception as e:
        log.error(f"WS SDK proxy: failed: {e}")
    
    log.info("WS SDK proxy: closed")

# WebSocket proxy for channel-based URL format
# Route: /{channel}/webSocketVideoCtrlProxy
@app.websocket("/{channel:path}/webSocketVideoCtrlProxy")
async def websocket_proxy_channel(websocket: WebSocket, channel: str):
    # Get cookies from client headers
    client_headers = dict(websocket.headers)
    ws_cookie = client_headers.get("cookie", "")
    log.info(f"WS proxy: channel={channel}, cookies={ws_cookie[:80]}...")
    
    # SDK sets cookies:
    # - webVideoCtrlProxyWs = ip:port (for ws://)
    # - webVideoCtrlProxyWsChannel = channel number
    # But SDK also passes channel in URL path: /{channel}/webSocketVideoCtrlProxy
    # Use URL channel as primary, Cookie channel as fallback
    
    ws_target = None
    ws_channel = channel  # Use URL path channel (e.g. "101" for channel 1 stream 1)
    
    for cookie in ws_cookie.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("webVideoCtrlProxyWs="):
            ws_target = cookie.split("=")[1]
        elif cookie.startswith("webVideoCtrlProxyWss="):
            ws_target = cookie.split("=")[1]
        # Cookie channel is fallback, prefer URL path channel
    
    if ws_target:
        camera_ip, camera_ws_port = ws_target.split(":")
        camera_ws_port = int(camera_ws_port)
    else:
        device_identify = websocket.query_params.get("deviceIdentify", "192.168.5.72:80")
        camera_ip = device_identify.split(":")[0] if ":" in device_identify else device_identify
        camera_ws_port = 7681
    
    # Build WebSocket URL to camera
    # URL format: ws://camera_ip:camera_ws_port/{channel}
    ws_query = str(websocket.query_params)
    if ws_query:
        camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/{ws_channel}?{ws_query}"
    else:
        camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/{ws_channel}"
    
    # Forward WebSession auth cookie to camera for WebSocket auth
    # The browser cookie contains WebSession_15edb5a7ff from ISAPI login
    # Parse out just the WebSession cookie for camera auth
    ws_session_cookie = ""
    for c in ws_cookie.split(";"):
        c = c.strip()
        if c.startswith("WebSession"):
            ws_session_cookie = c
            break
    
    # If we have a WebSession cookie, use it for camera auth
    if ws_session_cookie:
        ws_auth_headers = {"Cookie": ws_session_cookie}
        log.info(f"WS proxy: using auth cookie: {ws_session_cookie[:50]}...")
    else:
        ws_auth_headers = {}
        log.info("WS proxy: NO WebSession cookie found, connecting without auth")
    
    log.info(f"WS proxy: channel={ws_channel}, target={camera_ws_url}, cookie={'yes' if ws_cookie else 'no'}")
    
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
                    async for msg in websocket.iter_text():
                        await cam_ws.send(msg)
                except websockets.exceptions.ConnectionClosed:
                    pass
                except WebSocketDisconnect:
                    pass
            
            async def camera_to_browser():
                try:
                    async for msg in cam_ws:
                        await websocket.send_text(msg)
                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception:
                    pass
            
            await asyncio.gather(browser_to_camera(), camera_to_browser())
    except websockets.exceptions.InvalidStatus as e:
        log.error(f"WS proxy: camera rejected connection: {e}")
    except Exception as e:
        log.error(f"WS proxy: connection failed: {e}")
    
    log.info("WS proxy: connection closed")

# SDK capabilities - WASM SDK queries this to determine streaming support
@app.get("/SDK/capabilities")
async def sdk_capabilities(request: Request):
    """Return SDK capabilities indicating WebSocket streaming support.
    
    WASM SDK calls this to check:
    - isSupportHttpPlay
    - isSupportHttpPlayback
    - isSupportHttpsPlay
    - ipChanBase
    
    Returns XML response with streaming capabilities.
    """
    from fastapi.responses import Response
    
    # Get device IP from cookie or default
    client_headers = dict(request.headers)
    ws_cookie = client_headers.get("cookie", "")
    
    device_ip = "192.168.5.72"  # default
    for cookie in ws_cookie.split(";"):
        cookie = cookie.strip()
        if cookie.startswith("webVideoCtrlProxyWs="):
            target = cookie.split("=")[1]
            device_ip = target.split(":")[0]
            break
    
    log.info(f"SDK/capabilities: device={device_ip}")
    
    # Return capabilities XML - indicate support for WebSocket streaming
    capabilities_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<SDKCap>
    <isSupportHttpPlay>true</isSupportHttpPlay>
    <isSupportHttpPlayback>true</isSupportHttpPlayback>
    <isSupportHttpsPlay>true</isSupportHttpsPlay>
    <isSupportHttpsPlayback>true</isSupportHttpsPlayback>
    <isSupportHttpTransCodePlayback>true</isSupportHttpTransCodePlayback>
    <isSupportHttpsTransCodePlayback>true</isSupportHttpsTransCodePlayback>
    <ipChanBase>1</ipChanBase>
</SDKCap>''' 
    
    return Response(content=capabilities_xml, media_type="application/xml")

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









