#!/usr/bin/env python
"""
Add ISAPI proxy to main.py
"""
import sys
from pathlib import Path

content = '''#!/usr/bin/env python
"""M12 Integration - With Jinja2 and Managers"""

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
from fastapi import FastAPI, Request
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

# Configure Jinja2 templates
templates = Jinja2Templates(directory=str(get_web_dir()))

# Global orchestrator instance
_orchestrator = None

# ISAPI proxy session
_isapi_session = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _orchestrator, _isapi_session
    ensure_directories()
    log.info(f"{PROJECT_NAME} v{VERSION} starting...")
    
    # Initialize orchestrator and managers
    _orchestrator = Orchestrator()
    await _orchestrator.start()
    
    # Register managers with API router
    set_managers(
        ptz_manager=_orchestrator.get_module("ptz"),
        device_manager=_orchestrator.get_module("device"),
        stream_manager=_orchestrator.get_module("stream"),
        calibration_manager=_orchestrator.get_module("calibration")
    )
    log.info("Managers registered with API router")
    
    # Initialize ISAPI proxy session
    _isapi_session = aiohttp.ClientSession()
    log.info("ISAPI proxy session initialized")
    
    yield
    
    # Cleanup
    if _isapi_session:
        await _isapi_session.close()
    if _orchestrator:
        await _orchestrator.stop()
    log.info(f"{PROJECT_NAME} stopped.")

app = FastAPI(title=PROJECT_NAME, version=VERSION, lifespan=lifespan)

# Static files
web_dir = get_web_dir()
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir / "static")), name="static")

# API routers
app.include_router(api_router)
app.include_router(health_router)

# ISAPI Proxy - forward all /ISAPI/* requests to camera
@app.api_route("/ISAPI/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def isapi_proxy(request: Request, path: str):
    global _isapi_session
    
    # Target camera
    camera_ip = "192.168.5.72"
    camera_port = 80
    
    # Build target URL
    target_url = f"http://{camera_ip}:{camera_port}/ISAPI/{path}"
    
    # Get query parameters
    query_string = str(request.query_params)
    if query_string:
        target_url += f"?{query_string}"
    
    # Copy headers (excluding host)
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ["host", "content-length", "transfer-encoding", "connection"]:
            headers[key] = value
    
    # Add auth header if present in cookies
    # Note: ISAPI uses Digest auth, which is handled by the browser/SDK
    
    try:
        # Get request body
        body = await request.body()
        
        # Make request
        async with _isapi_session.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=body,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            # Read response body
            resp_body = await resp.read()
            
            # Return response
            return Response(
                content=resp_body,
                status_code=resp.status,
                headers=dict(resp.headers)
            )
    except Exception as e:
        log.error(f"ISAPI proxy error: {e}")
        return Response(
            content=f"Proxy error: {str(e)}".encode(),
            status_code=502
        )

# Home page
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