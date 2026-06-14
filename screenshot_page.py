#!/usr/bin/env python
"""Screenshot current page state"""
import asyncio
from playwright.async_api import async_playwright

async def screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(3000)
        
        # Screenshot full page
        await page.screenshot(path="page_state.png", full_page=True)
        print("Screenshot saved: page_state.png")
        
        # Get page HTML
        html = await page.content()
        with open("page_html.txt", "w", encoding="utf-8") as f:
            f.write(html[:5000])
        print("HTML saved: page_html.txt")
        
        await browser.close()

asyncio.run(screenshot())