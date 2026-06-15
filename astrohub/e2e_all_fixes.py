"""E2E 验证所有修复"""
from playwright.sync_api import sync_playwright
import time

def test_all_fixes():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        page.goto('http://localhost:10280')
        page.wait_for_timeout(3000)
        
        print('\n=== 测试1: 码流切换 ===')
        page.click('[data-page="console"]')
        page.wait_for_timeout(2000)
        
        # 切换码流
        page.select_option('#streamType', '1')
        page.wait_for_timeout(2000)
        stream_val = page.evaluate('document.getElementById("streamType")?.value')
        print(f'码流选择: {stream_val}')
        
        # 检查全局变量
        g_stream = page.evaluate('window.g_iStreamType')
        print(f'全局码流变量: {g_stream}')
        
        print('\n=== 测试2: 曝光模式 ===')
        # 检查曝光模式下拉框
        exposure_options = page.evaluate("""
            (function() {
                var select = document.getElementById("exposureMode");
                if (select) {
                    return Array.from(select.options).map(o => o.value);
                }
                return [];
            })()
        """)
        print(f'曝光模式选项: {exposure_options}')
        
        print('\n=== 测试3: 高级功能画面 ===')
        page.click('[data-page="advanced"]')
        page.wait_for_timeout(2000)
        
        # 检查视频容器位置
        video_location = page.evaluate("""
            (function() {
                var video = document.getElementById("divPlugin");
                var advBox = document.getElementById("advVideoBox");
                if (video && advBox) {
                    return advBox.contains(video) ? "在高级功能页面" : "不在高级功能页面";
                }
                return "未找到";
            })()
        """)
        print(f'视频容器位置: {video_location}')
        
        print('\n=== 测试4: 返回主控台 ===')
        page.click('[data-page="console"]')
        page.wait_for_timeout(2000)
        
        video_location = page.evaluate("""
            (function() {
                var video = document.getElementById("divPlugin");
                var consoleWrap = document.querySelector(".console-video-wrap");
                if (video && consoleWrap) {
                    return consoleWrap.contains(video) ? "在主控台" : "不在主控台";
                }
                return "未找到";
            })()
        """)
        print(f'视频容器位置: {video_location}')
        
        browser.close()
        print('\n=== 所有测试完成 ===')

if __name__ == '__main__':
    test_all_fixes()