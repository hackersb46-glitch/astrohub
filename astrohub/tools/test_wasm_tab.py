"""WASM tab switch test: switch to replay, then back to console, check WASM state"""
from playwright.sync_api import sync_playwright
import time, json, urllib.request

def api(path):
    try:
        r = urllib.request.urlopen(f'http://localhost:10280{path}', timeout=10)
        return json.loads(r.read().decode())
    except Exception as e:
        return {'error': str(e)}

print('=== WASM Tab Switch Test ===')

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={'width': 1920, 'height': 1080})

    # Collect console messages
    console_msgs = []
    page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text[:200]}'))

    page.goto('http://localhost:10280', timeout=30000)
    page.wait_for_load_state('networkidle')
    time.sleep(8)

    # Wait for device connection
    page.wait_for_function('() => window.connectedDevice && window.connectedDevice.ip', timeout=30000)
    time.sleep(5)

    # Screenshot 1: console with WASM playing
    page.screenshot(path='test_wasm_01_console.png')
    wasm_state = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        var div = document.getElementById('divPlugin');
        return {
            sdkReady: wp.sdkReady,
            loggedIn: wp.loggedIn,
            playing: wp.playing,
            deviceIp: wp.deviceIp,
            divChildren: div ? div.children.length : -1,
            divInnerHTML_len: div ? div.innerHTML.length : 0,
            activePage: document.querySelector('.page.active')?.id
        };
    }''')
    print(f'State 1 (console): {json.dumps(wasm_state, indent=2)}')

    # Switch to replay tab
    print('\n--- Switch to replay ---')
    page.evaluate('''() => {
        var btn = document.querySelector('.nav-btn[data-page="replay"]');
        if (btn) btn.click();
    }''')
    time.sleep(3)
    page.screenshot(path='test_wasm_02_replay.png')
    wasm_state2 = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        var div = document.getElementById('divPlugin');
        return {
            sdkReady: wp.sdkReady,
            loggedIn: wp.loggedIn,
            playing: wp.playing,
            divChildren: div ? div.children.length : -1,
            divInnerHTML_len: div ? div.innerHTML.length : 0,
            activePage: document.querySelector('.page.active')?.id
        };
    }''')
    print(f'State 2 (replay): {json.dumps(wasm_state2, indent=2)}')

    # Switch to advanced tab
    print('\n--- Switch to advanced ---')
    page.evaluate('''() => {
        var btn = document.querySelector('.nav-btn[data-page="advanced"]');
        if (btn) btn.click();
    }''')
    time.sleep(3)
    page.screenshot(path='test_wasm_03_advanced.png')
    wasm_state3 = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        var div = document.getElementById('divPlugin');
        return {
            sdkReady: wp.sdkReady,
            loggedIn: wp.loggedIn,
            playing: wp.playing,
            divChildren: div ? div.children.length : -1,
            divInnerHTML_len: div ? div.innerHTML.length : 0,
            activePage: document.querySelector('.page.active')?.id,
            divParent: div ? div.parentElement?.id : 'none'
        };
    }''')
    print(f'State 3 (advanced): {json.dumps(wasm_state3, indent=2)}')

    # Switch back to console
    print('\n--- Switch back to console ---')
    page.evaluate('''() => {
        var btn = document.querySelector('.nav-btn[data-page="console"]');
        if (btn) btn.click();
    }''')
    time.sleep(5)
    page.screenshot(path='test_wasm_04_back_console.png')
    wasm_state4 = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        var div = document.getElementById('divPlugin');
        return {
            sdkReady: wp.sdkReady,
            loggedIn: wp.loggedIn,
            playing: wp.playing,
            divChildren: div ? div.children.length : -1,
            divInnerHTML_len: div ? div.innerHTML.length : 0,
            activePage: document.querySelector('.page.active')?.id,
            divParent: div ? div.parentElement?.id : 'none'
        };
    }''')
    print(f'State 4 (back to console): {json.dumps(wasm_state4, indent=2)}')

    # Print relevant console messages
    print('\n=== Relevant console messages ===')
    for msg in console_msgs:
        if 'WASM' in msg or 'wasm' in msg or 'video' in msg.lower() or 'play' in msg.lower() or 'error' in msg.lower():
            print(f'  {msg}')

    b.close()

print('\nDone.')
