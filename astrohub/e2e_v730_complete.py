"""E2E 验证 v7.30 - 完整测试"""
from playwright.sync_api import sync_playwright
import requests

def test_api_connected():
    """测试 API 连接状态"""
    print('\n=== API 测试 ===')
    r = requests.get('http://localhost:10280/api/v1/ptz/connected', timeout=5)
    data = r.json()
    print(f'1. /api/v1/ptz/connected: success={data.get("success")}, connected={data.get("connected")}')
    if data.get('device'):
        print(f'   设备: {data["device"].get("name")} ({data["device"].get("ip")})')
    return data.get('connected', False)

def test_ui_connected_state():
    """测试已连接状态的 UI"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print('\n=== UI 测试（已连接状态）===')
        print('1. 加载页面...')
        page.goto('http://localhost:10280', timeout=30000)
        page.wait_for_timeout(5000)
        
        print('2. 进入主控台...')
        page.click('[data-page="console"]')
        page.wait_for_timeout(5000)
        
        # 测试覆盖层
        overlay = page.query_selector('#wasm-disconnected-overlay')
        print(f'3. WASM覆盖层存在: {overlay is not None} (应为 False)')
        
        # 测试连接状态
        connected = page.evaluate('window.connectedDevice')
        print(f'4. connectedDevice: {connected.get("ip") if connected else "无"}')
        
        # 测试控件状态
        tests = [
            ('gainLevel', False, '增益滑块'),
            ('infoOsdSwitch', False, '信息OSD开关'),
            ('ptzOsdSwitch', False, 'PTZ OSD开关'),
        ]
        all_pass = True
        for id_, expected_disabled, name in tests:
            el = page.query_selector(f'#{id_}')
            if el:
                disabled = el.is_disabled()
                status = 'PASS' if disabled == expected_disabled else 'FAIL'
                print(f'5. {name} disabled={disabled} (应为 {expected_disabled}) {status}')
                if disabled != expected_disabled:
                    all_pass = False
        
        # 测试视频容器
        div_plugin = page.query_selector('#divPlugin')
        if div_plugin:
            box = div_plugin.bounding_box()
            if box:
                ratio = round(box['width'] / box['height'], 2)
                width_ok = box['width'] <= 1280
                ratio_ok = abs(ratio - 1.78) < 0.1
                print(f'6. divPlugin: {int(box["width"])}x{int(box["height"])}, 比例={ratio}')
                print(f'   宽度<=1280: {width_ok} PASS' if width_ok else f'   宽度<=1280: {width_ok} FAIL')
                print(f'   16:9比例: {ratio_ok} PASS' if ratio_ok else f'   16:9比例: {ratio_ok} FAIL')
        
        # 测试模块禁用状态
        sections = ['ptzControlSection', 'trackControlSection', 'mediaControlSection', 'imageControlSection']
        print('7. 模块禁用状态:')
        for sec_id in sections:
            sec = page.query_selector(f'#{sec_id}')
            if sec:
                has_disabled = sec.evaluate('el => el.classList.contains("section-disabled")')
                status = 'PASS' if not has_disabled else 'FAIL'
                print(f'   {sec_id}: section-disabled={has_disabled} (应为 False) {status}')
        
        # 测试折叠展开功能
        print('8. 测试折叠展开功能:')
        for sec_id in ['ptzControlSection', 'imageControlSection']:
            sec = page.query_selector(f'#{sec_id}')
            if sec:
                # 点击展开
                header = sec.query_selector('.collapsible-header')
                if header:
                    header.click()
                    page.wait_for_timeout(500)
                    is_collapsed = sec.evaluate('el => el.classList.contains("collapsed")')
                    print(f'   {sec_id} 点击后: collapsed={is_collapsed}')
                    # 再次点击折叠
                    header.click()
                    page.wait_for_timeout(500)
                    is_collapsed2 = sec.evaluate('el => el.classList.contains("collapsed")')
                    print(f'   {sec_id} 再次点击: collapsed={is_collapsed2}')
        
        browser.close()
        return all_pass

def main():
    print('========================================')
    print('v7.30 E2E 验证测试')
    print('========================================')
    
    # API 测试
    api_connected = test_api_connected()
    
    # UI 测试
    ui_pass = test_ui_connected_state()
    
    print('\n========================================')
    print('测试结果汇总')
    print('========================================')
    print(f'API连接状态: PASS' if api_connected else 'API连接状态: FAIL')
    print(f'UI控件状态: PASS' if ui_pass else 'UI控件状态: FAIL')
    print('========================================')

if __name__ == '__main__':
    main()