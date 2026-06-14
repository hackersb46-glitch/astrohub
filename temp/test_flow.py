import asyncio
from playwright.async_api import async_playwright

async def test():
    print("=== Full flow: Connect and preview ===")
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(m.text))
    
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(2)
    
    # Go to devices
    await page.click(".nav-btn:has-text('设备管理')")
    await asyncio.sleep(2)
    
    # Check device table
    table = await page.locator("#deviceTable").inner_html()
    print(f"Device table: {table[:200]}...")
    
    # Find connect button
    connect_btns = await page.locator("button:has-text('连接')").count()
    print(f"Connect buttons: {connect_btns}")
    
    if connect_btns > 0:
        print("Clicking Connect...")
        await page.locator("button:has-text('连接')").first.click()
        await asyncio.sleep(5)  # Wait for WASM login
        
        # Check WASM messages
        wasm_msgs = [m for m in msgs if "WASM" in m or "Login" in m or "CLICK" in m]
        print(f"WASM/Login messages ({len(wasm_msgs)}):")
        for m in wasm_msgs[:15]:
            print(f"  {m[:100]}")
    
    # Go to console
    await page.click(".nav-btn:has-text('主控台')")
    await asyncio.sleep(3)
    
    # Take screenshot
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/hik_final.png")
    print("Screenshot saved: hik_final.png")
    
    await browser.close()
    p.stop()

asyncio.run(test())