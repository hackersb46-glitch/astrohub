"""Playwright screenshot - navigate to console tab"""
from playwright.sync_api import sync_playwright
import time

url = "http://127.0.0.1:10280/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    
    print(f"Visiting: {url}")
    page.goto(url, wait_until="networkidle")
    time.sleep(2)
    
    # Click console tab (主控台)
    console_tab = page.query_selector("text=主控台")
    if console_tab:
        console_tab.click()
        print("[OK] Clicked console tab")
        time.sleep(3)
    else:
        print("[WARN] Console tab not found, trying alt selector")
        # Try finding by nav link
        nav = page.query_selector("nav a:nth-child(3)")
        if nav:
            nav.click()
            time.sleep(3)
    
    # Screenshot console page
    page.screenshot(path="console_v848_page.png", full_page=True)
    print("[OK] Saved: console_v848_page.png")
    
    # Feature checks on console page
    checks = [
        ("slowShutterSelect", "Slow shutter select"),
        ("infoOsdSwitch", "Info OSD switch"),
        ("ptzOsdSwitch", "PTZ OSD switch"),
    ]
    
    print("\nConsole page features:")
    for elem_id, desc in checks:
        elem = page.query_selector(f"#{elem_id}")
        status = "[OK]" if elem else "[FAIL]"
        print(f"  {status} {desc}")
    
    # Check if "信息显示" section exists (backup_20260705_205538 layout)
    info_section = page.query_selector("text=信息显示")
    status = "[OK]" if info_section else "[FAIL]"
    print(f"  {status} Info display section")
    
    # Check if "慢快门" label exists
    ss_label = page.query_selector("text=慢快门")
    status = "[OK]" if ss_label else "[FAIL]"
    print(f"  {status} Slow shutter label")
    
    browser.close()
    print("\n[OK] Done")
