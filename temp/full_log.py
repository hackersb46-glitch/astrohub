import asyncio
from playwright.async_api import async_playwright

async def test():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    all_msgs = []
    page.on("console", lambda m: all_msgs.append(m.text))
    
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(2)
    
    # Go to console
    await page.click(".nav-btn:has-text('主控台')")
    await asyncio.sleep(12)
    
    # Print ALL messages related to login flow
    print("=== ALL relevant messages ===")
    for m in all_msgs:
        if any(k in m for k in ["WASM", "SDK", "Login", "Port", "RTSP", "START", "clickLogin", "connected", "stream", "play", "Resize"]):
            print(m)
    
    await browser.close()
    p.stop()

asyncio.run(test())