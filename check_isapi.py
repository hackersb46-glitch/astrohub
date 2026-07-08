import asyncio
from playwright.async_api import async_playwright

async def check_isapi_status():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        
        try:
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(3000)
            
            # 检查 ISAPI 登录状态
            isapi_status = await page.evaluate("""
                () => {
                    // 检查全局变量
                    return {
                        connectedDevice: window.connectedDevice || null,
                        deviceManager: window.deviceManager ? {
                            hasDevices: window.deviceManager.devices && window.deviceManager.devices.length > 0,
                            deviceCount: window.deviceManager.devices ? window.deviceManager.devices.length : 0
                        } : null,
                        isapiSession: window.isapiSession || null
                    };
                }
            """)
            print("=== ISAPI 状态 ===")
            print(f"connectedDevice: {isapi_status.get('connectedDevice')}")
            print(f"deviceManager: {isapi_status.get('deviceManager')}")
            print(f"isapiSession: {isapi_status.get('isapiSession')}")
            
            # 检查后端 API
            api_status = await page.evaluate("""
                async () => {
                    try {
                        const resp = await fetch('/api/v1/devices');
                        const data = await resp.json();
                        return {
                            success: true,
                            deviceCount: data.length,
                            devices: data.map(d => ({ip: d.ip, port: d.port, connected: d.connected}))
                        };
                    } catch (e) {
                        return {success: false, error: e.message};
                    }
                }
            """)
            print("\n=== 后端设备状态 ===")
            print(f"API 状态: {api_status}")
            
            # 检查 WASM SDK 状态
            wasm_status = await page.evaluate("""
                () => {
                    return {
                        sdkReady: typeof WebVideoCtrl !== 'undefined',
                        pluginReady: WasmPlayer ? WasmPlayer.sdkReady : false,
                        loggedIn: WasmPlayer ? WasmPlayer.loggedIn : false,
                        playing: WasmPlayer ? WasmPlayer.playing : false
                    };
                }
            """)
            print("\n=== WASM SDK 状态 ===")
            print(f"SDK 加载: {wasm_status.get('sdkReady')}")
            print(f"插件就绪: {wasm_status.get('pluginReady')}")
            print(f"已登录: {wasm_status.get('loggedIn')}")
            print(f"正在播放: {wasm_status.get('playing')}")
            
            await browser.close()
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
            await browser.close()

asyncio.run(check_isapi_status())
