"""
模拟 SDK 的 WebSocket 连接流程
"""
import asyncio
import aiohttp
import json

async def simulate_sdk_flow():
    # 1. 模拟 SDK 的 k() 函数设置的 cookie
    cookies = {
        'webVideoCtrlProxyWs': 'localhost:10280',
        'webVideoCtrlProxyWsChannel': '102',
        'webVideoCtrlProxy': '192.168.5.72:80'
    }
    
    print("=== Simulating SDK WebSocket Flow ===\n")
    
    # 2. 连接 WebSocket 代理
    async with aiohttp.ClientSession(cookies=cookies) as session:
        # 3. 尝试连接 /webSocketVideoCtrlProxy
        print("Connecting to /webSocketVideoCtrlProxy...")
        try:
            async with session.ws_connect(
                'ws://localhost:10280/webSocketVideoCtrlProxy',
                timeout=aiohttp.ClientWSTimeout(ws_close=10)
            ) as ws:
                print("[OK] Connected!")
                
                # 4. 等待初始消息
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=3)
                    print(f"[MSG] Initial: {msg.data}")
                except asyncio.TimeoutError:
                    print("[TIMEOUT] No initial message")
                
                # 5. 发送 realplay 命令（模拟 SDK 的行为）
                realplay_cmd = {
                    "sequence": 0,
                    "cmd": "realplay",
                    "url": "live://127.0.0.1:10280/1/2"
                }
                await ws.send_json(realplay_cmd)
                print(f"[SENT] {json.dumps(realplay_cmd)}")
                
                # 6. 等待响应
                for i in range(5):
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=2)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            print(f"[RESP] {msg.data[:150]}")
                        elif msg.type == aiohttp.WSMsgType.BINARY:
                            print(f"[DATA] {len(msg.data)} bytes")
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            print("[CLOSED]")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            print(f"[ERROR] {msg.data}")
                            break
                    except asyncio.TimeoutError:
                        print(f"[WAIT] No response {i+1}")
                        break
                        
        except Exception as e:
            print(f"[FAIL] {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_sdk_flow())
