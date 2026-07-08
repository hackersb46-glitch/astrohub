"""
检查 WebSocket 端点和路由配置
"""
import asyncio
import aiohttp

async def check_ws_routes():
    # 检查所有路由
    async with aiohttp.ClientSession() as session:
        # 检查根路由
        async with session.get('http://localhost:10280/openapi.json') as resp:
            if resp.status == 200:
                data = await resp.json()
                paths = data.get('paths', {})
                print("=== API Routes ===")
                for path in sorted(paths.keys()):
                    methods = paths[path].keys()
                    print(f"  {path}: {', '.join(methods)}")
        
        # 尝试 WebSocket 连接
        print("\n=== WebSocket Tests ===")
        ws_paths = ['/ws', '/webSocketVideoCtrlProxy', '/102']
        for path in ws_paths:
            try:
                async with session.ws_connect(f'ws://localhost:10280{path}', timeout=2) as ws:
                    print(f"  {path}: Connected!")
                    msg = await asyncio.wait_for(ws.receive(), timeout=2)
                    print(f"    Received: {msg.data[:100] if msg.data else 'empty'}")
            except asyncio.TimeoutError:
                print(f"  {path}: Timeout (no response)")
            except Exception as e:
                print(f"  {path}: {type(e).__name__}: {str(e)[:80]}")

if __name__ == "__main__":
    asyncio.run(check_ws_routes())
