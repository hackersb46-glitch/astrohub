"""E2E Test for v7.30 - module disabled test"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    print('=== Test: Module Disabled State ===')
    print('1. Loading page...')
    page.goto('http://localhost:10280', timeout=30000)
    page.wait_for_timeout(5000)
    
    print('2. Clicking console page...')
    page.click('[data-page="console"]')
    page.wait_for_timeout(3000)
    
    # 检查模块是否有 disabled 类
    sections = ['ptzControlSection', 'trackControlSection', 'mediaControlSection', 'imageControlSection']
    for section_id in sections:
        section = page.query_selector(f'#{section_id}')
        if section:
            has_disabled = section.evaluate('el => el.classList.contains("section-disabled")')
            print(f'3. {section_id} has section-disabled: {has_disabled}')
    
    # 检查连接状态
    connected = page.evaluate('window.connectedDevice')
    print('4. connectedDevice:', '有值' if connected else '无')
    
    browser.close()
    print('Done!')
