"""
E2E WASM Test using Playwright
Tests WASM plugin loading and rendering
"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

async def run_e2e_test():
    results = {
        "success": False,
        "wasm_loaded": False,
        "divPlugin_found": False,
        "errors": [],
        "console_logs": [],
        "wasm_logs": []
    }
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        # Collect console logs
        def handle_console(msg):
            log_text = f"[{msg.type}] {msg.text}"
            results["console_logs"].append(log_text)
            if "[WASM]" in msg.text:
                results["wasm_logs"].append(log_text)
                if "loaded" in msg.text.lower() or "success" in msg.text.lower():
                    results["wasm_loaded"] = True
        
        page.on("console", handle_console)
        
        # Collect page errors
        def handle_error(error):
            results["errors"].append(str(error))
        
        page.on("pageerror", handle_error)
        
        try:
            # Step 1: Visit localhost:8000
            print("[1/9] 访问 http://localhost:8000...")
            await page.goto("http://localhost:8000", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
            print("✓ 页面加载完成")
            
            # Step 2: Switch to device management page
            print("[2/9] 切换到设备管理页面...")
            # Try to find device management link/button
            device_mgmt_selectors = [
                'text=设备管理',
                'text=Device Management',
                '[href*="device"]',
                'button:has-text("设备")',
                'a:has-text("设备")',
                '.nav-item:has-text("设备")',
                '[data-page="device"]'
            ]
            
            device_page_found = False
            for selector in device_mgmt_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.is_visible(timeout=2000):
                        await element.click()
                        device_page_found = True
                        print(f"✓ 找到并点击设备管理: {selector}")
                        break
                except:
                    continue
            
            if not device_page_found:
                print("⚠ 未找到设备管理页面入口，检查当前页面...")
            
            await page.wait_for_timeout(2000)
            
            # Step 3: Check if devices exist
            print("[3/9] 检查设备列表...")
            device_selectors = [
                '.device-item',
                '.device-card',
                '[class*="device"]',
                'table tbody tr',
                '.device-list > *'
            ]
            
            devices_found = False
            for selector in device_selectors:
                try:
                    devices = page.locator(selector)
                    count = await devices.count()
                    if count > 0:
                        devices_found = True
                        print(f"✓ 发现 {count} 个设备")
                        break
                except:
                    continue
            
            # Step 4: If no devices, click discover button
            if not devices_found:
                print("[4/9] 未发现设备，点击发现设备按钮...")
                discover_selectors = [
                    'text=发现设备',
                    'text=Discover',
                    'text=扫描',
                    'text=Scan',
                    'button:has-text("发现")',
                    'button:has-text("扫描")',
                    '.btn-discover',
                    '[data-action="discover"]'
                ]
                
                for selector in discover_selectors:
                    try:
                        element = page.locator(selector).first
                        if await element.is_visible(timeout=2000):
                            await element.click()
                            print(f"✓ 点击发现设备按钮: {selector}")
                            # Wait for discovery to complete
                            await page.wait_for_timeout(5000)
                            break
                    except:
                        continue
            else:
                print("[4/9] 设备已存在，跳过发现步骤")
            
            # Step 5: Connect to device 192.168.5.72
            print("[5/9] 连接设备 192.168.5.72...")
            # Look for the device with IP 192.168.5.72
            device_ip_selectors = [
                f'text=192.168.5.72',
                f'[data-ip="192.168.5.72"]',
                f'tr:has-text("192.168.5.72")',
                f'.device:has-text("192.168.5.72")'
            ]
            
            device_connected = False
            for selector in device_ip_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.is_visible(timeout=2000):
                        # Try to find connect button near this device
                        connect_btn = element.locator('xpath=..').locator('button:has-text("连接"), button:has-text("Connect"), .btn-connect').first
                        if await connect_btn.is_visible(timeout=1000):
                            await connect_btn.click()
                            device_connected = True
                            print(f"✓ 点击连接按钮")
                            await page.wait_for_timeout(3000)
                            break
                        else:
                            # Maybe clicking the device itself connects it
                            await element.click()
                            device_connected = True
                            print(f"✓ 点击设备")
                            await page.wait_for_timeout(3000)
                            break
                except:
                    continue
            
            if not device_connected:
                print("⚠ 未能连接到设备，继续测试...")
            
            # Step 6: Switch to main console page
            print("[6/9] 切换到主控台页面...")
            console_selectors = [
                'text=主控台',
                'text=Console',
                'text=控制台',
                '[href*="console"]',
                'button:has-text("主控")',
                'a:has-text("主控")',
                '.nav-item:has-text("主控")',
                '[data-page="console"]'
            ]
            
            for selector in console_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.is_visible(timeout=2000):
                        await element.click()
                        print(f"✓ 切换到主控台: {selector}")
                        break
                except:
                    continue
            
            await page.wait_for_timeout(3000)
            
            # Step 7: Check WASM rendering (divPlugin element)
            print("[7/9] 检查 WASM 框体渲染...")
            wasm_selectors = [
                '#divPlugin',
                'divPlugin',
                '[id*="plugin"]',
                '[class*="plugin"]',
                '.wasm-container',
                '#wasm-plugin'
            ]
            
            for selector in wasm_selectors:
                try:
                    element = page.locator(selector).first
                    if await element.is_visible(timeout=5000):
                        results["divPlugin_found"] = True
                        print(f"✓ 找到 WASM 容器: {selector}")
                        
                        # Check if it has content (not empty)
                        box = await element.bounding_box()
                        if box and box['width'] > 0 and box['height'] > 0:
                            print(f"✓ WASM 容器尺寸: {box['width']}x{box['height']}")
                        break
                except:
                    continue
            
            if not results["divPlugin_found"]:
                print("⚠ 未找到 WASM 容器元素")
            
            # Step 8: Take screenshot
            print("[8/9] 保存截图...")
            screenshot_path = Path("C:/Users/admin/.openclaw/agents/dev-factory/astrohub/data/reports/e2e_wasm_test.png")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"✓ 截图已保存: {screenshot_path}")
            
            # Step 9: Compile results
            print("[9/9] 生成测试报告...")
            
            # Determine success
            if results["divPlugin_found"] and len(results["errors"]) == 0:
                results["success"] = True
            
            print("\n" + "="*60)
            print("E2E 测试结果")
            print("="*60)
            print(f"测试成功: {'✓' if results['success'] else '✗'}")
            print(f"WASM 加载: {'✓' if results['wasm_loaded'] else '✗'}")
            print(f"divPlugin 元素: {'✓' if results['divPlugin_found'] else '✗'}")
            print(f"页面错误数: {len(results['errors'])}")
            print(f"Console 日志数: {len(results['console_logs'])}")
            print(f"WASM 日志数: {len(results['wasm_logs'])}")
            
            if results['errors']:
                print("\n错误列表:")
                for err in results['errors'][:5]:  # Show first 5 errors
                    print(f"  - {err[:200]}")
            
            if results['wasm_logs']:
                print("\nWASM 相关日志:")
                for log in results['wasm_logs'][:10]:  # Show first 10 WASM logs
                    print(f"  {log}")
            
            print("="*60)
            
        except Exception as e:
            print(f"✗ 测试执行失败: {e}")
            results["errors"].append(str(e))
            
            # Try to take screenshot even on error
            try:
                screenshot_path = Path("C:/Users/admin/.openclaw/agents/dev-factory/astrohub/data/reports/e2e_wasm_test_error.png")
                await page.screenshot(path=str(screenshot_path))
                print(f"错误截图已保存: {screenshot_path}")
            except:
                pass
        
        finally:
            await browser.close()
    
    return results

if __name__ == "__main__":
    results = asyncio.run(run_e2e_test())
    
    # Exit with appropriate code
    if results["success"]:
        print("\n✓ E2E 测试通过")
        exit(0)
    else:
        print("\n✗ E2E 测试失败")
        exit(1)
