import asyncio
from playwright.async_api import async_playwright

async def test():
    print("=== 功能验证测试 ===")
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    
    msgs = []
    page.on("console", lambda m: msgs.append(f"[{m.type}] {m.text[:100]}"))
    
    # 1. 页面加载
    print("\n[1] 页面加载...")
    await page.goto("http://127.0.0.1:10280/", timeout=15000)
    await asyncio.sleep(3)
    
    nav_count = await page.locator(".nav-btn").count()
    print(f"    导航按钮: {nav_count}")
    
    # 2. 各页面切换
    pages = ["dashboard", "devices", "console", "observation", "advanced", "replay"]
    print("\n[2] 页面切换...")
    for p_name in pages:
        try:
            await page.click(f".nav-btn[data-page='{p_name}']")
            await asyncio.sleep(0.5)
            visible = await page.locator(f"#page-{p_name}").is_visible()
            print(f"    {p_name}: {'✅' if visible else '❌'}")
        except:
            print(f"    {p_name}: ❌ 未找到")
    
    # 3. 设备管理
    print("\n[3] 设备管理...")
    await page.click(".nav-btn[data-page='devices']")
    await asyncio.sleep(2)
    
    device_table = await page.locator("table tbody tr").count()
    print(f"    设备列表行数: {device_table}")
    
    # 4. 主控台 WASM SDK
    print("\n[4] 主控台 WASM SDK...")
    await page.click(".nav-btn[data-page='console']")
    await asyncio.sleep(8)  # 等待 WASM 加载
    
    wasm_msgs = [m for m in msgs if "WASM" in m or "SDK" in m or "Login" in m]
    print(f"    WASM/SDK 消息数: {len(wasm_msgs)}")
    
    for m in wasm_msgs[:10]:
        print(f"      {m}")
    
    # 检查视频容器
    divPlugin = await page.locator("#divPlugin").count()
    print(f"    divPlugin 存在: {divPlugin > 0}")
    
    # 检查 Canvas
    canvas_count = await page.locator("canvas").count()
    print(f"    Canvas 元素数: {canvas_count}")
    
    # 截图
    await page.screenshot(path="C:/Users/admin/.openclaw/agents/dev-factory/verify_result.png")
    print("\n截图已保存: verify_result.png")
    
    # 5. 错误检查
    errors = [m for m in msgs if "[error]" in m.lower()]
    if errors:
        print("\n[错误]")
        for e in errors[:5]:
            print(f"    {e}")
    else:
        print("\n[无错误] ✅")
    
    await browser.close()
    p.stop()
    
    print("\n=== 验证完成 ===")

asyncio.run(test())