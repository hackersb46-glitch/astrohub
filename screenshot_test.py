#!/usr/bin/env python3
"""Screenshot test for all pages"""
import asyncio
from playwright.async_api import async_playwright

async def take_screenshots():
    print("Taking screenshots...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        
        await page.goto("http://127.0.0.1:10280/", timeout=10000)
        await asyncio.sleep(2)
        
        # Dashboard
        await page.screenshot(path="C:\\Users\\admin\\.openclaw\\agents\\dev-factory\\screenshot_dashboard.png")
        print("1. Dashboard screenshot saved")
        
        # Devices page
        await page.click(".nav-btn:has-text('设备管理')")
        await asyncio.sleep(1)
        await page.screenshot(path="C:\\Users\\admin\\.openclaw\\agents\\dev-factory\\screenshot_devices.png")
        print("2. Devices screenshot saved")
        
        # Console page
        await page.click(".nav-btn:has-text('主控台')")
        await asyncio.sleep(1)
        await page.screenshot(path="C:\\Users\\admin\\.openclaw\\agents\\dev-factory\\screenshot_console.png")
        print("3. Console screenshot saved")
        
        await browser.close()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(take_screenshots())