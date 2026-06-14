import asyncio
import websockets
import requests
from requests.auth import HTTPDigestAuth

# 测试摄像头 WebSocket
async def test_ws():
    # 先获取 token
    token_resp = requests.get('http://192.168.5.72/ISAPI/Security/token?format=json',
        auth=HTTPDigestAuth('admin', 'Nftw1357'), timeout=10)
    print(f'Token status: {token_resp.status_code}')
    if token_resp.status_code == 200:
        token = token_resp.json().get('Token', {}).get('value', '')
        print(f'Token: {token[:20]}...')
        
        # 测试 WebSocket 带认证
        ws_url = f'ws://192.168.5.72:7681/?version=1.0&sessionID={token}&token={token}'
        print(f'WS URL: {ws_url[:60]}...')
        try:
            async with websockets.connect(ws_url, close_timeout=5) as ws:
                print('WebSocket connected!')
                await ws.send('{"action":"play"}')
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                print(f'Response: {msg[:200]}')
        except Exception as e:
            print(f'WebSocket error: {e}')
    else:
        print(f'Token failed: {token_resp.text[:200]}')

asyncio.run(test_ws())
