# -*- coding: utf-8 -*-
"""
WASM 网络请求监控
捕获所有 HTTP/WebSocket 请求以找出 404 错误来源
"""
import asyncio
from playwright.async_api import async_playwright

async def monitor_network():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 监控所有请求
        requests_log = []
        
        async def log_request(request):
            requests_log.append({
                'url': request.url,
                'method': request.method,
                'type': request.resource_type,
                'status': None  # 会在 response 中更新
            })
            print(f"[REQ] {request.method} {request.url}")
        
        async def log_response(response):
            # 更新对应请求的状态
            for req in requests_log:
                if req['url'] == response.url and req['status'] is None:
                    req['status'] = response.status
                    if response.status >= 400:
                        print(f"[ERR] {response.status} {response.url}")
                    break
        
        page.on("request", log_request)
        page.on("response", log_response)
        
        try:
            # 导航到 AstroHub
            print("[1] Loading AstroHub...")
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            # 切换到主控台
            print("[2] Switching to console...")
            await page.evaluate("switchPage('console')")
            await page.wait_for_timeout(1000)
            
            # 清空请求日志
            requests_log.clear()
            
            # 模拟设备连接
            print("[3] Connecting device...")
            await page.evaluate("""
                () => {
                    window.connectedDevice = {
                        ip: '192.168.5.72',
                        port: 80,
                        username: 'admin',
                        password: 'Nftw1357'
                    };
                    onDeviceConnected();
                }
            """)
            
            # 等待 SDK 初始化
            print("[4] Waiting for SDK init...")
            await page.wait_for_timeout(5000)
            
            # 输出所有请求
            print(f"\n[5] All Network Requests ({len(requests_log)} total):")
            for req in requests_log:
                status = req['status'] or 'pending'
                marker = ' ❌' if status and status >= 400 else ''
                print(f"    {req['method']:6} {status:3} {req['type']:10} {req['url']}{marker}")
            
            # 筛选关键请求
            failed_requests = [r for r in requests_log if r['status'] and r['status'] >= 400]
            ws_requests = [r for r in requests_log if r['type'] == 'websocket']
            sdk_requests = [r for r in requests_log if 'sdk' in r['url'].lower() or 'wasm' in r['url'].lower() or 'webVideoCtrl' in r['url']]
            
            print(f"\n[6] Failed Requests ({len(failed_requests)}):")
            for req in failed_requests:
                print(f"    {req['method']} {req['status']} {req['url']}")
            
            print(f"\n[7] WebSocket Requests ({len(ws_requests)}):")
            for req in ws_requests:
                print(f"    {req['url']}")
            
            print(f"\n[8] SDK-related Requests ({len(sdk_requests)}):")
            for req in sdk_requests:
                print(f"    {req['url']}")
            
            await browser.close()
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            await browser.close()

if __name__ == '__main__':
    asyncio.run(monitor_network())
