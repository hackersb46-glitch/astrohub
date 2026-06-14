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
    await asyncio.sleep(15)  # Longer wait for video stream
    
    # Check video stream start messages
    stream_msgs = [m for m in all_msgs if any(k in m.lower() for k in ["real play", "startstream", "playing", "websocket connect", "stream"])]
    print("=== Stream related messages ===")
    for m in stream_msgs:
        print(m)
    
    if not stream_msgs:
        print("NO stream start messages found!")
        # Check if startConsoleStream2 was called
        click_msgs = [m for m in all_msgs if "CLICK" in m or "START" in m]
        print("\n=== Click/Start messages ===")
        for m in click_msgs:
            print(m)
    
    # Check canvas status
    canvas_count = await page.locator("canvas").count()
    print(f"\nCanvas count: {canvas_count}")
    
    # Check if video is actually playing
    try:
        playing = await page.evaluate("() => window.g_bPlaying2")
        print(f"g_bPlaying2: {playing}")
    except:
        print("g_bPlaying2 not found")
    
    await browser.close()
    p.stop()

asyncio.run(test())