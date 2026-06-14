import asyncio
from playwright.async_api import async_playwright

async def test_js_errors():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(m.text))
    
    # Track page errors
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(4)
    
    print(f"Console messages ({len(msgs)}):")
    for m in msgs[:30]:
        print(f"  {m[:200]}")
    
    print(f"\nPage errors ({len(errors)}):")
    for e in errors:
        print(f"  {e}")
    
    # Check if init() was called by looking at DOM state
    clock = await page.locator("#clock").inner_text()
    print(f"\nClock: {clock}")
    
    await browser.close()
    p.stop()

asyncio.run(test_js_errors())