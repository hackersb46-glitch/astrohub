"""验证 v8.50 CSS 和交互"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        
        # 导航到主控台
        await page.goto("http://127.0.0.1:10280", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)
        
        # 设置模拟设备
        await page.evaluate("""
            window.connectedDevice = {
                ip: '192.168.1.100',
                username: 'admin',
                password: 'admin',
                port: 80,
                model: 'DS-2DC2204IW-D3'
            };
        """)
        
        # 直接调用 loadFilterStatus
        await page.evaluate("""
            if (typeof loadFilterStatus === 'function') {
                loadFilterStatus('192.168.1.100');
            }
        """)
        await page.wait_for_timeout(1000)
        
        # 检查三段式开关的 CSS 计算样式
        for switch_id in ['dayNightSwitch', 'irCutSwitch']:
            switch = await page.query_selector(f'#{switch_id}')
            if switch:
                # 获取计算样式
                styles = await page.evaluate(f"""
                    (() => {{
                        var el = document.getElementById('{switch_id}');
                        if (!el) return null;
                        var style = window.getComputedStyle(el);
                        return {{
                            display: style.display,
                            border: style.border,
                            borderRadius: style.borderRadius,
                            background: style.backgroundColor,
                            overflow: style.overflow
                        }};
                    }})()
                """)
                print(f"\n{switch_id} styles: {styles}")
                
                # 检查按钮
                buttons = await switch.query_selector_all('.ts-btn')
                for i, btn in enumerate(buttons):
                    btn_styles = await page.evaluate(f"""
                        (() => {{
                            var el = document.querySelectorAll('#{switch_id} .ts-btn')[{i}];
                            if (!el) return null;
                            var style = window.getComputedStyle(el);
                            return {{
                                backgroundColor: style.backgroundColor,
                                color: style.color,
                                border: style.border,
                                padding: style.padding,
                                fontSize: style.fontSize
                            }};
                        }})()
                    """)
                    print(f"  Button {i}: {btn_styles}")
            else:
                print(f"\n{switch_id}: NOT FOUND!")
        
        # 截图
        await page.screenshot(path="verify_css_screenshot.png", full_page=False)
        print("\nScreenshot saved: verify_css_screenshot.png")
        
        # 测试按钮点击
        print("\n--- Testing button click ---")
        day_night_switch = await page.query_selector('#dayNightSwitch')
        if day_night_switch:
            buttons = await day_night_switch.query_selector_all('.ts-btn')
            if buttons:
                await buttons[0].click()
                await page.wait_for_timeout(1000)
                
                # 检查点击后的状态
                for i, btn in enumerate(buttons):
                    classes = await btn.get_attribute('class')
                    print(f"  After click - Button {i}: class='{classes}'")
        
        # 再次截图
        await page.screenshot(path="verify_css_after_click.png", full_page=False)
        print("Screenshot saved: verify_css_after_click.png")
        
        await browser.close()

asyncio.run(main())
