#!/usr/bin/env python
"""Check 404 URLs"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Track 404 responses
        async def log_response(response):
            if response.status == 404:
                print(f"[404] {response.request.method} {response.url}")
        
        page.on("response", lambda r: asyncio.create_task(log_response(r)))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(5000)
        
        await browser.close()

asyncio.run(test())