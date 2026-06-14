#!/usr/bin/env python
"""
AstroHub v2.0 - 统一入口

FastAPI + pywebview 桌面客户端 / 无头服务端。

功能:
- FastAPI app，挂载 src/web/index.html 静态文件 + SPA 回退
- 集成所有 core managers
- WebSocket 端点 /ws
- lifespan: 启动初始化 / 关闭清理
- pywebview 桌面模式 (1600x900, 标题 AstroHub)
- --headless 模式: 仅 uvicorn
- 系统托盘 (Windows pystray)
- 数据目录自动创建

Author: 雅痞张@南方天文
"""

from __future__ import annotations

# ================================================================ #
#  sys.path 补丁：使 src/ 下的 m1_ptz_astro 等模块可被顶级导入
# ================================================================ #
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import warnings
warnings.warn(
    "src/main.py is deprecated. Use 'src/main/main.py' for unified entry, "
    "or 'src/ptz/main.py' for PTZ module. "
    "Will be removed in a future version.",
    DeprecationWarning,
    stacklevel=2,
)

import argparse
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import httpx
from fastapi import FastAPI, Request, WebSocket, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from src.config import HOST, PORT, WINDOW_TITLE, WINDOW_WIDTH, WINDOW_HEIGHT, ensure_directories
from src.config_paths import DATA_DIR, HLS_DIR, CALIBRATION_DIR, get_web_dir, get_index_html
from src.api.router import api_router, health_router, set_managers
from src.core.ptz_manager import PTZManager
from src.core.device_manager import DeviceManager
from src.core.stream_manager import StreamManager
from src.core.calibration_manager import CalibrationManager
from src.core.auth import AuthManager
from src.core.ws_manager import WebSocketManager
from src.core.ascom_manager import ASCOMManager
from src.core.orchestrator import Orchestrator
from src.core.health_monitor import HealthMonitor
from src.database.core.db_manager import DatabaseManager, init_db
from src.logger import get_logger

log = get_logger("main")

async def lifespan(app: FastAPI):
    """应用生命周期：初始化所有管理器 → yield → 清理所有管理器。"""
    log.info("=== AstroHub 启动中 ===")

    _ensure_data_dirs()

    # 初始化所有管理器
    log.info("初始化 PTZManager ...")
    ptz_mgr = PTZManager()
    _managers["ptz_manager"] = ptz_mgr

    log.info("初始化 DeviceManager ...")
    device_mgr = DeviceManager()
    _managers["device_manager"] = device_mgr

    log.info("初始化 StreamManager ...")
    stream_mgr = StreamManager()
    _managers["stream_manager"] = stream_mgr

    log.info("初始化 CalibrationManager ...")
    calib_mgr = CalibrationManager()
    _managers["calibration_manager"] = calib_mgr

    log.info("初始化 AuthManager ...")
    auth_svc = AuthManager()
    _managers["auth_service"] = auth_svc

    log.info("初始化 WebSocketManager ...")
    ws_mgr = WebSocketManager()
    _managers["ws_manager"] = ws_mgr

    log.info("检测 ASCOM 平台...")
    ascom_platform = "windows"  # default
    try:
        import sys as _sys
        if _sys.platform == "linux":
            ascom_platform = "linux"  # Alpaca on Linux
        else:
            # On Windows, check if Alpaca server is available
            try:
                import requests  # noqa: F811
                resp = requests.get("http://localhost:5555/management/v1/apidevices", timeout=3)
                if resp.status_code == 200:
                    log.info("检测到 ASCOM Alpaca Server (localhost:5555)")
                    ascom_platform = "linux"  # Use Alpaca protocol
            except Exception:
                log.info("ASCOM Alpaca Server 未检测到，使用 Windows COM")
    except ImportError:
        pass

    log.info("初始化 ASCOMManager ...")
    ascom_mgr = ASCOMManager(platform=ascom_platform)
    _managers["ascom_manager"] = ascom_mgr

    log.info("初始化 DatabaseManager (M5)...")
    try:
        await init_db()
        db_mgr = DatabaseManager()
        _managers["db_manager"] = db_mgr
        log.info("DatabaseManager 初始化成功")
    except Exception as e:
        log.error(f"DatabaseManager 初始化失败: {e}")
        _managers["db_manager"] = None
        db_mgr = None

    log.info("初始化 HealthMonitor ...")
    health_mon = HealthMonitor()
    _managers["health_monitor"] = health_mon

    log.info("初始化 Orchestrator ...")
    orchestrator = Orchestrator()
    await orchestrator.start()
    _managers["orchestrator"] = orchestrator

    log.info("初始化 ASCOM Alpaca Server (端口 5555) ...")
    from src.core.alpaca_server import create_alpaca_server
    alpaca_server = create_alpaca_server("localhost", 5555, ptz_mgr)
    alpaca_thread = threading.Thread(target=alpaca_server.serve_forever, daemon=True)
    alpaca_thread.start()
    _managers["alpaca_server"] = alpaca_server
    log.info("ASCOM Alpaca Server 已启动: http://localhost:5555")
    log.info("  → Telescope (PTZ Pan/Tilt): 设备编号 0")
    log.info("  → Focuser (PTZ Zoom): 设备编号 0")
    log.info("  → FilterWheel (IRCUT 日夜切换): 设备编号 0")

    # 注入到路由模块
    set_managers(
        ptz_manager=ptz_mgr,
        device_manager=device_mgr,
        stream_manager=stream_mgr,
        calibration_manager=calib_mgr,
        auth_service=auth_svc,
        ws_manager=ws_mgr,
        ascom_manager=ascom_mgr,
        db_manager=db_mgr,
        health_monitor=health_mon,
        orchestrator=orchestrator,
    )

    log.info("=== AstroHub 所有管理器初始化完成 ===")

    yield

    # ---- 关闭阶段 ----
    log.info("=== AstroHub 关闭中 ===")

    # 停止 ASCOM Alpaca Server
    alpaca_srv = _managers.get("alpaca_server")
    if alpaca_srv:
        log.info("正在关闭 ASCOM Alpaca Server ...")
        alpaca_srv.shutdown()  # type: ignore[union-attr]
        log.info("ASCOM Alpaca Server 已关闭")

    # 停止 Orchestrator
    if isinstance(orchestrator, Orchestrator):
        await orchestrator.stop()
        log.info("Orchestrator 已停止")

    # 断开所有 ASCOM 设备
    if isinstance(ascom_mgr, ASCOMManager):
        ascom_mgr.disconnect_all()
        log.info("ASCOM 设备已全部断开")

    # Close db_manager
    if isinstance(db_mgr, DatabaseManager):
        await db_mgr.close()
        log.info("DatabaseManager 已关闭")

    _managers.clear()
    log.info("=== AstroHub 已安全关闭 ===")


# ================================================================ #
#  SPA 回退路径列表
# ================================================================ #

_SPA_FALLBACK_PATHS = {
    "/", "/dashboard", "/devices", "/console", "/observation", "/advanced", "/replay",
}


# ================================================================ #
#  创建 FastAPI App
# ================================================================ #

_WEB_DIR = get_web_dir()
_INDEX_HTML = get_index_html()



def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(
        title="AstroHub",
        description="统一天文设备控制平台",
        version="2.0",
        lifespan=lifespan,
    )

    # 挂载 HLS 静态文件目录
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/hls", StaticFiles(directory=str(HLS_DIR), html=True), name="hls")

    # 挂载 src/web 静态文件
    app.mount("/static", StaticFiles(directory=str(_WEB_DIR), html=True), name="static")

    # 挂载 API 路由
    app.include_router(api_router)
    app.include_router(health_router)

    # 根路径 -> index.html
    @app.get("/", response_class=HTMLResponse)
    async def serve_index(request: Request) -> HTMLResponse:
        return _templates.TemplateResponse("index.html", {"request": request})

    # SPA 回退 - 所有前端路由返回 index.html
# SPA 前端路由列表（非这些路径应返回 404）
    _SPA_ROUTES = frozenset({
        "/", "/dashboard", "/devices", "/console", "/observation", "/advanced", "/replay",
    })

    
    # ================================================================ #
    #  ISAPI Proxy for WASM SDK
    # ================================================================ #


    @app.api_route('/ISAPI/{path:path}', methods=['GET', 'POST', 'PUT', 'DELETE'])
    async def isapi_proxy(path: str, request: Request) -> Response:
        """Proxy ISAPI requests to Hikvision device for WASM SDK."""
        with open(r"str(Path(__file__).resolve().parent / "logs" / "isapi_debug.log")", "a", encoding="utf-8") as _f:
            _f.write(f"[ISAPI ENTRY] method={request.method} path={path}\n")
            _f.flush()
        ptz_mgr = _managers.get('ptz_manager')
        if not ptz_mgr:
            return Response(content='PTZManager not initialized', status_code=500)

        # Get device IP from deviceIdentify header (WASM SDK) or query params
        device_identify = request.headers.get("deviceidentify") or request.headers.get("deviceIdentify")
        device_ip = request.query_params.get("device_ip") or request.query_params.get("ip")
        if not device_ip and device_identify:
            device_ip = device_identify.split(":")[0]
            print(f"[ISAPI] Extracted device IP from deviceIdentify: {device_ip}")
        if not device_ip:
            devices = ptz_mgr.list_stored_devices()
            for dev in devices:
                if dev.get("ip"):
                    device_ip = dev["ip"]
                    break
        if not device_ip:
            return Response(content='No device IP specified', status_code=400)

        port = 80
        target_url = f'http://{device_ip}:{port}/ISAPI/{path}'
        if request.query_params:
            filtered_params = {k: v for k, v in request.query_params.items() if k not in ('device_ip', 'ip')}
            if filtered_params:
                target_url += '?' + '&'.join(f'{k}={v}' for k, v in filtered_params.items())

        print(f"[ISAPI] {request.method} {path} -> {target_url}", flush=True)
        print(f"[ISAPI] method={request.method}, path='{path}'", flush=True)
        
        # Build headers to forward - keep Cookie for session auth
        fwd_headers = {}
        for k, v in request.headers.items():
            lk = k.lower()
            if lk in ('host', 'content-length', 'transfer-encoding'):
                continue
            fwd_headers[k] = v
        
        # Read body for POST/PUT
        body = await request.body() if request.method in ('POST', 'PUT') else None

        print(f"[ISAPI] POST body check: path={path}, stripped={path.strip(chr(47))}, has_body={body is not None}")
        # FIX: Override isNeedSessionTag to false for sessionLogin
        # This device has a bug: sessionTag login succeeds but subsequent requests fail
        if request.method == 'POST' and body:
            _debug_body = body.decode('utf-8', errors='replace')[:200]
            with open(r"str(Path(__file__).resolve().parent / "logs" / "isapi_debug.log")", "a", encoding="utf-8") as _f:
                _f.write(f"[ISAPI POST] path={path} body={_debug_body}\n")
                _f.flush()
            if 'Security/sessionLogin' in path:
                if '<isNeedSessionTag>true</isNeedSessionTag>' in _debug_body:
                    _debug_body = _debug_body.replace('<isNeedSessionTag>true</isNeedSessionTag>', '<isNeedSessionTag>false</isNeedSessionTag>')
                    body = _debug_body.encode('utf-8')
                    with open(r"str(Path(__file__).resolve().parent / "logs" / "isapi_debug.log")", "a", encoding="utf-8") as _f:
                        _f.write("[ISAPI] Overrode isNeedSessionTag to false\n")
                        _f.flush()
                elif '<isNeedSessionTag>false</isNeedSessionTag>' in _debug_body:
                    print("[ISAPI] isNeedSessionTag already false", flush=True)
                else:
                    print("[ISAPI] WARNING: isNeedSessionTag tag not found in body", flush=True)
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                if request.method == 'GET':
                    resp = await client.get(target_url, headers=fwd_headers)
                elif request.method == 'POST':
                    resp = await client.post(target_url, content=body, headers=fwd_headers)
                elif request.method == 'PUT':
                    resp = await client.put(target_url, content=body, headers=fwd_headers)
                elif request.method == 'DELETE':
                    resp = await client.delete(target_url, headers=fwd_headers)
                else:
                    return Response(content='Method not allowed', status_code=405)

                # Forward Set-Cookie headers for session auth
                resp_headers = dict(resp.headers)
                return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
            except httpx.TimeoutException:
                return Response(content='Device timeout', status_code=504)
            except Exception as e:
                return Response(content=str(e), status_code=500)


    @app.get("/{full_path:path}", response_model=None)
    async def spa_fallback(full_path: str) -> FileResponse | HTMLResponse:
        # Skip API/HLS/静态文件路径不回退
        if full_path.startswith(("api/", "hls/", "static/")) or full_path in ("docs", "redoc", "openapi.json"):
            return HTMLResponse(status_code=404, content="Not Found")

        # 如果路径包含文件扩展名（如 .js, .css, .png），不是 SPA 路由，返回 404
        import os
        _, ext = os.path.splitext(full_path)
        if ext and full_path not in _SPA_ROUTES:
            return HTMLResponse(status_code=404, content="Not Found")

        # SPA 前端路由回退
        return FileResponse(_INDEX_HTML)

    # WebSocket 端点
    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        client_id = id(ws)
        ws_mgr: WebSocketManager = _managers.get("ws_manager")  # type: ignore[assignment]
        if ws_mgr:
            # 注册默认频道
            await ws_mgr.connect(ws, str(client_id), channels=["system", "health"])
            try:
                while True:
                    # 接收消息保持连接活跃
                    data = await ws.receive_json()
                    # 简单回显确认
                    await ws_mgr.send_to(str(client_id), {
                        "type": "ack",
                        "data": data,
                    })
            except Exception:
                pass
            finally:
                await ws_mgr.disconnect(str(client_id))
        else:
            # ws_mgr 未初始化，保持最基础的回显
            try:
                while True:
                    data = await ws.receive_json()
                    await ws.send_json({"type": "ack", "data": data})
            except Exception:
                pass

    return app


# ================================================================ #
#  Pywebview 桌面窗口
# ================================================================ #

def _run_desktop_window(url: str, stop_event: threading.Event) -> None:
    """在独立线程中启动 pywebview 窗口。"""
    try:
        import webview
        log.info("启动桌面窗口: %s (%dx%d)", url, WINDOW_WIDTH, WINDOW_HEIGHT)
        webview.create_window(WINDOW_TITLE, url, width=WINDOW_WIDTH, height=WINDOW_HEIGHT)
        webview.start()
    except ImportError:
        log.warning("pywebview 未安装，无法启动桌面窗口")
    finally:
        stop_event.set()


# ================================================================ #
#  系统托盘 (Windows)
# ================================================================ #

def _run_system_tray(stop_event: threading.Event, open_url: str) -> None:
    """运行系统托盘图标（仅 Windows）。"""
    try:
        import pystray
        from PIL import Image
    except ImportError:
        log.warning("pystray / Pillow 未安装，跳过系统托盘")
        return

    # 创建最小图标 (16x16 蓝色方块)
    img = Image.new("RGB", (16, 16), "#238636")
    icon = pystray.Icon("astrohub", img, "AstroHub")

    def on_open(icon: pystray.Icon, item) -> None:
        log.info("托盘 -> 打开浏览器")
        import webbrowser
        webbrowser.open(open_url)

    def on_stop(icon: pystray.Icon, item) -> None:
        log.info("托盘 -> 停止服务")
        stop_event.set()
        icon.stop()

    def on_exit(icon: pystray.Icon, item) -> None:
        log.info("托盘 -> 退出程序")
        stop_event.set()
        icon.stop()
        sys.exit(0)

    icon.menu = pystray.Menu(
        pystray.MenuItem("打开 AstroHub", on_open, default=True),
        pystray.MenuItem("停止服务", on_stop),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_exit),
    )
    icon.visible = True
    icon.run()


# ================================================================ #
#  Uvicorn 服务端启动
# ================================================================ #

def _run_uvicorn(host: str, port: int, app: FastAPI, stop_event: threading.Event) -> None:
    """运行 uvicorn 服务器。"""
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(config)

    # 在独立线程中运行
    def _serve() -> None:
        server.run()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    log.info("Uvicorn 已启动: http://%s:%d", host, port)

    # 等待停止信号
    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=0.5)
    except KeyboardInterrupt:
        pass

    server.should_exit = True
    thread.join(timeout=5)


# ================================================================ #
#  Headless 模式
# ================================================================ #

def _run_headless(host: str, port: int) -> None:
    """headless 模式: 同步运行 uvicorn 服务端。"""
    app = create_app()
    log.info("=== Headless 模式 ===")
    uvicorn.run(app, host=host, port=port, log_level="info")


# ================================================================ #
#  入口
# ================================================================ #


def main() -> None:
    """程序入口。"""
    parser = argparse.ArgumentParser(description="AstroHub v2.0 - 统一天文设备控制平台")
    parser.add_argument("--headless", action="store_true", help="仅启动 uvicorn 服务端（无桌面窗口）")
    parser.add_argument("--host", default=HOST, help=f"监听地址 (默认: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"监听端口 (默认: {PORT})")
    args = parser.parse_args()

    # Headless 模式
    if args.headless:
        _run_headless(args.host, args.port)
        return

    # 桌面模式
    app = create_app()
    stop_event = threading.Event()
    open_url = f"http://{args.host}:{args.port}"

    # 启动 uvicorn 在后台线程
    uvicorn_thread = threading.Thread(
        target=_run_uvicorn,
        args=(args.host, args.port, app, stop_event),
        daemon=True,
    )
    uvicorn_thread.start()

    # 给 uvicorn 一点时间启动
    import time
    time.sleep(1)

    # 系统托盘 (Windows)
    if sys.platform == "win32":
        tray_thread = threading.Thread(
            target=_run_system_tray,
            args=(stop_event, open_url),
            daemon=True,
        )
        tray_thread.start()

    # 启动 pywebview 桌面窗口 (阻塞直到窗口关闭)
    _run_desktop_window(open_url, stop_event)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("用户中断")
        sys.exit(0)
    except Exception as e:
        log.error("程序异常: %s", e, exc_info=True)
        sys.exit(1)
