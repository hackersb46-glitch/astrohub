"""E2E Test - 断开重连场景（直接API）"""
from playwright.sync_api import sync_playwright
import requests
import time

API_BASE = 'http://localhost:10280/api/v1'

def test_disconnect_reconnect_api():
    """测试断开重连 - 直接通过 API"""
    ip = '192.168.5.72'
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print('\n=== 步骤1: 加载页面（初始状态）===')
        page.goto('http://localhost:10280', timeout=30000)
        page.wait_for_timeout(5000)
        
        # 检查初始状态
        r = requests.get(f'{API_BASE}/ptz/connected', timeout=5)
        api_status = r.json()
        print(f'API connected: {api_status.get("connected")}')
        
        connected = page.evaluate('window.connectedDevice')
        print(f'window.connectedDevice: {connected.get("ip") if connected else "无"}')
        
        device_status = page.query_selector('#deviceStatus')
        ws_status = page.query_selector('#wsStatus')
        wasm_status = page.query_selector('#wasmStatus')
        
        print(f'deviceStatus: {device_status.text_content() if device_status else "N/A"}')
        print(f'wsStatus: {ws_status.text_content() if ws_status else "N/A"}')
        print(f'wasmStatus: {wasm_status.text_content() if wasm_status else "N/A"}')
        
        # 进入主控台检查控件状态
        page.click('[data-page="console"]')
        page.wait_for_timeout(3000)
        
        gain = page.query_selector('#gainLevel')
        info_osd = page.query_selector('#infoOsdSwitch')
        print(f'gainLevel disabled: {gain.is_disabled() if gain else "N/A"}')
        print(f'infoOsdSwitch disabled: {info_osd.is_disabled() if info_osd else "N/A"}')
        
        print('\n=== 步骤2: 通过页面调用 disconnectDevice ===')
        # 直接在页面中调用 disconnectDevice
        page.evaluate(f'disconnectDevice("{ip}")')
        page.wait_for_timeout(5000)
        
        # 检查断开后的状态
        r = requests.get(f'{API_BASE}/ptz/connected', timeout=5)
        api_status = r.json()
        print(f'API connected: {api_status.get("connected")}')
        
        connected = page.evaluate('window.connectedDevice')
        print(f'window.connectedDevice: {connected}')
        
        print(f'deviceStatus: {device_status.text_content() if device_status else "N/A"}')
        print(f'wsStatus: {ws_status.text_content() if ws_status else "N/A"}')
        print(f'wasmStatus: {wasm_status.text_content() if wasm_status else "N/A"}')
        
        gain = page.query_selector('#gainLevel')
        info_osd = page.query_selector('#infoOsdSwitch')
        print(f'gainLevel disabled: {gain.is_disabled() if gain else "N/A"}')
        print(f'infoOsdSwitch disabled: {info_osd.is_disabled() if info_osd else "N/A"}')
        
        print('\n=== 步骤3: 通过页面调用 connectDevice ===')
        page.evaluate(f'connectDevice("{ip}")')
        page.wait_for_timeout(8000)
        
        # 检查重连后的状态
        r = requests.get(f'{API_BASE}/ptz/connected', timeout=5)
        api_status = r.json()
        print(f'API connected: {api_status.get("connected")}')
        
        connected = page.evaluate('window.connectedDevice')
        print(f'window.connectedDevice: {connected.get("ip") if connected else "无"}')
        
        print(f'deviceStatus: {device_status.text_content() if device_status else "N/A"}')
        print(f'wsStatus: {ws_status.text_content() if ws_status else "N/A"}')
        print(f'wasmStatus: {wasm_status.text_content() if wasm_status else "N/A"}')
        
        gain = page.query_selector('#gainLevel')
        info_osd = page.query_selector('#infoOsdSwitch')
        print(f'gainLevel disabled: {gain.is_disabled() if gain else "N/A"}')
        print(f'infoOsdSwitch disabled: {info_osd.is_disabled() if info_osd else "N/A"}')
        
        browser.close()

if __name__ == '__main__':
    test_disconnect_reconnect_api()