import asyncio
from playwright.async_api import async_playwright

async def test_video():
    print("=== Check video playback status ===")
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(m.text))
    
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(2)
    
    # Go to console
    await page.click(".nav-btn:has-text('主控台')")
    await asyncio.sleep(8)  # Longer wait for video stream
    
    print("Console messages (last 40):")
    for m in msgs[-40:]:
        print(f"  {m[:150]}")
    
    # Check video container state
    plugin_div = await page.locator("#divPlugin").inner_html()
    print(f"\ndivPlugin content (first 500 chars):\n{plugin_div[:500]}")
    
    # Check login status text if exists
    try:
        status = await page.locator("#login-status").inner_text(timeout=2000)
        print(f"login-status: {status}")
    except:
        print("login-status element not found")
    
    # Check if canvas/video element exists
    video_elements = await page.locator("canvas, video").count()
    print(f"Canvas/video elements: {video_elements}")
    
    # Take screenshot
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/video_check.png", full_page=True)
    print("\nScreenshot saved: video_check.png")
    
    await browser.close()
    p.stop()

asyncio.run(test_video())