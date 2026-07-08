"""检查WASM框体居中对齐"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1600, "height": 900})
        await page.goto("http://localhost:10280/", timeout=30000)
        await asyncio.sleep(5)
        
        # 切换到主控台
        console_btn = page.locator('[data-page="console"]')
        if await console_btn.count() > 0:
            await console_btn.click()
            await asyncio.sleep(2)
        
        result = await page.evaluate("""() => {
            let dp = document.getElementById('divPlugin');
            let wrap = dp ? dp.parentElement : null;
            let center = wrap ? wrap.parentElement : null;
            
            let dpR = dp ? dp.getBoundingClientRect() : null;
            let wrapR = wrap ? wrap.getBoundingClientRect() : null;
            let centerR = center ? center.getBoundingClientRect() : null;
            
            // 检查是否有 mseVideo 残留
            let mseVideo = document.getElementById('mseVideo');
            
            return {
                // 居中检查：divPlugin 是否在 videoWrap 中水平居中
                divPlugin_x: dpR ? dpR.x : null,
                divPlugin_w: dpR ? dpR.width : null,
                videoWrap_x: wrapR ? wrapR.x : null,
                videoWrap_w: wrapR ? wrapR.width : null,
                center_x: centerR ? centerR.x : null,
                center_w: centerR ? centerR.width : null,
                // divPlugin 相对于 videoWrap 的偏移
                offset_in_wrap: dpR && wrapR ? dpR.x - wrapR.x : null,
                // divPlugin 宽度 vs videoWrap 宽度
                width_diff: dpR && wrapR ? wrapR.width - dpR.width : null,
                // 是否居中（左右间距相等）
                is_centered: dpR && wrapR ? Math.abs((dpR.x - wrapR.x) - (wrapR.right - dpR.right)) < 2 : null,
                // divPlugin 样式
                dp_style_margin: dp ? window.getComputedStyle(dp).margin : null,
                dp_style_maxWidth: dp ? window.getComputedStyle(dp).maxWidth : null,
                dp_style_aspectRatio: dp ? window.getComputedStyle(dp).aspectRatio : null,
                // MSE 是否存在
                mse_exists: !!mseVideo,
                // divPlugin 内部播放器窗口
                player0: dp ? (dp.querySelector('[id*="player-container-0"]') ? dp.querySelector('[id*="player-container-0"]').getBoundingClientRect() : null) : null,
            }
        }""")
        
        print("=== WASM 框体居中检查 ===")
        print(f"divPlugin: x={result['divPlugin_x']}, w={result['divPlugin_w']}")
        print(f"videoWrap: x={result['videoWrap_x']}, w={result['videoWrap_w']}")
        print(f"console-center: x={result['center_x']}, w={result['center_w']}")
        print(f"divPlugin在wrap中偏移: {result['offset_in_wrap']}")
        print(f"宽度差(wrap-dp): {result['width_diff']}")
        print(f"是否居中: {result['is_centered']}")
        print(f"divPlugin margin: {result['dp_style_margin']}")
        print(f"divPlugin maxWidth: {result['dp_style_maxWidth']}")
        print(f"divPlugin aspectRatio: {result['dp_style_aspectRatio']}")
        print(f"MSE元素存在: {result['mse_exists']}")
        if result['player0']:
            p0 = result['player0']
            print(f"播放器窗口0: x={p0['x']}, y={p0['y']}, w={p0['width']}, h={p0['height']}")
        
        await page.screenshot(path="debug_centered.png", full_page=False)
        print("\n截图: debug_centered.png")
        
        await browser.close()

asyncio.run(main())
