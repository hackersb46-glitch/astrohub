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
        
        print('\n=== Test 1: Limit - Start Check ===')
        page.click('[data-test="limit"]')
        page.wait_for_timeout(1000)
        
        run_btn = page.query_selector('#btnAdvRun')
        if run_btn:
            print('[OK] Run button found')
            run_btn.click()
            page.wait_for_timeout(3000)
            output = page.evaluate('document.getElementById("advOutput")?.innerText || "None"')
            if 'limit' in output.lower() or 'device' in output.lower() or '192.168' in output:
                print('[OK] Limit test started')
                print(f'Output: {output[:150]}')
            else:
                print(f'Output: {output[:100]}')
        
        print('\n=== Test 2: Speed - Start Check ===')
        page.wait_for_timeout(15000)
        
        page.click('[data-test="speed"]')
        page.wait_for_timeout(1000)
        
        run_btn = page.query_selector('#btnAdvRun')
        if run_btn:
            is_disabled = page.evaluate('document.getElementById("btnAdvRun")?.disabled')
            print(f'Button status: {"Disabled" if is_disabled else "Enabled"}')
            
            if not is_disabled:
                run_btn.click()
                page.wait_for_timeout(3000)
                output = page.evaluate('document.getElementById("advOutput")?.innerText || "None"')
                if 'speed' in output.lower() or 'device' in output.lower() or '192.168' in output:
                    print('[OK] Speed test started')
                    print(f'Output: {output[:150]}')
                else:
                    print(f'Output: {output[:100]}')
            else:
                print('[WARN] Button disabled, waiting for Limit to complete...')
        
        browser.close()
        print('\n=== Test Complete ===')

if __name__ == '__main__':
    test_speed_limit()