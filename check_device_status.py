"""检查已连接设备状态"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        
        # 导航到主控台
        await page.goto("http://127.0.0.1:10280", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(3000)
        
        # 检查 window.connectedDevice
        connected_device = await page.evaluate("window.connectedDevice")
        print(f"window.connectedDevice: {connected_device}")
        
        # 检查按钮状态
        for switch_id in ['dayNightSwitch', 'irCutSwitch']:
            switch = await page.query_selector(f'#{switch_id}')
            if switch:
                buttons = await switch.query_selector_all('.ts-btn')
                print(f"\n{switch_id}:")
                for i, btn in enumerate(buttons):
                    class_name = await btn.get_attribute('class')
                    data_value = await btn.get_attribute('data-value')
                    print(f"  Button {i}: class='{class_name}', data-value='{data_value}'")
        
        # 检查慢快门
        slow_shutter = await page.query_selector('#slowShutterSelect')
        if slow_shutter:
            current_value = await slow_shutter.get_attribute('value')
            print(f"\nslowShutterSelect value: {current_value}")
        
        # 截图
        await page.screenshot(path="check_device_status.png", full_page=False)
        print("\nScreenshot saved: check_device_status.png")
        
        await browser.close()

asyncio.run(main())
