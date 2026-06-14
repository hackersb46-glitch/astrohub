#!/usr/bin/env python
"""Check video stream acquisition"""
import asyncio
from playwright.async_api import async_playwright

async def check_video():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: logs.append(f"[ERROR] {err}"))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(3000)
        
        # Set device
        await page.evaluate("""() => {
            window.connectedDevice = {
                ip: "192.168.5.72", port: 80,
                username: "admin", password: "Nftw1357"
            };
        }""")
        
        # Click console tab
        await page.click("text=主控台")
        await page.wait_for_timeout(3000)
        
        # Wait for auto login
        for i in range(20):
            logged_in = await page.evaluate("() => typeof g_bLoggedIn2 !== 'undefined' ? g_bLoggedIn2 : false")
            if logged_in:
                break
            await page.wait_for_timeout(500)
        
        print(f"Login status: {logged_in}")
        
        # Check for video stream errors
        video_errors = [l for l in logs if "StartRealPlay" in l or "stream" in l.lower() or "404" in l or "websocket" in l.lower()]
        print("\n=== Video Stream Related Logs ===")
        for log in video_errors[-20:]:
            print(log)
        
        await browser.close()

asyncio.run(check_video())