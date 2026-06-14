import asyncio
from playwright.async_api import async_playwright

async def test():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(m.text))
    
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(2)
    
    print("1. Initial page loaded")
    
    # Go directly to console
    await page.click(".nav-btn:has-text('主控台')")
    await asyncio.sleep(6)
    
    print("2. Console page loaded")
    
    wasm_msgs = [m for m in msgs if "WASM" in m or "Login" in m or "CLICK" in m or "connected" in m.lower()]
    print("WASM/Login messages:")
    for m in wasm_msgs[:25]:
        print(f"  {m[:150]}")
    
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/hik_console.png")
    print("3. Screenshot saved")
    
    plugin = await page.locator("#divPlugin").count()
    print(f"4. divPlugin count: {plugin}")
    
    await browser.close()
    p.stop()

asyncio.run(test())