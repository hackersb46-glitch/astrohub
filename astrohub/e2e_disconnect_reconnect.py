"""E2E Test - 断开重连场景"""
from playwright.sync_api import sync_playwright
import requests
import time

API_BASE = 'http://localhost:10280/api/v1'

def api_disconnect(ip):
    """API 断开连接"""
    r = requests.post(f'{API_BASE}/devices/{ip}/disconnect', timeout=10)
    return r.json()

def api_connect(ip):
    """API 连接"""
    r = requests.post(f'{API_BASE}/devices/{ip}/connect', timeout=10)
    return r.json()

def api_connected():
    """获取连接状态"""
    r = requests.get(f'{API_BASE}/ptz/connected', timeout=5)
    return r.json()

def test_disconnect_reconnect():
    """测试断开重连"""
    # 先获取当前连接状态
    status = api_connected()
    print(f'初始状态: connected={status.get("connected")}, device={status.get("device", {}).get("ip")}')
    
    if not status.get('connected'):
        print('设备未连接，先连接...')
        ip = '192.168.5.72'
        api_connect(ip)
        time.sleep(2)
        status = api_connected()
        print(f'连接后: connected={status.get("connected")}')
    
    ip = status.get('device', {}).get('ip', '192.168.5.72')
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print('\n=== 步骤1: 加载页面（已连接状态）===')
        page.goto('http://localhost:10280', timeout=30000)
        page.wait_for_timeout(5000)
        
        # 检查初始状态
        connected = page.evaluate('window.connectedDevice')
        print(f'window.connectedDevice: {connected}')
        
        overlay = page.query_selector('#wasm-disconnected-overlay')
        print(f'WASM覆盖层: {overlay is not None}')
        
        # 检查控件状态
        gain = page.query_selector('#gainLevel')
        info_osd = page.query_selector('#infoOsdSwitch')
        if gain:
            print(f'gainLevel disabled: {gain.is_disabled()}')
        if info_osd:
            print(f'infoOsdSwitch disabled: {info_osd.is_disabled()}')
        
        # 检查顶部状态
        device_status = page.query_selector('#deviceStatus')
        ws_status = page.query_selector('#wsStatus')
        wasm_status = page.query_selector('#wasmStatus')
        if device_status:
            print(f'deviceStatus文本: {device_status.text_content()}')
        if ws_status:
            print(f'wsStatus文本: {ws_status.text_content()}')
        if wasm_status:
            print(f'wasmStatus文本: {wasm_status.text_content()}')
        
        print('\n=== 步骤2: 点击断开按钮 ===')
        # 进入设备页面
        page.click('[data-page="devices"]')
        page.wait_for_timeout(2000)
        
        # 找到设备卡片，点击开关断开
        switch = page.query_selector('.device-switch')
        if switch:
            # 检查当前状态
            is_checked = switch.evaluate('el => el.checked')
            print(f'设备开关当前状态: {is_checked}')
            if is_checked:
                print('点击开关断开...')
                switch.click()
                page.wait_for_timeout(5000)
        
        # 检查断开后的状态
        status = api_connected()
        print(f'API状态: connected={status.get("connected")}')
        
        # 回到主控台检查
        page.click('[data-page="console"]')
        page.wait_for_timeout(3000)
        
        connected = page.evaluate('window.connectedDevice')
        print(f'断开后 window.connectedDevice: {connected}')
        
        overlay = page.query_selector('#wasm-disconnected-overlay')
        print(f'断开后 WASM覆盖层: {overlay is not None}')
        
        if device_status:
            print(f'断开后 deviceStatus: {device_status.text_content()}')
        if ws_status:
            print(f'断开后 wsStatus: {ws_status.text_content()}')
        if wasm_status:
            print(f'断开后 wasmStatus: {wasm_status.text_content()}')
        
        if gain:
            print(f'断开后 gainLevel disabled: {gain.is_disabled()}')
        
        print('\n=== 步骤3: 重新连接 ===')
        # 回到设备页面
        page.click('[data-page="devices"]')
        page.wait_for_timeout(2000)
        
        switch = page.query_selector('.device-switch')
        if switch:
            is_checked = switch.evaluate('el => el.checked')
            print(f'设备开关状态: {is_checked}')
            if not is_checked:
                print('点击开关连接...')
                switch.click()
                page.wait_for_timeout(8000)
        
        # 检查连接状态
        status = api_connected()
        print(f'API状态: connected={status.get("connected")}')
        
        # 回到主控台
        page.click('[data-page="console"]')
        page.wait_for_timeout(5000)
        
        connected = page.evaluate('window.connectedDevice')
        print(f'重连后 window.connectedDevice: {connected}')
        
        overlay = page.query_selector('#wasm-disconnected-overlay')
        print(f'重连后 WASM覆盖层: {overlay is not None}')
        
        if device_status:
            print(f'重连后 deviceStatus: {device_status.text_content()}')
        if ws_status:
            print(f'重连后 wsStatus: {ws_status.text_content()}')
        if wasm_status:
            print(f'重连后 wasmStatus: {wasm_status.text_content()}')
        
        if gain:
            print(f'重连后 gainLevel disabled: {gain.is_disabled()}')
        if info_osd:
            print(f'重连后 infoOsdSwitch disabled: {info_osd.is_disabled()}')
        
        browser.close()

if __name__ == '__main__':
    test_disconnect_reconnect()