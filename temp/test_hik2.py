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
    await asyncio.sleep(3)  # Wait for refreshDevices to complete
    
    print("2. Devices page...")
    await page.click(".nav-btn:has-text('设备管理')")
    await asyncio.sleep(2)
    
    # Correct table ID: deviceTable (not device-table)
    rows = await page.locator("#deviceTable tr").count()
    print(f"   Rows in deviceTable: {rows}")
    
    if rows > 1:  # First row might be header
        data_rows = await page.locator("#deviceTable tr:not(:first-child)").count()
        print(f"   Data rows: {data_rows}")
        
        if data_rows > 0:
            first_data = page.locator("#deviceTable tr:not(:first-child)").first
            cells = await first_data.locator("td").all_text_contents()
            print(f"   First device data: {cells}")
            
            # Find connect button
            connect_btn = first_data.locator("button:has-text('连接')")
            if await connect_btn.count() > 0:
                print("3. Clicking Connect...")
                await connect_btn.click()
                await asyncio.sleep(5)
                
                login_msgs = [m for m in msgs if "Login" in m or "WASM" in m or "AUTO" in m]
                print(f"   Login/WASM msgs:")
                for m in login_msgs[:15]:
                    print(f"     {m[:150]}")
    
    print("4. Console page...")
    await page.click(".nav-btn:has-text('主控台')")
    await asyncio.sleep(3)
    
    # Check login status element
    status_el = await page.locator("#login-status").count()
    if status_el > 0:
        status = await page.locator("#login-status").inner_text()
        print(f"   Login status: '{status}'")
    else:
        print("   #login-status not found")
        # Try to find any status indicator
        console_info = await page.locator(".console-left h3").first.inner_text()
        print(f"   Console header: '{console_info}'")
    
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/hik_preview.png")
    print("5. Screenshot saved")
    
    # Print all WASM related console messages
    print("\nAll console messages (last 30):")
    for m in msgs[-30:]:
        print(f"  {m[:120]}")
    
    await browser.close()
    p.stop()

asyncio.run(test())