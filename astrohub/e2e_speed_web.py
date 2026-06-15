"""E2E 测试 - 通过 Web 界面验证 Speed 测试"""
from playwright.sync_api import sync_playwright

def test_speed_via_web():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # 1. 打开 astrohub
        page.goto('http://localhost:10280')
        page.wait_for_timeout(3000)
        
        # 2. 导航到高级功能页面
        print('\n=== Step 1: Navigate to Advanced ===')
        page.click('[data-page="advanced"]')
        page.wait_for_timeout(2000)
        
        # 3. 点击速度测试菜单项
        print('=== Step 2: Click Speed Test Menu ===')
        page.click('[data-test="speed"]')
        page.wait_for_timeout(1000)
        
        # 4. 检查运行按钮状态
        print('=== Step 3: Check Run Button ===')
        btn_state = page.evaluate('''
            (function() {
                var btn = document.getElementById("btnAdvRun");
                if (btn) {
                    return {
                        exists: true,
                        disabled: btn.disabled,
                        text: btn.innerText
                    };
                }
                return { exists: false };
            })()
        ''')
        print(f'Button: exists={btn_state.get("exists")}, disabled={btn_state.get("disabled")}')
        
        if btn_state.get('exists') and not btn_state.get('disabled'):
            # 5. 点击运行按钮
            print('=== Step 4: Click Run ===')
            page.click('#btnAdvRun')
            page.wait_for_timeout(3000)
            
            # 6. 检查输出
            output = page.evaluate('document.getElementById("advOutput")?.innerText || "None"')
            print(f'Output: {output[:200]}')
            
            if 'speed' in output.lower() or '192.168' in output or 'device' in output.lower():
                print('\n[SUCCESS] Speed test started via web interface!')
            else:
                print('\n[INFO] Output received, check logs above')
        else:
            print(f'\n[WARN] Button disabled or not found. State: {btn_state}')
            print('This may be because another test is running.')
        
        browser.close()

if __name__ == '__main__':
    test_speed_via_web()