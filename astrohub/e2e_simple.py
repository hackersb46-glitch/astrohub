"""E2E WASM Test - fixed"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        wasm_logs = []
        errors = []
        
        page.on("console", lambda msg: wasm_logs.append(msg.text) if "[WASM]" in msg.text else None)
        page.on("pageerror", lambda err: errors.append(str(err)))
        
        try:
            print("Loading page...")
            await page.goto("http://localhost:8000", timeout=30000)
            await page.wait_for_timeout(3000)
            
            print("Clicking console page...")
            # Click console page button
            console_btn = page.locator('[data-page="console"]')
            if await console_btn.count() > 0:
                await console_btn.first.click()
                await page.wait_for_timeout(5000)
            
            print("Checking divPlugin...")
            # Check divPlugin
            divPlugin = page.locator('#divPlugin')
            count = await divPlugin.count()
            divPlugin_exists = count > 0
            
            inner_html = ""
            box = None
            if divPlugin_exists:
                first_elem = divPlugin.first
                box = await first_elem.bounding_box()
                inner_html = await first_elem.evaluate('el => el.innerHTML')
            
            # Screenshot
            screenshot_path = Path("C:/Users/admin/.openclaw/agents/dev-factory/astrohub/data/reports/e2e_wasm.png")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path))
            print(f"Screenshot saved: {screenshot_path}")
            
            print("=== WASM Test Results ===")
            print(f"divPlugin exists: {divPlugin_exists}")
            print(f"divPlugin box: {box}")
            print(f"divPlugin innerHTML length: {len(inner_html)}")
            print(f"divPlugin innerHTML (first 500): {inner_html[:500] if inner_html else 'EMPTY'}")
            print(f"WASM logs count: {len(wasm_logs)}")
            for log in wasm_logs[:20]:
                print(f"  [WASM] {log}")
            print(f"Errors count: {len(errors)}")
            for err in errors[:5]:
                print(f"  ERROR: {err[:200]}")
            
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
        
        await browser.close()

asyncio.run(run_test())