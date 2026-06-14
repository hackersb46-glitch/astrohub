#!/usr/bin/env python
"""Check browser console logs"""
import asyncio
from playwright.async_api import async_playwright

async def check_logs():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Collect console logs
        logs = []
        page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
        
        await page.goto("http://localhost:10280/")
        await page.wait_for_timeout(3000)
        
        # Set device and trigger login
        await page.evaluate("""
            window.connectedDevice = {
                ip: '192.168.5.72',
                port: 80,
                username: 'admin', 
                password: 'Nftw1357',
                online: true
            };
        """)
        
        await page.click('button[data-page="console"]')
        await page.wait_for_timeout(2000)
        
        await page.evaluate("if (window.clickLogin2) window.clickLogin2();")
        await page.wait_for_timeout(5000)
        
        # Print logs
        print("=== Browser Console Logs ===")
        for log in logs[-30:]:
            print(log)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(check_logs())