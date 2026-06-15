"""E2E Test - 功能探测按钮测试"""
from playwright.sync_api import sync_playwright
import requests
import time

API_BASE = 'http://localhost:10280/api/v1'

def test_function_run():
    """测试功能探测按钮"""
    ip = '192.168.5.72'
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print('\n=== 步骤1: 进入高级功能页面 ===')
        page.goto('http://localhost:10280', timeout=30000)
        page.wait_for_timeout(5000)
        
        # 检查连接状态
        connected = page.evaluate('window.connectedDevice')
        print(f'window.connectedDevice: {connected.get("ip") if connected else "无"}')
        
        # 进入高级功能页面
        page.click('[data-page="advanced"]')
        page.wait_for_timeout(3000)
        
        # 检查功能探测按钮
        func_btn = page.query_selector('[data-test="function"]')
        if func_btn:
            print('功能探测按钮存在, 点击...')
            func_btn.click()
            page.wait_for_timeout(2000)
        else:
            print('功能探测按钮不存在')
        
        # 检查运行按钮
        run_btn = page.query_selector('#btnAdvRun')
        if run_btn:
            print('运行按钮存在, disabled:', run_btn.is_disabled())
            if not run_btn.is_disabled():
                print('点击运行按钮...')
                run_btn.click()
                page.wait_for_timeout(20000)
                
                # 检查输出
                output = page.query_selector('#advOutput')
                if output:
                    text = output.text_content()
                    print('输出内容:')
                    print(text[:1000] if text else '无')
        else:
            print('运行按钮不存在')
        
        browser.close()

if __name__ == '__main__':
    test_function_run()