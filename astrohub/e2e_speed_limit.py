"""E2E 测试 - Speed 和 Limit 功能验证"""
from playwright.sync_api import sync_playwright
import time

def test_speed_limit():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        page.goto('http://localhost:10280')
        page.wait_for_timeout(3000)
        
        # 导航到高级功能
        page.click('[data-page="advanced"]')
        page.wait_for_timeout(2000)
        
        print('\n=== 测试1: 限位测试 (Limit) ===')
        # 点击限位测试菜单
        page.click('[data-test="limit"]')
        page.wait_for_timeout(1000)
        
        # 检查运行按钮
        run_btn = page.query_selector('#btnAdvRun')
        if run_btn:
            print('运行按钮存在')
            run_btn.click()
            page.wait_for_timeout(5000)
            
            # 检查输出
            output = page.evaluate('document.getElementById("advOutput")?.innerText || "无输出"')
            print(f'输出: {output[:200]}...')
        else:
            print('未找到运行按钮')
        
        print('\n=== 测试2: 速度测试 (Speed) ===')
        # 点击速度测试菜单
        page.click('[data-test="speed"]')
        page.wait_for_timeout(1000)
        
        # 检查运行按钮
        run_btn = page.query_selector('#btnAdvRun')
        if run_btn:
            print('运行按钮存在')
            run_btn.click()
            page.wait_for_timeout(5000)
            
            # 检查输出
            output = page.evaluate('document.getElementById("advOutput")?.innerText || "无输出"')
            print(f'输出: {output[:200]}...')
        else:
            print('未找到运行按钮')
        
        browser.close()
        print('\n=== 测试完成 ===')

if __name__ == '__main__':
    test_speed_limit()