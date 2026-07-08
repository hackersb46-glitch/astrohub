"""
AstroHub v8.01 E2E 全功能验证脚本 (简化版)
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:10280"
DEVICE_IP = "192.168.5.72"
SCREENSHOT_DIR = Path("e2e_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

results = []

def log(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append({"name": name, "ok": ok, "detail": detail})
    print(f"[{status}] {name}: {detail}")

async def test_all():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. 首页
        await page.goto(BASE_URL, timeout=30000)
        log("首页加载", page.url.startswith(BASE_URL), f"URL: {page.url}")
        log("页面标题", "AstroHub" in await page.title())
        
        # 2. 设备管理页面
        await page.click('[data-page="devices"]', timeout=5000)
        await page.wait_for_timeout(1000)
        log("设备管理页面", await page.locator('#page-devices').is_visible(), "页面可见")
        
        # 3. 主控台页面
        await page.click('[data-page="console"]', timeout=5000)
        await page.wait_for_timeout(2000)
        log("主控台页面", await page.locator('#page-console').is_visible(), "页面可见")
        
        # 4. 高级功能页面
        await page.click('[data-page="advanced"]', timeout=5000)
        await page.wait_for_timeout(1000)
        log("高级功能页面", await page.locator('#page-advanced').is_visible(), "页面可见")
        
        # 5. 回放页面
        await page.click('[data-page="replay"]', timeout=5000)
        await page.wait_for_timeout(1000)
        log("回放页面", await page.locator('#page-replay').is_visible(), "页面可见")
        
        # 6. 设置页面
        await page.click('[data-page="settings"]', timeout=5000)
        await page.wait_for_timeout(1000)
        log("设置页面", await page.locator('#page-settings').is_visible(), "页面可见")
        
        # 7. API 测试
        api_endpoints = [
            ("设备列表", "/api/v1/devices"),
            ("PTZ位置", f"/api/v1/ptz/{DEVICE_IP}/position"),
            ("光圈", f"/api/v1/ptz/{DEVICE_IP}/image/iris"),
            ("快门", f"/api/v1/ptz/{DEVICE_IP}/image/shutter"),
            ("白平衡", f"/api/v1/ptz/{DEVICE_IP}/image/whitebalance"),
            ("降噪", f"/api/v1/ptz/{DEVICE_IP}/image/noisereduce"),
        ]
        
        for name, endpoint in api_endpoints:
            try:
                resp = await page.evaluate(f"""
                    async () => {{
                        const r = await fetch('{BASE_URL}{endpoint}');
                        return {{ status: r.status, ok: r.ok }};
                    }}
                """)
                log(f"API-{name}", resp['ok'], f"status={resp['status']}")
            except Exception as e:
                log(f"API-{name}", False, str(e))
        
        await browser.close()
        
        # 打印汇总
        print("\n" + "="*60)
        total = len(results)
        passed = sum(1 for r in results if r['ok'])
        print(f"总计: {total} 项 | 通过: {passed} | 失败: {total-passed}")
        print(f"通过率: {passed/total*100:.1f}%")
        print("="*60)

if __name__ == "__main__":
    asyncio.run(test_all())
