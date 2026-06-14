#!/usr/bin/env python
"""Analyze official Hikvision Web UI WebSocket"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = browser.new_context()
        page = await context.new_page()
        
        # Capture WebSocket URLs
        ws_urls = []
        page.on("websocket", lambda ws: ws_urls.append(ws.url))
        
        # Network requests
        requests = []
        page.on("request", lambda req: requests.append(f"{req.method} {req.url}"))
        
        try:
            print("=== Visiting official camera UI ===")
            await page.goto("http://192.168.5.72/", timeout=10000)
            await page.wait_for_timeout(2000)
            
            # Login
            try:
                await page.fill("input[name='username']", "admin", timeout=5000)
                await page.fill("input[name='password']", "Nftw1357", timeout=5000)
                await page.click("button[type='submit'], input[type='submit']", timeout=5000)
            except:
                # May already be logged in or different UI
                pass
            
            await page.wait_for_timeout(5000)
            
            print(f"\n=== WebSocket URLs ===")
            for url in ws_urls:
                print(url)
            
            print(f"\n=== Key Requests ===")
            for req in requests[-30:]:
                if any(k in req for k in ["WebSocket", "ws://", "ISAPI", "SDK", "video", "stream"]):
                    print(req)
            
        except Exception as e:
            print(f"Error: {e}")
        
        await browser.close()

asyncio.run(test())