"""
AstroHub v8.01 E2E 全功能验证脚本 (简化版)
使用 Playwright 推荐 API，避免复杂选择器语法问题。
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page

# === 配置 ===
BASE_URL = "http://127.0.0.1:10280"
DEVICE_IP = "192.168.5.72"
RESULTS = []
SCREENSHOT_DIR = Path("e2e_screenshots")

def log(name: str, passed: bool, detail: str = ""):
    status = "[OK]" if passed else "[NG]"
    RESULTS.append({"test": name, "passed": passed, "detail": detail})
    print(f"  {status} {name}: {detail}")

async def shot(page: Page, name: str):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(SCREENSHOT_DIR / f"{name}.png"))

# ============================================================
#  1. 设备发现 & 连接
# ============================================================
async def test_devices(page: Page):
    print("\n=== 1. 设备发现 & 连接 ===")
    
    await page.goto(BASE_URL, timeout=30000)
    await page.wait_for_load_state("networkidle")
    await shot(page, "01_home")
    log("首页加载", True)
    
    title = await page.title()
    log("页面标题", "AstroHub" in title, title)
    
    # 点击设备按钮 - 使用 getByText
    try:
        await page.get_by_text("设备", exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(2000)
        await shot(page, "02_devices")
        log("设备页面", True)
    except Exception as e:
        log("设备页面", False, str(e)[:50])
        return
    
    # 检查设备列表
    try:
        rows = await page.locator("table tbody tr").count()
        log("设备列表", rows > 0, f"{rows} 个设备")
    except:
        log("设备列表", False)
    
    # 连接设备
    try:
        btn = page.get_by_role("button", name="连接").first
        if await btn.count() > 0:
            await btn.click(timeout=5000)
            await page.wait_for_timeout(5000)
            await shot(page, "03_connected")
            log("设备连接", True)
        else:
            log("设备连接", False, "未找到连接按钮")
    except Exception as e:
        log("设备连接", False, str(e)[:50])

# ============================================================
#  2. WASM 播放 & 控制
# ============================================================
async def test_playback(page: Page):
    print("\n=== 2. WASM 播放 & 控制 ===")
    
    # 导航到控制台
    try:
        await page.get_by_text("控制台", exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(2000)
        await shot(page, "04_console")
        log("控制台页面", True)
    except Exception as e:
        log("控制台页面", False, str(e)[:50])
        return
    
    # 检查播放器
    try:
        player = page.locator("#player, video, canvas").first
        log("播放器", await player.count() > 0)
    except:
        log("播放器", False)
    
    # 码流切换
    try:
        stream = page.get_by_text("主码流", exact=False).first
        if await stream.count() > 0:
            await stream.click(timeout=3000)
            await page.wait_for_timeout(2000)
            log("码流切换", True)
        else:
            log("码流切换", False, "未找到码流按钮")
    except:
        log("码流切换", False)
    
    # 截图
    try:
        btn = page.get_by_role("button", name="截图").first
        if await btn.count() > 0:
            await btn.click(timeout=3000)
            await page.wait_for_timeout(2000)
            log("截图功能", True)
        else:
            log("截图功能", False)
    except:
        log("截图功能", False)
    
    # 录像
    try:
        btn = page.get_by_role("button", name="录像").first
        if await btn.count() > 0:
            await btn.click(timeout=3000)
            await page.wait_for_timeout(3000)
            await btn.click(timeout=3000)  # 停止
            log("录像功能", True)
        else:
            log("录像功能", False)
    except:
        log("录像功能", False)

# ============================================================
#  3. 高级功能测试
# ============================================================
async def test_advanced(page: Page):
    print("\n=== 3. 高级功能测试 ===")
    
    try:
        await page.get_by_text("高级", exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(2000)
        await shot(page, "05_advanced")
        log("高级页面", True)
    except Exception as e:
        log("高级页面", False, str(e)[:50])
        return
    
    # Function 测试
    try:
        btn = page.get_by_role("button", name="探测").or_(page.get_by_role("button", name="功能")).first
        if await btn.count() > 0:
            await btn.click(timeout=5000)
            await page.wait_for_timeout(10000)
            log("Function测试", True, "已执行")
        else:
            log("Function测试", False)
    except:
        log("Function测试", False)
    
    # Speed 测试
    try:
        btn = page.get_by_role("button", name="速度").first
        if await btn.count() > 0:
            await btn.click(timeout=5000)
            await page.wait_for_timeout(15000)
            log("Speed测试", True, "已执行")
        else:
            log("Speed测试", False)
    except:
        log("Speed测试", False)
    
    # Limit 测试
    try:
        btn = page.get_by_role("button", name="限位").first
        if await btn.count() > 0:
            await btn.click(timeout=5000)
            await page.wait_for_timeout(20000)
            log("Limit测试", True, "已执行")
        else:
            log("Limit测试", False)
    except:
        log("Limit测试", False)

# ============================================================
#  4. ISAPI 图像控制
# ============================================================
async def test_isapi(page: Page):
    print("\n=== 4. ISAPI 图像控制 ===")
    
    # 回到控制台
    try:
        await page.get_by_text("控制台", exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(2000)
    except:
        pass
    
    # 手动模式
    try:
        mode = page.get_by_text("手动", exact=False).first
        if await mode.count() > 0:
            await mode.click(timeout=3000)
            log("手动模式", True)
        else:
            log("手动模式", False)
    except:
        log("手动模式", False)
    
    # 光圈滑块
    try:
        slider = page.locator('input[type="range"]').first
        if await slider.count() > 0:
            await slider.fill("50", timeout=3000)
            log("光圈调整", True)
        else:
            log("光圈调整", False)
    except:
        log("光圈调整", False)
    
    # 快门滑块
    try:
        sliders = page.locator('input[type="range"]')
        count = await sliders.count()
        if count > 1:
            await sliders.nth(1).fill("30", timeout=3000)
            log("快门调整", True)
        else:
            log("快门调整", False, "滑块不足")
    except:
        log("快门调整", False)
    
    # 恢复默认
    try:
        btn = page.get_by_role("button", name="恢复").or_(page.get_by_role("button", name="重置")).first
        if await btn.count() > 0:
            await btn.click(timeout=3000)
            log("恢复默认", True)
        else:
            log("恢复默认", False)
    except:
        log("恢复默认", False)

# ============================================================
#  5. 回放
# ============================================================
async def test_replay(page: Page):
    print("\n=== 5. 回放 ===")
    
    try:
        await page.get_by_text("回放", exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(2000)
        await shot(page, "06_replay")
        log("回放页面", True)
    except Exception as e:
        log("回放页面", False, str(e)[:50])
        return
    
    # 文件列表
    try:
        files = await page.locator("tr, .file-item, [class*='file']").count()
        log("录像文件", files > 0, f"{files} 个")
    except:
        log("录像文件", False)

# ============================================================
#  6. API 验证
# ============================================================
async def test_api(page: Page):
    print("\n=== 6. API 验证 ===")
    
    apis = [
        ("设备列表", f"/api/v1/devices"),
        ("PTZ位置", f"/api/v1/ptz/{DEVICE_IP}/position"),
        ("光圈", f"/api/v1/ptz/{DEVICE_IP}/image/iris"),
        ("快门", f"/api/v1/ptz/{DEVICE_IP}/image/shutter"),
        ("白平衡", f"/api/v1/ptz/{DEVICE_IP}/image/whitebalance"),
        ("降噪", f"/api/v1/ptz/{DEVICE_IP}/image/noisereduce"),
    ]
    
    for name, endpoint in apis:
        try:
            r = await page.evaluate(f"fetch('{BASE_URL}{endpoint}').then(r => {{ return {{ok: r.ok, status: r.status}} }})")
            log(f"API:{name}", r.get("ok", False), f"status={r.get('status')}")
        except Exception as e:
            log(f"API:{name}", False, str(e)[:30])

# ============================================================
#  主流程
# ============================================================
async def main():
    print("=" * 50)
    print("AstroHub v8.01 E2E Test")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.set_default_timeout(30000)
        
        try: await test_devices(page)
        except Exception as e: print(f"  [ERR] devices: {e}")
        
        try: await test_playback(page)
        except Exception as e: print(f"  [ERR] playback: {e}")
        
        try: await test_advanced(page)
        except Exception as e: print(f"  [ERR] advanced: {e}")
        
        try: await test_isapi(page)
        except Exception as e: print(f"  [ERR] isapi: {e}")
        
        try: await test_replay(page)
        except Exception as e: print(f"  [ERR] replay: {e}")
        
        try: await test_api(page)
        except Exception as e: print(f"  [ERR] api: {e}")
        
        await browser.close()
    
    # 汇总
    print("\n" + "=" * 50)
    print("Results Summary")
    print("=" * 50)
    
    passed = sum(1 for r in RESULTS if r["passed"])
    failed = len(RESULTS) - passed
    
    for r in RESULTS:
        s = "[OK]" if r["passed"] else "[NG]"
        print(f"  {s} {r['test']}: {r['detail']}")
    
    print(f"\nTotal: {len(RESULTS)} | Pass: {passed} | Fail: {failed}")
    print(f"Rate: {passed/len(RESULTS)*100:.0f}%" if RESULTS else "No results")
    
    # 保存结果
    (SCREENSHOT_DIR / "results.json").write_text(json.dumps({
        "version": "v8.01",
        "time": datetime.now().isoformat(),
        "passed": passed,
        "failed": failed,
        "results": RESULTS
    }, indent=2), encoding='utf-8')
    
    return failed == 0

if __name__ == "__main__":
    ok = asyncio.run(main())
    exit(0 if ok else 1)
