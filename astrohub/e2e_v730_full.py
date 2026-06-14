"""E2E Test for v7.30 - full test"""
from playwright.sync_api import sync_playwright
import time

def test_disconnected_state():
    """测试未连接状态"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        # 清除 cookies，模拟未连接状态
        context.clear_cookies()
        page = context.new_page()
        
        print('=== Test: Disconnected State ===')
        print('1. Loading page...')
        page.goto('http://localhost:10280', timeout=30000)
        page.wait_for_timeout(5000)
        
        print('2. Clicking console page...')
        page.click('[data-page="console"]')
        page.wait_for_timeout(5000)
        
        # 检查覆盖层
        overlay = page.query_selector('#wasm-disconnected-overlay')
        print('3. Overlay exists:', overlay is not None, '(should be False)')
        
        # 检查控件状态
        gain = page.query_selector('#gainLevel')
        if gain:
            print('4. gainLevel disabled:', gain.is_disabled(), '(should be True when disconnected)')
        
        info_osd = page.query_selector('#infoOsdSwitch')
        if info_osd:
            print('5. infoOsdSwitch disabled:', info_osd.is_disabled(), '(should be True)')
        
        ptz_osd = page.query_selector('#ptzOsdSwitch')
        if ptz_osd:
            print('6. ptzOsdSwitch disabled:', ptz_osd.is_disabled(), '(should be True)')
        
        # 检查连接状态
        connected = page.evaluate('window.connectedDevice')
        print('7. connectedDevice:', connected)
        
        browser.close()

def test_connected_state():
    """测试已连接状态"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print('\n=== Test: Connected State ===')
        print('1. Loading page...')
        page.goto('http://localhost:10280', timeout=30000)
        page.wait_for_timeout(8000)
        
        print('2. Clicking console page...')
        page.click('[data-page="console"]')
        page.wait_for_timeout(5000)
        
        # 检查覆盖层
        overlay = page.query_selector('#wasm-disconnected-overlay')
        print('3. Overlay exists:', overlay is not None, '(should be False when connected)')
        
        # 检查控件状态
        gain = page.query_selector('#gainLevel')
        if gain:
            print('4. gainLevel disabled:', gain.is_disabled(), '(should depend on exposure mode)')
        
        info_osd = page.query_selector('#infoOsdSwitch')
        if info_osd:
            print('5. infoOsdSwitch disabled:', info_osd.is_disabled(), '(should be False when connected)')
        
        ptz_osd = page.query_selector('#ptzOsdSwitch')
        if ptz_osd:
            print('6. ptzOsdSwitch disabled:', ptz_osd.is_disabled(), '(should be False when connected)')
        
        # 检查连接状态
        connected = page.evaluate('window.connectedDevice')
        print('7. connectedDevice:', connected)
        
        # 检查视频容器尺寸
        div_plugin = page.query_selector('#divPlugin')
        if div_plugin:
            box = div_plugin.bounding_box()
            if box:
                print('8. divPlugin size:', int(box['width']), 'x', int(box['height']))
                print('   Max width check: width <= 1280:', box['width'] <= 1280)
                print('   16:9 check:', round(box['width'] / box['height'], 2), '(should be ~1.78)')
        
        browser.close()

if __name__ == '__main__':
    test_connected_state()