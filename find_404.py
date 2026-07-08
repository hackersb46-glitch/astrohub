# -*- coding: utf-8 -*-
"""
简化诊断：找出 404 错误的具体 URL
"""
import asyncio
from playwright.async_api import async_playwright

async def find_404():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        failed_urls = []
        
        page.on("response", lambda response: (
            failed_urls.append(f"{response.status} {response.url}")
            if response.status >= 400 else None
        ))
        
        try:
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(1000)
            
            await page.evaluate("switchPage('console')")
            await page.wait_for_timeout(500)
            
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
            
            await page.wait_for_timeout(5000)
            
            print("Failed Requests:")
            for url in failed_urls:
                print(f"  {url}")
            
            # 测试关键端点
            print("\nTesting Critical Endpoints:")
            
            # 测试 ISAPI token
            token_resp = await page.evaluate("""
                async () => {
                    try {
                        const resp = await fetch('/ISAPI/Security/token?format=json');
                        return { url: '/ISAPI/Security/token', status: resp.status };
                    } catch(e) {
                        return { url: '/ISAPI/Security/token', error: e.message };
                    }
                }
            """)
            print(f"  {token_resp}")
            
            # 测试 WebSocket 代理端点
            ws_resp = await page.evaluate("""
                async () => {
                    try {
                        const resp = await fetch('/webSocketVideoCtrlProxy');
                        return { url: '/webSocketVideoCtrlProxy', status: resp.status };
                    } catch(e) {
                        return { url: '/webSocketVideoCtrlProxy', error: e.message };
                    }
                }
            """)
            print(f"  {ws_resp}")
            
            await browser.close()
            
        except Exception as e:
            print(f"Error: {e}")
            await browser.close()

if __name__ == '__main__':
    asyncio.run(find_404())
