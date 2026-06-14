#!/usr/bin/env python
"""
Add WebSocket proxy to main.py
"""
import sys
from pathlib import Path

content = '''#!/usr/bin/env python
"""M12 Integration - With Jinja2, Managers, and WebSocket proxy"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import asyncio
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request, WebSocket
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
    
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ["host", "content-length", "transfer-encoding", "connection"]}
    
    try:
        body = await request.body()
        async with _isapi_session.request(
            method=request.method, url=target_url, headers=headers,
            data=body, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp_body = await resp.read()
            return Response(content=resp_body, status_code=resp.status, headers=dict(resp.headers))
    except Exception as e:
        log.error(f"ISAPI proxy error: {e}")
        return Response(content=f"Proxy error: {e}".encode(), status_code=502)

# SDK Proxy
@app.api_route("/SDK/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def sdk_proxy(request: Request, path: str):
    global _isapi_session
    camera_ip = "192.168.5.72"
    camera_port = 80
    target_url = f"http://{camera_ip}:{camera_port}/SDK/{path}"
    query_string = str(request.query_params)
    if query_string:
        target_url += f"?{query_string}"
    
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ["host", "content-length", "transfer-encoding", "connection"]}
    
    try:
        body = await request.body()
        async with _isapi_session.request(
            method=request.method, url=target_url, headers=headers,
            data=body, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp_body = await resp.read()
            return Response(content=resp_body, status_code=resp.status, headers=dict(resp.headers))
    except Exception as e:
        log.error(f"SDK proxy error: {e}")
        return Response(content=f"Proxy error: {e}".encode(), status_code=502)

# WebSocket proxy - forward to camera WebSocket port
@app.websocket("/ws")
async def websocket_proxy(websocket: WebSocket):
    camera_ws_ip = "192.168.5.72"
    camera_ws_port = 7681  # Camera WebSocket port
    
    await websocket.accept()
    log.info(f"WebSocket connected, forwarding to {camera_ws_ip}:{camera_ws_port}")
    
    try:
        import websockets
        async with websockets.connect(f"ws://{camera_ws_ip}:{camera_ws_port}") as camera_ws:
            async def client_to_camera():
                while True:
                    data = await websocket.receive_text()
                    await camera_ws.send(data)
            
            async def camera_to_client():
                while True:
                    data = await camera_ws.recv()
                    await websocket.send_text(data)
            
            await asyncio.gather(client_to_camera(), camera_to_client())
    except Exception as e:
        log.error(f"WebSocket proxy error: {e}")
    finally:
        await websocket.close()

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
'''

target = Path("D:/py_app/astro_hub/src/main/main.py")
target.write_text(content, encoding="utf-8")
print(f"Rewrote {target}")