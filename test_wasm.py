#!/usr/bin/env python
"""Test WASM login and video stream"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(3000)
        
        # Check login status after page load
        for i in range(10):
            logged_in = await page.evaluate("() => typeof g_bLoggedIn2 !== 'undefined' ? g_bLoggedIn2 : false")
            print(f"Check {i+1}: g_bLoggedIn2 = {logged_in}")
            if logged_in:
                break
            await page.wait_for_timeout(1000)
        
        # Print relevant logs
        print("\n=== WASM Logs ===")
        for log in logs[-30:]:
            if any(k in log for k in ["Login", "WASM", "SDK", "StartRealPlay", "WebSocket", "ws://", "error"]):
                print(log)
        
        await page.screenshot(path="wasm_test.png")
        print("Screenshot saved")
        
        await browser.close()

asyncio.run(test())