#!/usr/bin/env python
"""Connect device via UI then test WASM"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(2000)
        
        # Go to devices page
        print("Going to devices page...")
        await page.click("text=设备管理")
        await page.wait_for_timeout(1000)
        
        # Find connect button
        connect_btns = await page.query_selector_all("button")
        print(f"Found {len(connect_btns)} buttons")
        
        # Click connect button for the device
        for btn in connect_btns:
            text = await btn.inner_text()
            if "连接" in text:
                print(f"Clicking button: {text}")
                await btn.click()
                await page.wait_for_timeout(3000)
                break
        
        # Back to console
        print("Going to console...")
        await page.click("text=主控台")
        await page.wait_for_timeout(3000)
        
        # Check connectedDevice
        cd = await page.evaluate("() => window.connectedDevice")
        print(f"connectedDevice: {cd}")
        
        # Check login status
        logged_in = await page.evaluate("() => typeof g_bLoggedIn2 !== 'undefined' ? g_bLoggedIn2 : false")
        print(f"g_bLoggedIn2: {logged_in}")
        
        # Print relevant logs
        print("\n=== WASM Logs ===")
        for log in logs[-30:]:
            if any(k in log for k in ["Login", "WASM", "SDK", "WebSocket", "error"]):
                print(log)
        
        await browser.close()

asyncio.run(test())