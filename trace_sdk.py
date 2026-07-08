import asyncio
from playwright.async_api import async_playwright

async def trace_sdk():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        
        try:
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(3000)
            
            # 在 SDK 调用 startRealPlay 之前，拦截关键函数
            await page.evaluate("""
                () => {
                    // 拦截 JS_Play，看传给 WASM 的 URL 是什么
                    window.__playUrls = [];
                    if (window.WebVideoCtrl && window.WebVideoCtrl.w_plugin) {
                        var origPlay = window.WebVideoCtrl.w_plugin.JS_Play;
                        if (origPlay) {
                            window.WebVideoCtrl.w_plugin.JS_Play = function(url) {
                                window.__playUrls.push(url);
                                console.log('[INTERCEPT] JS_Play URL: ' + url);
                                return origPlay.apply(this, arguments);
                            };
                        }
                    }
                }
            """)
            
            # 连接设备
            await page.evaluate("switchPage('console')")
            await page.wait_for_timeout(1000)
            await page.evaluate("""
                () => {
                    window.connectedDevice = {ip:'192.168.5.72', port:80, username:'admin', password:'Nftw1357'};
                }
            """)
            await page.wait_for_timeout(2000)
            
            # 手动触发预览
            await page.evaluate("""
                () => {
                    var channel = WasmPlayer.channel || 1;
                    var streamType = parseInt(document.getElementById('streamType').value, 10) || 2;
                    wasmStartRealPlay(channel, streamType, true);
                }
            """)
            await page.wait_for_timeout(3000)
            
            # 获取拦截的 URL
            urls = await page.evaluate("window.__playUrls || []")
            print(f"=== JS_Play URLs ({len(urls)}) ===")
            for url in urls:
                print(f"  {url}")
            
            # 同时检查 cookie
            cookies = await page.evaluate("""
                () => {
                    return document.cookie;
                }
            """)
            print(f"\n=== Cookies ===")
            print(f"  {cookies}")
            
            await browser.close()
        except Exception as e:
            print(f"Error: {e}")
            await browser.close()

asyncio.run(trace_sdk())
