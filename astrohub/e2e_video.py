"""E2E WASM Video Test - check if video is actually playing"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
import json

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        # Clear cache
        await context.clear_cookies()
        page = await context.new_page()
        
        all_logs = []
        wasm_logs = []
        errors = []
        
        def on_console(msg):
            text = msg.text
            all_logs.append(text)
            if "[WASM]" in text or "[CLICKLOGIN2]" in text or "播放" in text or "登录" in text:
                wasm_logs.append(text)
        
        page.on("console", on_console)
        page.on("pageerror", lambda err: errors.append(str(err)))
        
        try:
            print("1. Loading page...")
            await page.goto("http://localhost:10280", timeout=30000)
            await page.wait_for_timeout(2000)
            
            print("2. Clicking console page...")
            console_btn = page.locator('[data-page="console"]')
            if await console_btn.count() > 0:
                await console_btn.first.click()
            
            print("3. Waiting for WASM to initialize (10 seconds)...")
            await page.wait_for_timeout(10000)
            
            print("4. Checking WASM state...")
            
            # Check divPlugin
            divPlugin = page.locator('#divPlugin')
            count = await divPlugin.count()
            inner_html = ""
            if count > 0:
                inner_html = await divPlugin.first.evaluate('el => el.innerHTML')
            
            # Check WASM status indicator
            wasm_dot = page.locator('#wasmDot')
            wasm_status = page.locator('#wasmStatus')
            wasm_dot_class = ""
            wasm_status_text = ""
            if await wasm_dot.count() > 0:
                wasm_dot_class = await wasm_dot.first.evaluate('el => el.className')
            if await wasm_status.count() > 0:
                wasm_status_text = await wasm_status.first.evaluate('el => el.textContent')
            
            # Check ptz log box for WASM logs
            ptz_log = page.locator('#ptzLogBox')
            ptz_log_content = ""
            if await ptz_log.count() > 0:
                ptz_log_content = await ptz_log.first.evaluate('el => el.innerHTML')
            
            # Screenshot
            screenshot_path = Path("C:/Users/admin/.openclaw/agents/dev-factory/astrohub/data/reports/e2e_wasm_video.png")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=True)
            
            # Results
            print("\n" + "="*60)
            print("WASM VIDEO TEST RESULTS")
            print("="*60)
            print(f"divPlugin innerHTML length: {len(inner_html)}")
            print(f"WASM status dot class: {wasm_dot_class}")
            print(f"WASM status text: {wasm_status_text}")
            print(f"PTZ log content (first 500): {ptz_log_content[:500]}")
            print(f"\nWASM/Login logs ({len(wasm_logs)} total):")
            for log in wasm_logs[:30]:
                print(f"  {log}")
            print(f"\nErrors ({len(errors)} total):")
            for err in errors[:5]:
                print(f"  {err[:200]}")
            
            # Save full logs
            log_path = Path("C:/Users/admin/.openclaw/agents/dev-factory/astrohub/data/reports/e2e_logs.json")
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'wasm_logs': wasm_logs,
                    'errors': errors,
                    'all_logs': all_logs[:100]
                }, f, indent=2, ensure_ascii=False)
            print(f"\nFull logs saved to: {log_path}")
            
            # Check for video playing indicators
            video_playing = False
            if "播放成功" in ptz_log_content or "播放中" in wasm_status_text or "playing" in wasm_status_text.lower():
                video_playing = True
            
            print(f"\nVideo playing detected: {video_playing}")
            print("="*60)
            
        except Exception as e:
            print(f"Test failed: {e}")
            import traceback
            traceback.print_exc()
        
        await browser.close()

asyncio.run(run_test())