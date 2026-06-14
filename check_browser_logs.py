#!/usr/bin/env python
"""Check browser console logs for WASM login failure"""
import asyncio
from playwright.async_api import async_playwright

async def check_logs():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Listen to console logs
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: logs.append(f"[ERROR] {err}"))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(3000)
        
        # Set connectedDevice
        await page.evaluate("""() => {
            window.connectedDevice = {
                ip: "192.168.5.72",
                port: 80,
                username: "admin",
                password: "Nftw1357"
            };
        }""")
        
        # Navigate to console
        await page.click("text=主控台")
        await page.wait_for_timeout(2000)
        
        # Trigger login
        await page.evaluate("() => { if(typeof clickLogin2 === 'function') clickLogin2(); }")
        await page.wait_for_timeout(5000)
        
        # Print logs
        print("=== Browser Console Logs ===")
        for log in logs[-50:]:
            print(log)
        
        # Check login status
        logged_in = await page.evaluate("() => typeof g_bLoggedIn2 !== 'undefined' ? g_bLoggedIn2 : false")
        print(f"\ng_bLoggedIn2: {logged_in}")
        
        await browser.close()

asyncio.run(check_logs())