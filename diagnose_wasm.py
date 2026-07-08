# -*- coding: utf-8 -*-
"""
WASM Preview 诊断脚本
捕获浏览器控制台错误和详细 SDK 状态
"""
import asyncio
from playwright.async_api import async_playwright

async def diagnose_wasm():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 捕获控制台消息
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
        
        # 捕获页面错误
        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        
        try:
            # 导航
            print("[1] Navigating to AstroHub...")
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            # 切换到主控台
            print("[2] Switching to console page...")
            await page.evaluate("switchPage('console')")
            await page.wait_for_timeout(1000)
            
            # 检查 SDK 加载
            print("[3] Checking SDK loading...")
            sdk_loaded = await page.evaluate("typeof WebVideoCtrl !== 'undefined'")
            print(f"    WebVideoCtrl loaded: {sdk_loaded}")
            
            if not sdk_loaded:
                print("    ERROR: SDK not loaded!")
                return
            
            # 检查 WASM 模块
            wasm_loaded = await page.evaluate("typeof WasmPlayer !== 'undefined'")
            print(f"    WasmPlayer module: {wasm_loaded}")
            
            # 模拟设备连接
            print("[4] Simulating device connection...")
            await page.evaluate("""
                () => {
                    window.connectedDevice = {
                        ip: '192.168.5.72',
                        port: 80,
                        username: 'admin',
                        password: 'Nftw1357'
                    };
                    onDeviceConnected();
                }
            """)
            
            # 等待 SDK 初始化
            print("[5] Waiting for SDK initialization...")
            await page.wait_for_timeout(3000)
            
            # 检查 SDK 状态
            print("[6] Checking SDK status...")
            sdk_status = await page.evaluate("""
                () => {
                    return {
                        sdkReady: WasmPlayer.sdkReady,
                        loggedIn: WasmPlayer.loggedIn,
                        playing: WasmPlayer.playing,
                        deviceIdentify: WasmPlayer.deviceIdentify,
                        deviceIp: WasmPlayer.deviceIp,
                        devicePort: WasmPlayer.devicePort,
                        rtspPort: WasmPlayer.rtspPort,
                        channel: WasmPlayer.channel,
                        containerId: WasmPlayer.containerId
                    };
                }
            """)
            print(f"    SDK Ready: {sdk_status['sdkReady']}")
            print(f"    Logged In: {sdk_status['loggedIn']}")
            print(f"    Playing: {sdk_status['playing']}")
            print(f"    Device: {sdk_status['deviceIdentify']}")
            print(f"    RTSP Port: {sdk_status['rtspPort']}")
            
            # 检查 divPlugin
            print("[7] Checking divPlugin container...")
            div_info = await page.evaluate("""
                () => {
                    const el = document.getElementById('divPlugin');
                    if (!el) return { error: 'not found' };
                    const rect = el.getBoundingClientRect();
                    return {
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        children: el.children.length,
                        innerHTML: el.innerHTML.substring(0, 500)
                    };
                }
            """)
            print(f"    divPlugin size: {div_info.get('width')}x{div_info.get('height')}")
            print(f"    Children: {div_info.get('children')}")
            
            # 尝试手动开始预览
            print("[8] Manually starting preview...")
            preview_result = await page.evaluate("""
                () => {
                    return new Promise((resolve) => {
                        try {
                            const channel = WasmPlayer.channel || 1;
                            const streamType = 2;
                            const useProxy = true;
                            
                            console.log('[TEST] Starting preview with:', { channel, streamType, useProxy });
                            
                            WebVideoCtrl.I_StartRealPlay(WasmPlayer.deviceIdentify, {
                                iRtspPort: WasmPlayer.rtspPort,
                                iStreamType: streamType,
                                iChannelID: channel,
                                bZeroChannel: false,
                                bProxy: useProxy,
                                success: function() {
                                    console.log('[TEST] Preview started successfully!');
                                    resolve({ success: true });
                                },
                                error: function() {
                                    const args = Array.from(arguments);
                                    console.error('[TEST] Preview failed, args:', args);
                                    console.error('[TEST] Arguments detail:', args.map(a => typeof a));
                                    
                                    // 尝试获取更多错误信息
                                    let errorInfo = { args: [] };
                                    args.forEach((arg, i) => {
                                        if (typeof arg === 'object') {
                                            errorInfo.args.push({ index: i, type: 'object', keys: Object.keys(arg), value: JSON.stringify(arg) });
                                        } else {
                                            errorInfo.args.push({ index: i, type: typeof arg, value: String(arg) });
                                        }
                                    });
                                    
                                    resolve({ success: false, error: errorInfo });
                                }
                            });
                        } catch (e) {
                            console.error('[TEST] Exception:', e);
                            resolve({ success: false, exception: e.toString() });
                        }
                    });
                }
            """)
            
            print(f"    Preview result: {preview_result}")
            
            # 等待更多日志
            await page.wait_for_timeout(3000)
            
            # 输出所有控制台消息
            print("\n[9] Browser Console Messages:")
            for msg in console_messages:
                if 'WASM' in msg or 'TEST' in msg or 'WebVideoCtrl' in msg or 'error' in msg.lower():
                    print(f"    {msg}")
            
            if page_errors:
                print("\n[10] Page Errors:")
                for err in page_errors:
                    print(f"    {err}")
            
            # 截图
            await page.screenshot(path='wasm_diagnose.png', full_page=True)
            print("\n[11] Screenshot saved: wasm_diagnose.png")
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(diagnose_wasm())
