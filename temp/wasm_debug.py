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
    
    print("=== Step 1: Initial page ===")
    
    # Go to console
    await page.click(".nav-btn:has-text('主控台')")
    await asyncio.sleep(10)  # Wait for full WASM flow
    
    print("=== Step 2: Console page (10s wait) ===")
    
    # Filter WASM related messages
    wasm_msgs = [m for m in all_msgs if any(k in m for k in ["WASM", "SDK", "Login", "Stream", "Play", "WebSocket", "START", "clickLogin", "connected", "error", "Error"])]
    print("\n=== WASM/SDK Messages ===")
    for m in wasm_msgs[:50]:
        print(m[:200])
    
    # Check divPlugin state
    plugin_html = await page.locator("#divPlugin").inner_html()
    print(f"\n=== divPlugin HTML (first 300) ===\n{plugin_html[:300]}")
    
    # Check player container dimensions
    player_container = await page.locator("#divPluginplayer-container-0").evaluate("el => ({width: el.style.width, height: el.style.height})")
    print(f"\n=== Player container dimensions ===\n{player_container}")
    
    # Take screenshot
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/wasm_debug.png", full_page=True)
    print("\nScreenshot saved: wasm_debug.png")
    
    await browser.close()
    p.stop()

asyncio.run(test())