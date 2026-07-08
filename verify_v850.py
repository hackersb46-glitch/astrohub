"""Playwright 截图验证 v8.50"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        
        # 导航到主控台
        await page.goto("http://127.0.0.1:10280", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(2000)
        
        # 截图1: 初始页面
        await page.screenshot(path="screenshot_01_initial.png", full_page=False)
        print("Screenshot 1: Initial page")
        
        # 检查是否有设备连接
        page_content = await page.content()
        if "请连接设备" in page_content:
            print("WARNING: No device connected - showing warning")
        
        # 尝试点击主控台标签
        try:
            console_tab = page.locator("text=主控台").first
            if await console_tab.is_visible():
                await console_tab.click()
                await page.wait_for_timeout(2000)
                print("Clicked console tab")
        except:
            print("No console tab found, trying direct navigation")
        
        # 导航到 console 页面
        await page.goto("http://127.0.0.1:10280#page-console", wait_until="networkidle", timeout=15000)
        await page.wait_for_timeout(3000)
        
        # 截图2: 主控台页面
        await page.screenshot(path="screenshot_02_console.png", full_page=False)
        print("Screenshot 2: Console page")
        
        # 检查三段式开关是否存在
        day_night_switch = page.locator("#dayNightSwitch")
        ir_cut_switch = page.locator("#irCutSwitch")
        slow_shutter = page.locator("#slowShutterSelect")
        
        print(f"dayNightSwitch visible: {await day_night_switch.is_visible()}")
        print(f"irCutSwitch visible: {await ir_cut_switch.is_visible()}")
        print(f"slowShutterSelect visible: {await slow_shutter.is_visible()}")
        
        # 检查三段式开关的按钮
        day_night_buttons = day_night_switch.locator(".ts-btn")
        count = await day_night_buttons.count()
        print(f"dayNight buttons count: {count}")
        for i in range(count):
            btn = day_night_buttons.nth(i)
            text = await btn.text_content()
            class_name = await btn.get_attribute("class")
            data_value = await btn.get_attribute("data-value")
            print(f"  Button {i}: text='{text}', class='{class_name}', data-value='{data_value}'")
        
        ir_cut_buttons = ir_cut_switch.locator(".ts-btn")
        count = await ir_cut_buttons.count()
        print(f"irCut buttons count: {count}")
        for i in range(count):
            btn = ir_cut_buttons.nth(i)
            text = await btn.text_content()
            class_name = await btn.get_attribute("class")
            data_value = await btn.get_attribute("data-value")
            print(f"  Button {i}: text='{text}', class='{class_name}', data-value='{data_value}'")
        
        # 检查 slow shutter select
        ss_options = slow_shutter.locator("option")
        count = await ss_options.count()
        print(f"slowShutter options count: {count}")
        for i in range(count):
            opt = ss_options.nth(i)
            text = await opt.text_content()
            value = await opt.get_attribute("value")
            print(f"  Option {i}: text='{text}', value='{value}'")
        
        # 检查 CSS 样式
        ts_btn_box = await day_night_buttons.first.bounding_box()
        if ts_btn_box:
            print(f"dayNight button[0] bounding box: {ts_btn_box}")
        
        # 截图3: 三段式开关区域
        if await day_night_switch.is_visible():
            await day_night_switch.screenshot(path="screenshot_03_daynight_switch.png")
            print("Screenshot 3: Day/Night switch")
        
        if await ir_cut_switch.is_visible():
            await ir_cut_switch.screenshot(path="screenshot_04_ircut_switch.png")
            print("Screenshot 4: IR Cut switch")
        
        # 尝试点击 dayNight "日" 按钮
        if await day_night_buttons.first.is_visible():
            await day_night_buttons.first.click()
            await page.wait_for_timeout(2000)
            print("Clicked dayNight '日' button")
            
            # 截图5: 点击后
            await day_night_switch.screenshot(path="screenshot_05_after_click.png")
            print("Screenshot 5: After click")
            
            # 检查 active class
            for i in range(await day_night_buttons.count()):
                btn = day_night_buttons.nth(i)
                class_name = await btn.get_attribute("class")
                print(f"  After click - Button {i}: class='{class_name}'")
        
        # 截图6: 慢快门区域
        if await slow_shutter.is_visible():
            await slow_shutter.screenshot(path="screenshot_06_slow_shutter.png")
            print("Screenshot 6: Slow shutter")
        
        await browser.close()

asyncio.run(main())
