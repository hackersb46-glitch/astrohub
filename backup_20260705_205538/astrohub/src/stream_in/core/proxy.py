"""
StreamIn WebSocket 代理
负责将 WASM 插件的 WebSocket 请求转发到摄像头
"""
import asyncio
import json
import aiohttp
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
import requests
from requests.auth import HTTPDigestAuth
from src.stream_in.core.logger import wasm_log
from src.stream_in.core.device_cache import get_cached_device

# WebSocket 代理路径（SDK 会连接到这里）
WEBSOCKET_PROXY_PATH = "/webSocketVideoCtrlProxy"


async def _get_ws_token(camera_ip: str, camera_port: int, username: str, password: str) -> str:
    """
    从摄像头获取 WebSocket token
    
    使用 requests + HTTPDigestAuth 直接请求，因为 ISAPI 客户端无法处理 JSON 响应
    """
    url = f"http://{camera_ip}:{camera_port}/ISAPI/Security/token?format=json"
    
    try:
        # 使用 requests 同步请求（在线程池中执行）
        def fetch_token():
            r = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=5)
            if r.status_code == 200:
                data = r.json()
                return data.get("Token", {}).get("value", "")
            return ""
        
        # 在线程池中执行同步请求
        token = await asyncio.to_thread(fetch_token)
        
        if token:
            wasm_log.info(f"WS: Got token: {token[:20]}...")
        else:
            wasm_log.warning(f"WS: Failed to get token")
        
        return token
    except Exception as e:
        wasm_log.error(f"WS: Token request error: {e}")
        return ""


async def websocket_proxy_endpoint(websocket: WebSocket):
    """
    WebSocket 代理端点
    
    处理流程：
    1. 接受 WASM 插件的 WebSocket 连接
    2. 从 cookie 中提取设备信息
    3. 从摄像头获取 WebSocket token
    4. 连接到摄像头的 WebSocket 端口
    5. 双向转发消息
    """
    await websocket.accept()
    wasm_log.info("WS: Browser WebSocket connected")
    
    try:
        # 从 cookie 中提取设备信息
        # SDK 的 k() 函数会设置这些 cookie：
        # - webVideoCtrlProxyWs: 摄像头地址和端口 (如 "192.168.5.72:7681")
        # - webVideoCtrlProxyWsChannel: 通道 ID (如 "102")
        
        cookies = websocket.cookies
        proxy_ws = cookies.get("webVideoCtrlProxyWs", "")
        proxy_channel = cookies.get("webVideoCtrlProxyWsChannel", "")
        
        wasm_log.info(f"WS: Cookies - proxy_ws={proxy_ws}, proxy_channel={proxy_channel}")
        
        # 解析摄像头地址和端口
        if not proxy_ws:
            # 尝试从缓存获取设备信息
            device_info = await get_cached_device()
            if device_info:
                camera_ip = device_info.get("ip", "")
                camera_port = device_info.get("ws_port", 7681)
                username = device_info.get("username", "admin")
                password = device_info.get("password", "Nftw1357")
                channel_id = proxy_channel or "102"
                wasm_log.info(f"WS: Using cached device info: {camera_ip}:{camera_port}")
            else:
                wasm_log.error("WS: No device info in cookies or cache")
                await websocket.close(code=1008, reason="No device info")
                return
        else:
            # 从 cookie 解析
            # 格式: "192.168.5.72:7681" 或 "192.168.5.72"
            if ":" in proxy_ws:
                camera_ip, camera_port_str = proxy_ws.split(":", 1)
                camera_port = int(camera_port_str)
            else:
                camera_ip = proxy_ws
                camera_port = 7681  # 默认 WebSocket 端口
            
            # 从缓存获取凭据
            device_info = await get_cached_device()
            username = device_info.get("username", "admin") if device_info else "admin"
            password = device_info.get("password", "Nftw1357") if device_info else "Nftw1357"
            
            # 解析通道 ID
            # 格式可能是 "102" 或 "1/2" 或 "102?deviceIdentify=..."
            channel_id = proxy_channel.split("?")[0] if proxy_channel else "102"
            # 转换 "102" 为 "1/2" 格式
            if channel_id.isdigit() and len(channel_id) == 3:
                channel_id = f"{channel_id[0]}/{channel_id[2]}"
        
        wasm_log.info(f"WS: Target device: {camera_ip}:{camera_port}, channel={channel_id}")
        
        # 获取 WebSocket token
        token = await _get_ws_token(camera_ip, camera_port, username, password)
        
        if not token:
            wasm_log.error("WS: Failed to get token, cannot connect to camera")
            await websocket.close(code=1011, reason="Failed to get token")
            return
        
        # 构建摄像头 WebSocket URL
        # 格式: ws://IP:PORT/CHANNEL?version=0.1&cipherSuites=0&token=TOKEN
        camera_ws_url = f"ws://{camera_ip}:{camera_port}/{channel_id}?version=0.1&cipherSuites=0&token={token}"
        
        wasm_log.info(f"WS: Connecting to camera: {camera_ws_url[:50]}...")
        
        # 连接到摄像头 WebSocket
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(camera_ws_url, timeout=10) as camera_ws:
                    wasm_log.info("WS: Connected to camera WebSocket")
                    
                    # 双向转发任务
                    async def forward_browser_to_camera():
                        """转发浏览器消息到摄像头"""
                        try:
                            async for msg in websocket.iter_text():
                                wasm_log.debug(f"WS: Browser->Camera: {msg[:100]}")
                                await camera_ws.send_str(msg)
                        except WebSocketDisconnect:
                            wasm_log.info("WS: Browser disconnected")
                        except Exception as e:
                            wasm_log.error(f"WS: Browser->Camera error: {e}")
                    
                    async def forward_camera_to_browser():
                        """转发摄像头消息到浏览器"""
                        try:
                            async for msg in camera_ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    wasm_log.debug(f"WS: Camera->Browser: {msg.data[:100]}")
                                    await websocket.send_text(msg.data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    wasm_log.debug(f"WS: Camera->Browser: binary {len(msg.data)} bytes")
                                    await websocket.send_bytes(msg.data)
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    wasm_log.error(f"WS: Camera WebSocket error: {msg.data}")
                                    break
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    wasm_log.info("WS: Camera WebSocket closed")
                                    break
                        except Exception as e:
                            wasm_log.error(f"WS: Camera->Browser error: {e}")
                    
                    # 并发执行双向转发
                    await asyncio.gather(
                        forward_browser_to_camera(),
                        forward_camera_to_browser(),
                        return_exceptions=True
                    )
                    
            except Exception as e:
                wasm_log.error(f"WS: Failed to connect to camera: {e}")
                await websocket.close(code=1011, reason=f"Camera connection failed: {e}")
                return
    
    except Exception as e:
        wasm_log.error(f"WS: Proxy error: {e}")
        try:
            await websocket.close(code=1011, reason=f"Proxy error: {e}")
        except:
            pass
    
    finally:
        wasm_log.info("WS: Proxy connection closed")
