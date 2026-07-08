import asyncio
from playwright.async_api import async_playwright

async def check_sdk_internal():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1400, 'height': 900})
        
        try:
            await page.goto('http://localhost:10280/', wait_until='networkidle')
            await page.wait_for_timeout(3000)
            
            # 检查 SDK 内部状态
            sdk_internal = await page.evaluate("""
                () => {
                    // 访问 SDK 内部变量
                    const opts = WebVideoCtrl.w_options || {};
                    
                    // 检查 q() 函数的返回值
                    let q_result = false;
                    try {
                        // q() 检查 bNoPlugin 和浏览器版本
                        if (opts.bNoPlugin) {
                            const ua = navigator.userAgent;
                            const chromeMatch = ua.match(/Chrome\\/(\\d+)/);
                            q_result = chromeMatch && parseInt(chromeMatch[1]) > 90;
                        }
                    } catch(e) {
                        q_result = false;
                    }
                    
                    return {
                        proxyAddress: opts.proxyAddress,
                        proxyAddressPortType: typeof opts.proxyAddress?.port,
                        bNoPlugin: opts.bNoPlugin,
                        q_result: q_result,
                        shouldUseProxy: !!(opts.proxyAddress && q_result),
                        userAgent: navigator.userAgent.substring(0, 100)
                    };
                }
            """)
            
            print("=== SDK 内部状态 ===")
            print(f"proxyAddress: {sdk_internal['proxyAddress']}")
            print(f"proxyAddress.port 类型: {sdk_internal['proxyAddressPortType']}")
            print(f"bNoPlugin: {sdk_internal['bNoPlugin']}")
            print(f"q() 返回值: {sdk_internal['q_result']}")
            print(f"应该使用代理: {sdk_internal['shouldUseProxy']}")
            print(f"User-Agent: {sdk_internal['userAgent']}")
            
            await browser.close()
            
        except Exception as e:
            print(f"Error: {e}")
            await browser.close()

if __name__ == '__main__':
    asyncio.run(check_sdk_internal())
