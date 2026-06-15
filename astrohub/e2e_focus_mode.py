"""E2E 测试 - 对焦模式切换（带控制台日志）"""
from playwright.sync_api import sync_playwright

def test_focus_mode():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # 监听控制台日志
        console_logs = []
        page.on('console', lambda msg: console_logs.append(f'{msg.type}: {msg.text}'))
        
        page.goto('http://localhost:10280')
        page.wait_for_timeout(3000)
        
        page.click('[data-page="console"]')
        page.wait_for_timeout(2000)
        
        print('\n=== Test: Focus Mode Switch ===')
        
        # 检查 connectedDevice
        connected = page.evaluate('window.connectedDevice')
        print(f'connectedDevice: {connected}')
        
        # 直接调用 showToast 测试
        page.evaluate('window.showToast("success", "Test message")')
        page.wait_for_timeout(1000)
        
        # 检查 toast 容器
        toast_container = page.evaluate('''
            (function() {
                var container = document.getElementById("toast-container");
                var toasts = document.querySelectorAll(".toast");
                return {
                    container_exists: container !== null,
                    toast_count: toasts.length,
                    visible_toasts: Array.from(toasts).filter(t => t.classList.contains("show")).length
                };
            })()
        ''')
        print(f'Toast container: {toast_container}')
        
        # 打印相关日志
        print('Console logs:')
        for log in console_logs[-10:]:
            if 'focus' in log.lower() or 'toast' in log.lower() or 'api' in log.lower():
                print(f'  {log}')
        
        # 检查 API 响应
        api_result = page.evaluate('''
            (async function() {
                try {
                    const resp = await fetch('/api/v1/ptz/192.168.5.72/focus/mode', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({mode: 'auto'})
                    });
                    return await resp.json();
                } catch(e) {
                    return {error: e.message};
                }
            })()
        ''')
        print(f'\nAPI Result: {api_result}')
        
        browser.close()

if __name__ == '__main__':
    test_focus_mode()