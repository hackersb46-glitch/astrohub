"""E2E 测试 - 码流切换验证"""
from playwright.sync_api import sync_playwright
import time

def test_stream_switch():
    """测试主控台码流切换"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # 导航到主控台
        page.goto('http://localhost:10280')
        page.wait_for_timeout(2000)
        
        # 等待页面加载
        page.wait_for_selector('#nav-console', timeout=10000)
        page.click('#nav-console')
        page.wait_for_timeout(2000)
        
        print('\n=== 步骤1: 连接设备 ===')
        # 检查是否已连接
        connected = page.evaluate('window.connectedDevice && window.connectedDevice.ip')
        print(f'已连接: {connected}')
        
        if not connected:
            # 需要先连接设备
            print('未连接，跳转到设备管理...')
            page.click('#nav-device')
            page.wait_for_timeout(1000)
            
            # 点击连接按钮
            connect_btn = page.query_selector('.device-connect-btn')
            if connect_btn:
                connect_btn.click()
                page.wait_for_timeout(5000)
                
                # 回到主控台
                page.click('#nav-console')
                page.wait_for_timeout(3000)
        
        # 检查视频是否播放
        print('\n=== 步骤2: 检查当前码流 ===')
        current_stream = page.evaluate('document.getElementById("streamType").value')
        print(f'当前选择码流: {current_stream}')
        
        # 检查日志
        playing = page.evaluate('window.g_bPlaying2')
        print(f'播放状态: {playing}')
        
        # 切换码流
        print('\n=== 步骤3: 切换到第一码流 ===')
        page.select_option('#streamType', '1')
        page.wait_for_timeout(3000)
        
        # 检查是否切换
        new_stream = page.evaluate('document.getElementById("streamType").value')
        print(f'切换后码流: {new_stream}')
        
        # 检查 WASM 使用的码流
        wasm_stream = page.evaluate('''
            // 检查 WASM 内部状态
            if (window.WebVideoCtrl && window.WebVideoCtrl._oOptions) {
                return window.WebVideoCtrl._oOptions.iStreamType;
            }
            return "无法获取";
        ''')
        print(f'WASM 实际码流: {wasm_stream}')
        
        # 切换到第二码流
        print('\n=== 步骤4: 切换到第二码流 ===')
        page.select_option('#streamType', '2')
        page.wait_for_timeout(3000)
        
        wasm_stream = page.evaluate('''
            if (window.WebVideoCtrl && window.WebVideoCtrl._oOptions) {
                return window.WebVideoCtrl._oOptions.iStreamType;
            }
            return "无法获取";
        ''')
        print(f'WASM 实际码流: {wasm_stream}')
        
        browser.close()

if __name__ == '__main__':
    test_stream_switch()