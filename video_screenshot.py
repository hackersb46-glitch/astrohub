#!/usr/bin/env python
"""Screenshot to verify video stream"""
import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(2000)
        
        await page.evaluate("""() => {
            window.connectedDevice = {
                ip: "192.168.5.72", port: 80,
                username: "admin", password: "Nftw1357"
            };
        }""")
        
        await page.click("text=主控台")
        await page.wait_for_timeout(10000)  # Wait for stream
        
        # Screenshot
        await page.screenshot(path="video_check.png", full_page=False)
        print("Screenshot saved: video_check.png")
        
        # Check if video element exists
        video = await page.query_selector("video")
        canvas = await page.query_selector("canvas")
        div_plugin = await page.query_selector("#divPlugin")
        
        print(f"Video element: {video is not None}")
        print(f"Canvas element: {canvas is not None}")
        print(f"divPlugin: {div_plugin is not None}")
        
        await browser.close()

asyncio.run(check())