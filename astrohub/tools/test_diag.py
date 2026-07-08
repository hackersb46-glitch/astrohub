"""全面诊断测试 v8.55"""
from playwright.sync_api import sync_playwright
import time, json, urllib.request

print("=" * 60)
print("诊断测试 v8.55")
print("=" * 60)

def api(path, method='GET', data=None):
    try:
        url = f'http://localhost:10280{path}'
        if method == 'GET':
            r = urllib.request.urlopen(url, timeout=10)
            return json.loads(r.read().decode())
        else:
            req = urllib.request.Request(url, data=json.dumps(data).encode() if data else b'',
                headers={'Content-Type': 'application/json'}, method=method)
            r = urllib.request.urlopen(req, timeout=15)
            return json.loads(r.read().decode())
    except Exception as e:
        return {'success': False, 'message': str(e), '_error': str(type(e).__name__)}

# ====== API Tests ======
print("\n--- API: dayNightMode SET day ---")
r = api('/api/v1/ptz/192.168.5.72/image/filter', 'POST', {'dayNightMode': 'day'})
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: dayNightMode SET night ---")
r = api('/api/v1/ptz/192.168.5.72/image/filter', 'POST', {'dayNightMode': 'night'})
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: dayNightMode SET auto ---")
r = api('/api/v1/ptz/192.168.5.72/image/filter', 'POST', {'dayNightMode': 'auto'})
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: IR SET on ---")
r = api('/api/v1/ptz/192.168.5.72/image/filter', 'POST', {'IrcutFilterType': 'on'})
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: IR SET off ---")
r = api('/api/v1/ptz/192.168.5.72/image/filter', 'POST', {'IrcutFilterType': 'off'})
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: shutter GET ---")
r = api('/api/v1/ptz/192.168.5.72/image/shutter')
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: whitebalance GET ---")
r = api('/api/v1/ptz/192.168.5.72/image/whitebalance')
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: noisereduce GET ---")
r = api('/api/v1/ptz/192.168.5.72/image/noisereduce')
print(json.dumps(r, ensure_ascii=False))

print("\n--- API: position GET ---")
r = api('/api/v1/ptz/192.168.5.72/position')
print(json.dumps(r, ensure_ascii=False))

# ====== Playwright Tests ======
print("\n--- Playwright UI tests ---")
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={'width': 1920, 'height': 1080})
    try:
        page.goto('http://localhost:10280', timeout=30000)
        page.wait_for_load_state('networkidle')
        time.sleep(6)
        page.wait_for_function('() => window.connectedDevice && window.connectedDevice.ip', timeout=30000)
        time.sleep(5)

        # Screenshot 1: initial load
        page.screenshot(path='test_diag_01_initial.png')
        print("[SCREENSHOT] test_diag_01_initial.png")

        # Test dayNight button click
        print("\nClick dayNight=day...")
        page.evaluate("() => document.querySelector('#dayNightSwitch .ts-btn[data-value=\"day\"]')?.click()")
        time.sleep(8)
        op = page.evaluate("() => document.getElementById('operationLogBox')?.innerText || ''")
        print(f"  opLog: {op[-120:].strip()}")

        # Check if IR works
        print("\nClick IR=on...")
        page.evaluate("() => document.querySelector('#irCutSwitch .ts-btn[data-value=\"on\"]')?.click()")
        time.sleep(5)
        op = page.evaluate("() => document.getElementById('operationLogBox')?.innerText || ''")
        print(f"  opLog: {op[-120:].strip()}")

        # Check WASM tab switching
        print("\nSwitch to Playback tab...")
        page.evaluate("() => switchTab('playback')")
        time.sleep(3)
        page.screenshot(path='test_diag_02_playback.png')
        print("[SCREENSHOT] test_diag_02_playback.png")

        print("\nSwitch back to Console tab...")
        page.evaluate("() => switchTab('console')")
        time.sleep(5)
        page.screenshot(path='test_diag_03_back_to_console.png')
        print("[SCREENSHOT] test_diag_03_back_to_console.png")

        # Check if WASM video is visible
        visible = page.evaluate("() => { var v = document.getElementById('divPlugin'); return v ? (v.children.length > 0) : false; }")
        print(f"  WASM video visible after tab switch: {visible}")

    except Exception as e:
        print(f"[ERROR] {e}")
    b.close()

print("\nDone.")
