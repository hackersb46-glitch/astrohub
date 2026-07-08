"""Quick test: v8.56 fixes"""
from playwright.sync_api import sync_playwright
import time, json, urllib.request

def api(path):
    try:
        r = urllib.request.urlopen(f'http://localhost:10280{path}', timeout=10)
        return json.loads(r.read().decode())
    except Exception as e:
        return {'error': str(e)}

print('=== v8.56 Quick Test ===')

# Test 1: Filter API
print('\n--- Test 1: Filter API ---')
r = api('/api/v1/ptz/240f9b764193/image/filter')
print(f'GET /image/filter: {json.dumps(r, indent=2)}')

# Test 2: Page loads
print('\n--- Test 2: Page loads ---')
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={'width': 1920, 'height': 1080})

    errors = []
    page.on('pageerror', lambda err: errors.append(str(err)))

    page.goto('http://localhost:10280', timeout=30000)
    page.wait_for_load_state('networkidle')
    time.sleep(8)

    # Wait for device connection
    page.wait_for_function('() => window.connectedDevice && window.connectedDevice.ip', timeout=30000)
    time.sleep(5)

    # Go to console
    page.evaluate('document.querySelector(\'.nav-btn[data-page="console"]\').click()')
    time.sleep(8)

    # Check IR filter switch is gone
    ir_cut = page.evaluate('document.getElementById("irCutSwitch")')
    print(f'irCutSwitch element exists: {ir_cut is not None}')

    # Check label text
    label = page.evaluate('''() => {
        var labels = document.querySelectorAll('label');
        for (var l of labels) {
            if (l.textContent.includes('日夜')) return l.textContent;
        }
        return null;
    }''')
    print(f'Day/Night label: {label}')

    # Screenshot
    page.screenshot(path='test_v856_01_console.png')

    # Test 3: Switch to replay and back
    print('\n--- Test 3: Tab switch replay -> console ---')
    page.evaluate('document.querySelector(\'.nav-btn[data-page="replay"]\').click()')
    time.sleep(5)
    page.evaluate('document.querySelector(\'.nav-btn[data-page="console"]\').click()')
    time.sleep(8)

    wasm_state = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        return { playing: wp.playing, loggedIn: wp.loggedIn };
    }''')
    print(f'WASM state after tab switch: {json.dumps(wasm_state)}')
    page.screenshot(path='test_v856_02_after_switch.png')

    # Check for JS errors
    if errors:
        print(f'\nJS errors: {errors}')
    else:
        print('\nNo JS errors')

    b.close()

print('\nDone.')
