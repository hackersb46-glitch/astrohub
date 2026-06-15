"""E2E 测试 - 码流切换验证"""
from playwright.sync_api import sync_playwright
import time

def test_stream_switch():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        page.goto('http://localhost:10280')
        page.wait_for_timeout(3000)
        
        print('\n=== 步骤1: 检查当前状态 ===')
        
        # 导航到主控台
        page.click('[data-page="console"]')
        page.wait_for_timeout(2000)
        
        # 检查是否已连接
        connected = page.evaluate('window.connectedDevice && window.connectedDevice.ip')
        print(f'已连接设备: {connected}')
        
        # 检查当前码流选择
        current_stream = page.evaluate('document.getElementById("streamType")?.value || "未找到"')
        print(f'当前选择码流: {current_stream}')
        
        # 检查播放状态
        playing = page.evaluate('window.g_bPlaying2')
        print(f'播放状态: {playing}')
        
        if not connected:
            print('\n需要先连接设备，跳过测试')
            browser.close()
            return
        
        # 监听控制台日志
        console_logs = []
        page.on('console', lambda msg: console_logs.append(msg.text) if 'StreamType' in msg.text or 'stream' in msg.text.lower() else None)
        
        print('\n=== 步骤2: 切换到第一码流 ===')
        page.select_option('#streamType', '1')
        page.wait_for_timeout(3000)
        
        # 检查码流
        new_stream = page.evaluate('document.getElementById("streamType")?.value')
        print(f'切换后码流: {new_stream}')
        
        # 检查日志
        print('控制台日志:')
        for log in console_logs[-5:]:
            print(f'  {log}')
        
        print('\n=== 步骤3: 切换到第二码流 ===')
        page.select_option('#streamType', '2')
        page.wait_for_timeout(3000)
        
        new_stream = page.evaluate('document.getElementById("streamType")?.value')
        print(f'切换后码流: {new_stream}')
        
        print('\n=== 步骤4: 切换到第三码流 ===')
        page.select_option('#streamType', '3')
        page.wait_for_timeout(3000)
        
        new_stream = page.evaluate('document.getElementById("streamType")?.value')
        print(f'切换后码流: {new_stream}')
        
        browser.close()
        print('\n测试完成')

if __name__ == '__main__':
    test_stream_switch()