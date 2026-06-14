"""E2E Test - WASM Login Verification"""
import asyncio
from playwright.async_api import async_playwright
import os
from datetime import datetime

SCREENSHOT_DIR = os.path.expanduser("~/.openclaw/agents/dev-factory/screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def screenshot_path(name):
    return os.path.join(SCREENSHOT_DIR, f"{name}_{datetime.now().strftime('%H%M%S')}.png")

async def test():
    console_logs = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        
        print("[TEST] Loading page...")
        await page.goto("http://localhost:10280", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(3000)
        
        # Navigate to devices and click Connect
        await page.click("[data-page='devices']")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=screenshot_path("01_devices"))
        
        # Click Connect button
        connect_btns = await page.locator("button:has-text('连接')").count()
        print(f"[TEST] Connect buttons: {connect_btns}")
        
        if connect_btns > 0:
            await page.click("button:has-text('连接') >> nth=0")
            await page.wait_for_timeout(8000)
            await page.screenshot(path=screenshot_path("02_connected"))
            
            # Check connectedDevice
            connected = await page.evaluate("() => window.connectedDevice")
            print(f"[TEST] connectedDevice: {connected}")
            
            # Navigate to Console
            await page.click("[data-page='console']")
            await page.wait_for_timeout(10000)
            await page.screenshot(path=screenshot_path("03_console"))
            
            # Check WASM login status
            logged_in = await page.evaluate("() => window.g_bLoggedIn2")
            playing = await page.evaluate("() => window.g_bPlaying2")
            print(f"[TEST] WASM status: loggedIn={logged_in}, playing={playing}")
        
        # Print WASM logs
        print("[TEST] WASM logs:")
        for log in console_logs:
            if 'WASM' in log or 'CLICKLOGIN' in log or 'Login' in log or '401' in log or 'ISAPI' in log:
                print(f"  {log}")
        
        await browser.close()
        print("[TEST] Done")

asyncio.run(test())