"""WASM realistic test: start on console (WASM playing), switch to replay, back to console"""
from playwright.sync_api import sync_playwright
import time, json

print('=== WASM Realistic Tab Switch Test ===')

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page(viewport={'width': 1920, 'height': 1080})

    console_msgs = []
    page.on('console', lambda msg: console_msgs.append(f'[{msg.type}] {msg.text[:200]}'))

    page.goto('http://localhost:10280', timeout=30000)
    page.wait_for_load_state('networkidle')
    time.sleep(8)

    # Wait for device connection
    page.wait_for_function('() => window.connectedDevice && window.connectedDevice.ip', timeout=30000)
    time.sleep(5)

    # Go to console first (like user would)
    print('--- Step 1: Go to console ---')
    page.evaluate('document.querySelector(\'.nav-btn[data-page="console"]\').click()')
    time.sleep(8)

    state1 = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        var div = document.getElementById('divPlugin');
        return {
            playing: wp.playing,
            loggedIn: wp.loggedIn,
            divChildren: div ? div.children.length : -1,
            divInnerHTML_len: div ? div.innerHTML.length : 0,
            activePage: document.querySelector('.page.active')?.id
        };
    }''')
    print(f'State 1 (console initial): {json.dumps(state1)}')
    page.screenshot(path='test_wasm_real_01.png')

    # Switch to replay
    print('\n--- Step 2: Switch to replay ---')
    page.evaluate('document.querySelector(\'.nav-btn[data-page="replay"]\').click()')
    time.sleep(5)

    state2 = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        var div = document.getElementById('divPlugin');
        return {
            playing: wp.playing,
            loggedIn: wp.loggedIn,
            divChildren: div ? div.children.length : -1,
            divInnerHTML_len: div ? div.innerHTML.length : 0,
            activePage: document.querySelector('.page.active')?.id
        };
    }''')
    print(f'State 2 (replay): {json.dumps(state2)}')
    page.screenshot(path='test_wasm_real_02.png')

    # Switch back to console
    print('\n--- Step 3: Switch back to console ---')
    page.evaluate('document.querySelector(\'.nav-btn[data-page="console"]\').click()')
    time.sleep(8)

    state3 = page.evaluate('''() => {
        var wp = window.WasmPlayer || {};
        var div = document.getElementById('divPlugin');
        return {
            playing: wp.playing,
            loggedIn: wp.loggedIn,
            divChildren: div ? div.children.length : -1,
            divInnerHTML_len: div ? div.innerHTML.length : 0,
            activePage: document.querySelector('.page.active')?.id
        };
    }''')
    print(f'State 3 (back to console): {json.dumps(state3)}')
    page.screenshot(path='test_wasm_real_03.png')

    # Count Decoder.js loads (memory leak indicator)
    decoder_loads = [m for m in console_msgs if 'Decoder.js loaded' in m]
    print(f'\nDecoder.js loaded {len(decoder_loads)} times')
    for d in decoder_loads:
        print(f'  {d}')

    # Count preview starts
    preview_starts = [m for m in console_msgs if 'Preview started' in m]
    print(f'\nPreview started {len(preview_starts)} times')
    for ps in preview_starts:
        print(f'  {ps}')

    # Print all WASM messages
    print('\n=== All WASM messages ===')
    for msg in console_msgs:
        if 'WASM' in msg or 'wasm' in msg:
            print(f'  {msg}')

    b.close()

print('\nDone.')
