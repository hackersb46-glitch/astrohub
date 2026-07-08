import asyncio
from playwright.async_api import async_playwright

async def intercept_sdk():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        
        try:
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(2000)
            
            # 拦截 SDK 内部方法
            intercepted = await page.evaluate("""
                () => {
                    const logs = [];
                    
                    // 拦截 JS_StartRealPlay
                    if (window.WebVideoCtrl && window.WebVideoCtrl.w_plugin) {
                        const origStart = window.WebVideoCtrl.w_plugin.JS_StartRealPlay;
                        if (origStart) {
                            window.WebVideoCtrl.w_plugin.JS_StartRealPlay = function(...args) {
                                logs.push('JS_StartRealPlay args: ' + JSON.stringify(args));
                                return origStart.apply(this, args);
                            };
                        }
                    }
                    
                    // 检查 SDK 构建的 URL
                    const opts = window.WebVideoCtrl?.w_options || {};
                    logs.push('proxyAddress: ' + JSON.stringify(opts.proxyAddress));
                    logs.push('bNoPlugin: ' + opts.bNoPlugin);
                    
                    return logs;
                }
            """)
            
            print("=== SDK 拦截 ===")
            for log in intercepted:
                print(log)
            
            # 切换到主控台并触发预览
            await page.evaluate("switchPage('console')")
            await page.wait_for_timeout(1000)
            
            await page.evaluate("""
                () => {
                    window.connectedDevice = {ip:'192.168.5.72', port:80, username:'admin', password:'Nftw1357'};
                }
            """)
            await page.wait_for_timeout(2000)
            
            await page.evaluate("""
                () => {
                    var channel = WasmPlayer.channel || 1;
                    var streamType = 2;
                    wasmStartRealPlay(channel, streamType, true);
                }
            """)
            await page.wait_for_timeout(3000)
            
            # 获取拦截的日志
            final_logs = await page.evaluate("window.__intercepted_logs || []")
            print("\n=== 预览后的日志 ===")
            for log in final_logs:
                print(log)
            
            await browser.close()
            
        except Exception as e:
            print(f"Error: {e}")
            await browser.close()

if __name__ == '__main__':
    asyncio.run(intercept_sdk())
