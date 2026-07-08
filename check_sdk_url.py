import asyncio
from playwright.async_api import async_playwright

async def check_sdk_url():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        
        # 监控所有 WebSocket 连接
        ws_connections = []
        page.on("websocket", lambda ws: ws_connections.append(ws.url))
        
        try:
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            # 切换到主控台触发预览
            await page.evaluate("switchPage('console')")
            await page.wait_for_timeout(3000)
            
            # 模拟设备连接
            await page.evaluate("""
                () => {
                    window.connectedDevice = {ip:'192.168.5.72', port:80, username:'admin', password:'Nftw1357'};
                }
            """)
            await page.wait_for_timeout(2000)
            
            # 手动开始预览
            await page.evaluate("""
                () => {
                    var channel = WasmPlayer.channel || 1;
                    var streamType = 2;
                    wasmStartRealPlay(channel, streamType, true);
                }
            """)
            await page.wait_for_timeout(3000)
            
            print(f"=== WebSocket 连接记录 ===")
            print(f"共 {len(ws_connections)} 个连接:")
            for i, url in enumerate(ws_connections):
                print(f"{i+1}. {url}")
            
            # 检查是否有 webSocketVideoCtrlProxy
            has_proxy = any('webSocketVideoCtrlProxy' in url for url in ws_connections)
            print(f"\n是否连接到代理: {has_proxy}")
            
            await browser.close()
            
        except Exception as e:
            print(f"Error: {e}")
            await browser.close()

if __name__ == '__main__':
    asyncio.run(check_sdk_url())
