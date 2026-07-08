#!/usr/bin/env python
"""Check actual WebSocket URL from WASM SDK"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        ws_urls = []
        page.on("websocket", lambda ws: ws_urls.append(ws.url))
        
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(2000)
        
        # Go to devices and connect
        await page.click("text=设备管理")
        await page.wait_for_timeout(1000)
        
        connect_btns = await page.query_selector_all("button")
        for btn in connect_btns:
            text = await btn.inner_text()
            if "连接" in text:
                await btn.click()
                await page.wait_for_timeout(3000)
                break
        
        # Go to console
        await page.click("text=主控台")
        await page.wait_for_timeout(5000)
        
        print("=== WebSocket URLs ===")
        for url in ws_urls:
            print(url)
        
        print("\n=== WASM Logs ===")
        for log in logs[-30:]:
            if any(k in log for k in ["WebSocket", "ws://", "webSocketVideoCtrlProxy", "StartRealPlay", "error"]):
                print(log)
        
        await browser.close()

asyncio.run(test())