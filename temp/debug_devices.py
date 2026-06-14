import asyncio
from playwright.async_api import async_playwright

async def test():
    print("=== Debug device table ===")
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(m.text))
    
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(4)  # Wait for refreshDevices
    
    # Check refreshDevices console log
    refresh_msgs = [m for m in msgs if "REFRESH" in m]
    print(f"REFRESH messages ({len(refresh_msgs)}):")
    for m in refresh_msgs:
        print(f"  {m}")
    
    # Check device API calls
    api_msgs = [m for m in msgs if "api" in m.lower() or "API" in m]
    print(f"API messages ({len(api_msgs)}):")
    for m in api_msgs[:10]:
        print(f"  {m}")
    
    await page.click(".nav-btn:has-text('设备管理')")
    await asyncio.sleep(2)
    
    # Get table content
    table_html = await page.locator("#deviceTable").inner_html()
    print(f"\nDeviceTable HTML:\n{table_html[:500]}")
    
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/debug_devices.png")
    print("Screenshot saved")
    
    # Print all errors
    errors = [m for m in msgs if "error" in m.lower()]
    print(f"\nErrors ({len(errors)}):")
    for m in errors:
        print(f"  {m}")
    
    await browser.close()
    p.stop()

asyncio.run(test())