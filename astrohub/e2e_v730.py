"""E2E Test for v7.30"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    print('1. Loading page...')
    page.goto('http://localhost:10280', timeout=30000)
    page.wait_for_timeout(3000)
    
    print('2. Clicking console page...')
    page.click('[data-page="console"]')
    page.wait_for_timeout(3000)
    
    # 检查覆盖层
    overlay = page.query_selector('#wasm-disconnected-overlay')
    print('3. Overlay exists:', overlay is not None)
    
    # 检查增益控件状态
    gain = page.query_selector('#gainLevel')
    if gain:
        print('4. gainLevel disabled:', gain.is_disabled())
    else:
        print('4. gainLevel not found')
    
    # 检查 OSD 开关状态
    info_osd = page.query_selector('#infoOsdSwitch')
    if info_osd:
        print('5. infoOsdSwitch disabled:', info_osd.is_disabled())
    
    ptz_osd = page.query_selector('#ptzOsdSwitch')
    if ptz_osd:
        print('6. ptzOsdSwitch disabled:', ptz_osd.is_disabled())
    
    # 检查视频容器尺寸
    div_plugin = page.query_selector('#divPlugin')
    if div_plugin:
        box = div_plugin.bounding_box()
        if box:
            print('7. divPlugin size:', box['width'], 'x', box['height'])
    
    browser.close()
    print('Done!')
