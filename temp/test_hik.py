import asyncio
from playwright.async_api import async_playwright

async def test():
    print("=== Full user flow test ===")
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(m.text))
    
    print("1. Loading page...")
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(2)
    
    print("2. Devices page...")
    await page.click(".nav-btn:has-text('设备管理')")
    await asyncio.sleep(1)
    
    rows = await page.locator("#device-table tbody tr").count()
    print(f"   Rows: {rows}")
    
    if rows > 0:
        first = page.locator("#device-table tbody tr").first
        cells = await first.locator("td").all_text_contents()
        print(f"   Device: {cells}")
        
        btn = first.locator("button:has-text('连接')")
        if await btn.count() > 0:
            print("3. Clicking Connect...")
            await btn.click()
            await asyncio.sleep(5)
    
    print("4. Console page...")
    await page.click(".nav-btn:has-text('主控台')")
    await asyncio.sleep(3)
    
    status = await page.locator("#login-status").inner_text()
    print(f"   Status: {status}")
    
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/hik_preview.png")
    print("5. Screenshot saved")
    
    wasm = [m for m in msgs if "WASM" in m or "Login" in m][:20]
    print(f"WASM msgs ({len(wasm)}):")
    for m in wasm:
        print(f"  {m[:100]}")
    
    await browser.close()
    p.stop()

asyncio.run(test())