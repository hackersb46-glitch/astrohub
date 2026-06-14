import asyncio
from playwright.async_api import async_playwright

async def test():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    all_msgs = []
    page.on("console", lambda m: all_msgs.append(f"[{m.type}] {m.text}"))
    
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(2)
    
    # Go to console
    await page.click(".nav-btn:has-text('主控台')")
    
    # Wait longer and capture all messages
    await asyncio.sleep(12)
    
    print("=== ALL Messages ===")
    for m in all_msgs:
        print(m)
    
    # Check JS variables state
    try:
        state = await page.evaluate("""() => {
            return {
                g_bLoggedIn2: window.g_bLoggedIn2,
                g_bPlaying2: window.g_bPlaying2,
                connectedDevice: window.connectedDevice,
                g_szDeviceIdentify2: window.g_szDeviceIdentify2,
                startConsoleStream2_exists: typeof window.startConsoleStream2
            };
        }""")
        print(f"\n=== JS State ===\n{state}")
    except Exception as e:
        print(f"Error getting state: {e}")
    
    await browser.close()
    p.stop()

asyncio.run(test())