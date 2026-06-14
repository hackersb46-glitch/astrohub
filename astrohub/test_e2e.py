#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AstroHub v7.12 精简版 E2E 测试"""

import json
import time
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BASE_URL = "http://localhost:10280"
results = {"passed": [], "failed": []}

def log_result(category, test_name, success, detail=""):
    entry = {"category": category, "test": test_name, "detail": detail}
    if success:
        results["passed"].append(entry)
        print(f"[PASS] [{category}] {test_name}")
    else:
        results["failed"].append(entry)
        print(f"[FAIL] [{category}] {test_name}: {detail}")

def main():
    print("=" * 60)
    print("AstroHub v7.12 E2E Test (Clean Build)")
    print("=" * 60)
    
    Path("test_results").mkdir(exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        
        try:
            # ========== 1. 首页加载 ==========
            print("\n[1. Home Page]")
            page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            time.sleep(2)
            log_result("Home", "Page Load", True)
            
            # 版本号
            version = page.locator(".version")
            if version.count() > 0:
                ver_text = version.text_content()
                log_result("Home", "Version Display", "v7.12" in ver_text, ver_text)
            else:
                log_result("Home", "Version Display", False, "not found")
            
            page.screenshot(path="test_results/01_home.png")
            
            # ========== 2. 导航按钮 ==========
            print("\n[2. Navigation]")
            nav_buttons = [
                ("仪表盘", "dashboard"),
                ("设备管理", "devices"),
                ("主控台", "console"),
                ("观测计划", "observation"),
                ("高级功能", "advanced"),
                ("回放", "replay"),
            ]
            
            for name, page_id in nav_buttons:
                btn = page.locator(f"[data-page='{page_id}']")
                log_result("Nav", name, btn.count() > 0)
            
            # ========== 3. 设备管理 ==========
            print("\n[3. Device Management]")
            page.click("[data-page='devices']")
            time.sleep(1)
            
            table = page.locator("table")
            log_result("Devices", "Table", table.count() > 0)
            
            discover_btn = page.locator("button:has-text('发现'), button:has-text('搜索')")
            log_result("Devices", "Discover Button", discover_btn.count() > 0)
            
            quick_switch = page.locator("#quickConnectSwitch")
            log_result("Devices", "Quick Connect Switch", quick_switch.count() > 0)
            
            page.screenshot(path="test_results/02_devices.png")
            
            # ========== 4. 主控台 ==========
            print("\n[4. Console Page]")
            page.click("[data-page='console']")
            time.sleep(1)
            
            ptz_section = page.locator("#ptzControlSection")
            log_result("Console", "PTZ Section", ptz_section.count() > 0)
            
            # PTZ 方向按钮
            directions = ["up", "down", "left", "right"]
            ptz_btns = sum(1 for d in directions if page.locator(f"[onmousedown*=\"ptzMove('{d}'\"]").count() > 0)
            log_result("Console", "PTZ Buttons", ptz_btns >= 4, f"{ptz_btns}/4")
            
            # 预置点
            preset_select = page.locator("#ptzPresetSelect")
            log_result("Console", "Preset Select", preset_select.count() > 0)
            
            preset_btns = ["前往", "保存", "归位"]
            for btn_text in preset_btns:
                btn = page.locator(f"button:has-text('{btn_text}')")
                log_result("Console", f"Preset: {btn_text}", btn.count() > 0)
            
            # 变焦/对焦
            zoom_in = page.locator("[onmousedown*=\"ptzZoom('in'\"]")
            log_result("Console", "Zoom Buttons", zoom_in.count() > 0)
            
            focus_near = page.locator("[onmousedown*=\"ptzFocus('near'\"]")
            log_result("Console", "Focus Buttons", focus_near.count() > 0)
            
            focus_mode = page.locator("#focusMode")
            log_result("Console", "Focus Mode Select", focus_mode.count() > 0)
            
            # 跟踪控制
            track_section = page.locator("#trackControlSection")
            log_result("Console", "Track Section", track_section.count() > 0)
            
            track_btns = ["恒星跟踪", "月球跟踪", "太阳跟踪", "关闭跟踪"]
            for btn_text in track_btns:
                btn = page.locator(f"button:has-text('{btn_text}')")
                log_result("Console", f"Track: {btn_text}", btn.count() > 0)
            
            # 视频容器
            video_box = page.locator("#divPlugin")
            log_result("Console", "Video Container", video_box.count() > 0)
            
            # 媒体操作
            media_section = page.locator("#mediaControlSection")
            log_result("Console", "Media Section", media_section.count() > 0)
            
            stream_select = page.locator("#streamType")
            log_result("Console", "Stream Select", stream_select.count() > 0)
            
            snapshot_btn = page.locator("#btnConsoleSnapshot")
            log_result("Console", "Snapshot Button", snapshot_btn.count() > 0)
            
            record_btn = page.locator("#btnConsoleRecordStart")
            log_result("Console", "Record Button", record_btn.count() > 0)
            
            # Live Stack
            stack_btns = page.locator("[data-stack]")
            log_result("Console", "Live Stack Buttons", stack_btns.count() > 0)
            
            # 画面控制
            image_section = page.locator("#imageControlSection")
            log_result("Console", "Image Control Section", image_section.count() > 0)
            
            page.screenshot(path="test_results/03_console.png")
            
            # ========== 5. 画面控制详细 ==========
            print("\n[5. Image Controls]")
            
            # 展开画面控制
            image_header = page.locator("#imageControlSection .collapsible-header")
            if image_header.count() > 0:
                image_header.click()
                time.sleep(0.5)
            
            sliders = [
                ("亮度", "consoleBrightness"),
                ("对比度", "consoleContrast"),
                ("饱和度", "consoleSaturation"),
                ("锐度", "consoleSharpness"),
            ]
            for name, slider_id in sliders:
                slider = page.locator(f"#{slider_id}")
                log_result("Image", f"{name} Slider", slider.count() > 0)
            
            wb_mode = page.locator("#wbMode")
            log_result("Image", "WB Mode Select", wb_mode.count() > 0)
            
            wb_red = page.locator("#wbRed")
            wb_blue = page.locator("#wbBlue")
            log_result("Image", "WB Red Slider", wb_red.count() > 0)
            log_result("Image", "WB Blue Slider", wb_blue.count() > 0)
            
            dnr_spatial = page.locator("#dnrSpatial")
            dnr_temporal = page.locator("#dnrTemporal")
            log_result("Image", "Spatial NR Slider", dnr_spatial.count() > 0)
            log_result("Image", "Temporal NR Slider", dnr_temporal.count() > 0)
            
            exposure_mode = page.locator("#exposureMode")
            log_result("Image", "Exposure Mode Select", exposure_mode.count() > 0)
            
            shutter = page.locator("#shutterSpeed")
            log_result("Image", "Shutter Select", shutter.count() > 0)
            
            iris = page.locator("#irisLevel")
            log_result("Image", "Iris Select", iris.count() > 0)
            
            gain = page.locator("#gainLevel")
            log_result("Image", "Gain Slider", gain.count() > 0)
            
            info_osd = page.locator("#infoOsdSwitch")
            ptz_osd = page.locator("#ptzOsdSwitch")
            log_result("Image", "Info OSD Switch", info_osd.count() > 0)
            log_result("Image", "PTZ OSD Switch", ptz_osd.count() > 0)
            
            page.screenshot(path="test_results/04_image.png")
            
            # ========== 6. 高级功能 ==========
            print("\n[6. Advanced Features]")
            page.click("[data-page='advanced']")
            time.sleep(1)
            
            test_items = ["功能测试", "限位测试", "速度测试", "推流/存储", "天文校准"]
            for item in test_items:
                btn = page.locator(f".adv-menu-item:has-text('{item}')")
                log_result("Advanced", f"Menu: {item}", btn.count() > 0)
            
            run_btn = page.locator("#btnAdvRun")
            stop_btn = page.locator("#btnAdvStop")
            log_result("Advanced", "Run Button", run_btn.count() > 0)
            log_result("Advanced", "Stop Button", stop_btn.count() > 0)
            
            video_box = page.locator("#advVideoBox")
            log_result("Advanced", "Video Box", video_box.count() > 0)
            
            output = page.locator("#advOutput")
            result = page.locator("#advResult")
            log_result("Advanced", "Output Area", output.count() > 0)
            log_result("Advanced", "Result Area", result.count() > 0)
            
            page.screenshot(path="test_results/05_advanced.png")
            
            # ========== 7. 观测计划 ==========
            print("\n[7. Observation]")
            page.click("[data-page='observation']")
            time.sleep(1)
            
            obs_cards = page.locator(".obs-card")
            log_result("Observation", "Cards", obs_cards.count() > 0)
            
            page.screenshot(path="test_results/06_observation.png")
            
            # ========== 8. 回放 ==========
            print("\n[8. Replay]")
            page.click("[data-page='replay']")
            time.sleep(1)
            page.screenshot(path="test_results/07_replay.png")
            log_result("Replay", "Page Load", True)
            
            # ========== 9. 仪表盘 ==========
            print("\n[9. Dashboard]")
            page.click("[data-page='dashboard']")
            time.sleep(1)
            page.screenshot(path="test_results/08_dashboard.png")
            log_result("Dashboard", "Page Load", True)
            
        except Exception as e:
            print(f"\n[ERROR] {e}")
            page.screenshot(path="test_results/error.png")
            log_result("Error", "Exception", False, str(e))
        
        finally:
            browser.close()
    
    # 汇总
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"[PASS] {len(results['passed'])}")
    print(f"[FAIL] {len(results['failed'])}")
    
    if results["failed"]:
        print("\nFailed:")
        for f in results["failed"]:
            print(f"  - [{f['category']}] {f['test']}: {f['detail']}")
    
    with open("test_results/report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\nScreenshots: test_results/*.png")
    
    return len(results["failed"]) == 0

if __name__ == "__main__":
    sys.exit(0 if main() else 1)