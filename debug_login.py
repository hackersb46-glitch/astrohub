#!/usr/bin/env python
"""Debug WASM login flow"""
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
        
        # Check connectedDevice status
        cd = await page.evaluate("() => window.connectedDevice")
        print(f"connectedDevice: {cd}")
        
        # Check if clickLogin2 exists
        has_fn = await page.evaluate("() => typeof window.clickLogin2 === 'function'")
        print(f"clickLogin2 exists: {has_fn}")
        
        # Manually trigger clickLogin2
        print("Triggering clickLogin2...")
        await page.evaluate("() => { if(window.clickLogin2) window.clickLogin2(); }")
        await page.wait_for_timeout(5000)
        
        # Check login status
        logged_in = await page.evaluate("() => typeof g_bLoggedIn2 !== 'undefined' ? g_bLoggedIn2 : false")
        print(f"g_bLoggedIn2: {logged_in}")
        
        # Print logs
        print("\n=== All Logs ===")
        for log in logs[-50:]:
            print(log)
        
        await browser.close()

asyncio.run(test())