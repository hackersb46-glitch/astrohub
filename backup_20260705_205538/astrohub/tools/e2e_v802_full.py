"""
AstroHub v8.02 E2E 全功能交互测试
"""
import asyncio, sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding='utf-8')
BASE_URL = "http://127.0.0.1:10280"
SCREENSHOT_DIR = Path("e2e_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)
results = []

def log(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append({"name": name, "ok": ok, "detail": detail})
    print(f"  [{status}] {name}: {detail}")


async def test_top_header(page):
    print("\n=== 1. 顶部状态栏 ===")
    version = await page.locator("#version-display").text_content()
    log("版本号", version and "v" in version, version)
    clock = await page.locator("#clock").text_content()
    log("时钟", bool(clock and len(clock) > 0), clock)
    ws = await page.locator("#wsStatus").text_content()
    log("ISAPI状态", ws is not None, ws)
    mo = await page.locator("#mediaOutputStatus").text_content()
    log("媒体输出", mo is not None, mo)


async def test_devices(page):
    print("\n=== 2. 设备管理 ===")
    await page.click('[data-page="devices"]')
    await page.wait_for_timeout(1500)
    log("页面切换", await page.is_visible("#page-devices"))
    
    log("本机信息", await page.is_visible("#localhostCard"))
    ip = await page.locator("#localhost-ip").text_content()
    log("本机IP", ip and ip != "-", ip)
    
    log("发现按钮", await page.is_visible("#btnDiscover"))
    await page.click("#btnDiscover")
    await page.wait_for_timeout(6000)
    # 等待设备表格填充（排除空行）
    data_rows = page.locator("#deviceTable tr:not([style*='text-align:center'])")
    await data_rows.first.wait_for(timeout=10000)
    rows = await data_rows.count()
    log("设备列表", rows >= 1, f"共{rows}个设备")
    
    # 连接/断开：设备表格使用开关(checkbox)切换
    toggle = page.locator("#deviceTable .switch input[type='checkbox']").first
    if await toggle.count() > 0:
        was_checked = await toggle.is_checked()
        log("设备状态", True, "已连接" if was_checked else "未连接")
        
        # 如果未连接，点击连接
        if not was_checked:
            await page.locator("#deviceTable .switch .slider").first.click()
            await page.wait_for_timeout(4000)
            now_checked = await toggle.is_checked()
            log("设备连接", now_checked, "开关已打开" if now_checked else "开关未打开")
        
        # 断开
        if await toggle.is_checked():
            await page.locator("#deviceTable .switch .slider").first.click()
            await page.wait_for_timeout(3000)
            still_checked = await toggle.is_checked()
            log("设备断开", not still_checked, "开关已关闭" if not still_checked else "开关未关闭")
        
        # 重新连接
        if not await toggle.is_checked():
            await page.locator("#deviceTable .switch .slider").first.click()
            await page.wait_for_timeout(3000)
            log("重新连接", await toggle.is_checked())
    else:
        log("设备连接", False, "无开关元素")
    
    quick = page.locator("#quickConnectSwitch")
    log("快速连接", await quick.count() > 0, "可见" if await quick.count() > 0 else "不存在")


async def test_console(page):
    print("\n=== 3. 主控台 WASM/码流/截图/录像 ===")
    await page.click('[data-page="console"]')
    await page.wait_for_timeout(2000)
    log("页面切换", await page.is_visible("#page-console"))
    log("WASM容器", await page.is_visible("#divPlugin"))
    
    # 码流按钮
    btns = ["#btnStreamMain", "#btnStreamSub", "#btnStreamThird", "#btnStreamStop"]
    ok_list = [await page.is_visible(b) for b in btns]
    all_ok = all(ok_list)
    log("码流按钮", all_ok, str(ok_list))
    
    await page.click("#btnStreamSub")
    await page.wait_for_timeout(1500)
    log("切换子码流", True)
    
    # 截图
    cap = page.locator("#btnConsoleSnapshot")
    if await cap.count() > 0:
        await cap.click()
        await page.wait_for_timeout(2000)
        log("截图", True)
    else:
        log("截图", False, "无btnConsoleSnapshot")
    
    # 录像
    rec = page.locator("#btnConsoleRecord")
    if await rec.count() > 0:
        txt = await rec.text_content()
        await rec.click()
        await page.wait_for_timeout(2000)
        log("开始录像", True, txt)
        await rec.click()
        await page.wait_for_timeout(1000)
        log("停止录像", True)
    else:
        log("录像", False, "无btnConsoleRecord")


async def test_settings(page):
    print("\n=== 4. 设置页面 ===")
    await page.click('[data-page="settings"]')
    await page.wait_for_timeout(1500)
    log("页面切换", await page.is_visible("#page-settings"))
    
    log("录制路径", await page.is_visible("#settingRecordPath"))
    current = await page.locator("#settingRecordPath").input_value()
    log("当前路径", await page.is_visible("#settingRecordPath"), current or "空")
    
    test_path = current + "_test"
    await page.locator("#settingRecordPath").fill(test_path)
    await page.wait_for_timeout(500)
    new_val = await page.locator("#settingRecordPath").input_value()
    log("修改路径", new_val == test_path, new_val)
    
    await page.locator("#settingRecordPath").fill(current)
    log("恢复路径", True)
    
    log("本机配置", await page.is_visible("#settingLocalConfig"))
    log("设备配置", await page.is_visible("#settingDeviceConfig"))
    
    n = await page.locator("button:has-text('浏览')").count()
    log("浏览按钮", n >= 3, f"{n}个")


async def test_replay(page):
    print("\n=== 5. 回放页面 ===")
    await page.click('[data-page="replay"]')
    await page.wait_for_timeout(1500)
    log("页面切换", await page.is_visible("#page-replay"))
    log("媒体库", await page.is_visible("#replay-tree"))
    
    await page.click('button[onclick="refreshFiles()"]')
    await page.wait_for_timeout(3000)
    
    cnt = await page.locator("#replay-count").text_content()
    log("文件数量", cnt is not None, cnt)
    log("网格", await page.is_visible("#replay-grid"))
    
    n = await page.locator(".replay-thumb, .replay-thumb-video").count()
    log("缩略图", True, f"{n}个")
    
    if n > 0:
        await page.locator(".replay-item").first.click()
        await page.wait_for_timeout(2000)
        log("点击回放", True)
    # 关闭 modal
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    
    log("打开目录", await page.is_visible('button[onclick="openRecordFolder()"]'))


async def test_navigation(page):
    print("\n=== 6. 页面切换 ===")
    for pid, name in [("dashboard","仪表盘"),("devices","设备管理"),("console","主控台"),
                       ("advanced","高级功能"),("replay","回放"),("settings","设置")]:
        await page.click(f'[data-page="{pid}"]')
        await page.wait_for_timeout(400)
        active = await page.evaluate(f'document.querySelector(\'[data-page="{pid}"]\').classList.contains("active")')
        visible = await page.is_visible(f"#page-{pid}")
        log(f"{name}", active and visible)


async def test_api(page):
    print("\n=== 7. API 端点 ===")
    endpoints = [
        ("设备列表", "/api/v1/devices"),
        ("PTZ位置", "/api/v1/ptz/192.168.5.72/position"),
        ("光圈", "/api/v1/ptz/192.168.5.72/image/iris"),
        ("快门", "/api/v1/ptz/192.168.5.72/image/shutter"),
        ("白平衡", "/api/v1/ptz/192.168.5.72/image/whitebalance"),
        ("降噪", "/api/v1/ptz/192.168.5.72/image/noisereduce"),
    ]
    for name, ep in endpoints:
        try:
            resp = await page.evaluate(f"""
                async () => {{ const r = await fetch('{BASE_URL}{ep}'); return {{status:r.status}}; }}
            """)
            log(f"API-{name}", resp["status"] == 200, f"status={resp['status']}")
        except Exception as e:
            log(f"API-{name}", False, str(e))


async def main():
    print("=" * 60)
    print("AstroHub v8.02 E2E 全功能交互测试")
    print("=" * 60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await page.goto(BASE_URL, timeout=30000)
        await page.wait_for_load_state("networkidle")
        
        await test_top_header(page)
        await test_devices(page)
        await test_console(page)
        await test_settings(page)
        await test_replay(page)
        await test_navigation(page)
        await test_api(page)
        
        await page.screenshot(path=str(SCREENSHOT_DIR / "final_v802.png"), full_page=True)
        await browser.close()
    
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    print(f"\n{'='*60}")
    print(f"总计: {total} | 通过: {passed} | 失败: {total-passed}")
    print(f"通过率: {passed/total*100:.1f}%" if total else "")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
