#!/usr/bin/env python
"""Check official Hikvision Web UI WebSocket implementation"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Track WebSocket connections
        ws_connections = []
        page.on("websocket", lambda ws: ws_connections.append(ws.url))
        
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        
        # Visit official camera web UI
        print("Visiting official camera web UI...")
        await page.goto("http://192.168.5.72/")
        await page.wait_for_timeout(3000)
        
        # Login
        await page.fill("input[name='username']", "admin")
        await page.fill("input[name='password']", "Nftw1357")
        await page.click("button[type='submit'], input[type='submit']")
        await page.wait_for_timeout(5000)
        
        print(f"\nWebSocket connections found: {ws_connections}")
        
        # Check for video player
        video = await page.query_selector("video, canvas, #divPlugin")
        print(f"Video element found: {video is not None}")
        
        # Print relevant logs
        print("\n=== Console Logs ===")
        for log in logs[-20:]:
            print(log)
        
        await browser.close()

asyncio.run(test())