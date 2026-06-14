"""Fix WebSocket proxy in src/main/main.py to use proper WebSocket-to-WebSocket proxying"""

main_py = r"D:\py_app\astro_hub\src\main\main.py"

with open(main_py, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the old raw TCP proxy with a proper WebSocket proxy
old_ws = '''# WebSocket proxy - SDK uses /webSocketVideoCtrlProxy path
@app.websocket("/{path:path}/webSocketVideoCtrlProxy")
async def websocket_proxy(websocket: WebSocket, path: str):
    # Extract channel from path (e.g., "101" from "/101")
    camera_ws_ip = "192.168.5.72"
    camera_ws_port = 7682
    
    await websocket.accept()
    log.info(f"WebSocket client connected, target: {camera_ws_ip}:{camera_ws_port}")
    
    reader = None
    writer = None
    
    try:
        reader, writer = await asyncio.open_connection(camera_ws_ip, camera_ws_port)
        log.info(f"Connected to camera WebSocket")
        
        async def client_to_camera():
            try:
                while True:
                    data = await websocket.receive()
                    if "text" in data:
                        writer.write(data["text"].encode())
                        await writer.drain()
                    elif "bytes" in data:
                        writer.write(data["bytes"])
                        await writer.drain()
                    elif websocket.application_state == "disconnected":
                        break
            except WebSocketDisconnect:
                log.info("Browser disconnected")
            except Exception as e:
                log.error(f"Browser->Camera error: {e}")
        
        async def camera_to_client():
            try:
                while True:
                    data = await reader.read(4096)
                    if not data:
                        log.info("Camera closed connection")
                        break
                    await websocket.send_bytes(data)
            except Exception as e:
                log.error(f"Camera->Browser error: {e}")
        
        await asyncio.gather(client_to_camera(), camera_to_client())
        
    except Exception as e:
        log.error(f"WebSocket proxy error: {e}")
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()
        if websocket.application_state != "disconnected":
            await websocket.close()
        log.info("WebSocket proxy closed")'''

new_ws = '''# WebSocket proxy - SDK uses /webSocketVideoCtrlProxy path
@app.websocket("/{path:path}/webSocketVideoCtrlProxy")
async def websocket_proxy(websocket: WebSocket, path: str):
    # Extract deviceIdentify from query params
    device_identify = websocket.query_params.get("deviceIdentify", "192.168.5.72:80")
    camera_ip = device_identify.split(":")[0] if ":" in device_identify else device_identify
    camera_ws_port = 7682
    
    # Get the cookie (WebSession) from the client's handshake for auth
    client_headers = dict(websocket.headers)
    ws_cookie = client_headers.get("cookie", "")
    
    log.info(f"WS proxy: client connected, target={camera_ip}:{camera_ws_port}, cookie={'yes' if ws_cookie else 'no'}")
    
    try:
        await websocket.accept()
    except Exception as e:
        log.error(f"WS proxy: accept failed: {e}")
        return
    
    import websockets
    import websockets.exceptions
    
    camera_ws_url = f"ws://{camera_ip}:{camera_ws_port}/webSocketVideoCtrlProxy"
    
    async with websockets.connect(camera_ws_url, additional_headers={"Cookie": ws_cookie}) as cam_ws:
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
    
    log.info("WS proxy: connection closed")'''

if old_ws in content:
    content = content.replace(old_ws, new_ws)
    with open(main_py, "w", encoding="utf-8") as f:
        f.write(content)
    print("Fixed WebSocket proxy!")
else:
    print("Pattern not found!")
    # Show what we have
    idx = content.find("WebSocket proxy")
    if idx >= 0:
        print(repr(content[idx:idx+500]))
