import asyncio
from playwright.async_api import async_playwright

async def test():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(f"[{m.type}] {m.text}"))
    
    try:
        await page.goto("http://127.0.0.1:10280/", timeout=15000)
        await asyncio.sleep(3)
        
        print("=== Page loaded ===")
        
        # Check if nav buttons exist
        nav_count = await page.locator(".nav-btn").count()
        print(f"Nav buttons: {nav_count}")
        
        # Check if pages exist
        pages = ["dashboard", "devices", "console", "observation", "advanced", "replay"]
        for p_name in pages:
            count = await page.locator(f"#page-{p_name}").count()
            print(f"page-{p_name}: {count}")
        
        # Check console messages for errors
        errors = [m for m in msgs if "[error]" in m]
        if errors:
            print("\n=== Errors ===")
            for e in errors[:10]:
                print(e)
        
        # Take screenshot
        await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/split_test.png")
        print("Screenshot saved")
        
    except Exception as e:
        print(f"Error: {e}")
    
    await browser.close()
    p.stop()

asyncio.run(test())