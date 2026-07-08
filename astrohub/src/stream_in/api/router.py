"""
WebSocket 代理 - 使用 SDK k() 函数的路径
关键：从 cookie 解析通道路径，使用正确路径连接相机
"""
from __future__ import annotations
import asyncio
import aiohttp
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.stream_in.core.logger import wasm_log
import requests as sync_requests
from requests.auth import HTTPDigestAuth

stream_in_router = APIRouter(tags=["StreamIn"])
COOP_COEP_PATHS = ("/static/websdk/", "/ISAPI/", "/webSocketVideoCtrlProxy")
_app_state = None


def set_app_state(app_state):
    global _app_state
    _app_state = app_state


def _get_device_credentials():
    if not _app_state:
        return None
    ptz_mgr = getattr(_app_state, 'ptz_controller', None)
    if not ptz_mgr:
        return None
    device = ptz_mgr.get_connected_device()
    if not device:
        return None
    return {
        'ip': device.get('ip', ''),
        'username': device.get('username', 'admin'),
        'password': device.get('password', ''),
    }


def _fetch_token_sync(device_ip: str, username: str, password: str) -> str:
    url = f"http://{device_ip}/ISAPI/Security/token?format=json"
    try:
        r = sync_requests.get(url, auth=HTTPDigestAuth(username, password), timeout=5)
        if r.status_code == 200:
            data = r.json()
            return data.get("Token", {}).get("value", "")
    except Exception as e:
        wasm_log.error(f"Token fetch error: {e}")
    return ""


@stream_in_router.websocket("/{path:path}")
async def ws_video_proxy(websocket: WebSocket, path: str):
    """
    WebSocket 代理
    
    流程：
    1. 从 cookie 解析通道路径
    2. 获取 token
    3. 连接到相机（使用通道路径 + token）
    4. 双向转发
    """
    await websocket.accept()
    
    wasm_log.info(f"WS proxy: /{path}")

    cookies = websocket.cookies or {}
    
    # 按官方 Nginx 方式：proxy_pass http://$cookie_webVideoCtrlProxyWs/?$args;
    # 1. 从 cookie 读设备地址
    cookie_ws = cookies.get("webVideoCtrlProxyWs", "") or cookies.get("webVideoCtrlProxyWss", "")
    if not cookie_ws:
        wasm_log.warning("WS proxy: no webVideoCtrlProxyWs cookie")
        await websocket.close(code=1011, reason="No device cookie")
        return
    
    # 2. 转发查询字符串（官方 Nginx 的 ?$args）
    query_string = websocket.scope.get("query_string", b"").decode("utf-8", errors="ignore")
    camera_url = f"ws://{cookie_ws}/"
    if query_string:
        camera_url += f"?{query_string}"
    
    wasm_log.info(f"WS proxy -> camera: {camera_url}")

    # 连接并转发
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                camera_url,
                timeout=aiohttp.ClientWSTimeout(ws_close=10),
            ) as camera_ws:
                wasm_log.info(f"WS proxy: camera connected, relay starting")

                b2c = 0
                c2b = 0

                async def browser_to_camera():
                    nonlocal b2c
                    try:
                        while True:
                            try:
                                data = await asyncio.wait_for(websocket.receive(), timeout=1)
                            except asyncio.TimeoutError:
                                continue
                            
                            if data.get("type") == "websocket.disconnect":
                                break
                            
                            if "text" in data:
                                b2c += 1
                                if b2c <= 10:
                                    wasm_log.info(f"WS proxy: b->c text #{b2c}: {data['text'][:100]}")
                                await camera_ws.send_str(data["text"])
                            elif "bytes" in data:
                                b2c += 1
                                if b2c <= 10:
                                    wasm_log.info(f"WS proxy: b->c bin #{b2c}: {len(data['bytes'])}B")
                                await camera_ws.send_bytes(data["bytes"])
                    except WebSocketDisconnect:
                        pass
                    except Exception as e:
                        wasm_log.debug(f"b->c end: {type(e).__name__}")
                    finally:
                        wasm_log.info(f"WS proxy: b->c ended, {b2c} msgs")

                async def camera_to_browser():
                    nonlocal c2b
                    try:
                        async for msg in camera_ws:
                            c2b += 1
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                if c2b <= 10:
                                    wasm_log.info(f"WS proxy: c->b text #{c2b}: {msg.data[:100]}")
                                await websocket.send_text(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                if c2b <= 5:
                                    wasm_log.info(f"WS proxy: c->b bin #{c2b}: {len(msg.data)}B")
                                elif c2b % 100 == 0:
                                    wasm_log.info(f"WS proxy: c->b #{c2b}: {len(msg.data)}B")
                                await websocket.send_bytes(msg.data)
                            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                                wasm_log.info(f"WS proxy: camera closed")
                                break
                    except Exception as e:
                        wasm_log.debug(f"c->b end: {type(e).__name__}")
                    finally:
                        wasm_log.info(f"WS proxy: c->b ended, {c2b} msgs")

                await asyncio.gather(browser_to_camera(), camera_to_browser(), return_exceptions=True)
                wasm_log.info(f"WS proxy: relay ended (b2c={b2c}, c2b={c2b})")

    except Exception as e:
        wasm_log.error(f"WS proxy error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass
