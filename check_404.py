#!/usr/bin/env python
"""Check what URL causes 404"""
import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Track all requests and responses
        async def handle_route(route, request):
            url = request.url
            await route.continue_()
        
        await page.route("**/*", handle_route)
        
        # Monitor responses
        async def log_response(response):
            if response.status == 404:
                print(f"[404] {response.request.method} {response.url}")
        
        page.on("response", lambda r: asyncio.create_task(log_response(r)))
        
        logs = []
        page.on("console", lambda msg: logs.append(msg.text))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(2000)
        
        await page.evaluate("""() => {
            window.connectedDevice = {
                ip: "192.168.5.72", port: 80,
                username: "admin", password: "Nftw1357"
            };
        }""")
        
        await page.click("text=主控台")
        await page.wait_for_timeout(8000)
        
        print("\n=== All 404s captured ===")
        
        await browser.close()

asyncio.run(check())