"""Playwright - 精确分析主控台黑色框体的层级结构"""
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
        
        # 精确分析层级结构
        result = await page.evaluate("""() => {
            let divPlugin = document.getElementById('divPlugin');
            let mseVideo = document.getElementById('mseVideo');
            let videoWrap = divPlugin ? divPlugin.parentElement : null;
            let consoleCenter = videoWrap ? videoWrap.parentElement : null;
            
            function getBox(el) {
                if (!el) return null;
                let r = el.getBoundingClientRect();
                let s = window.getComputedStyle(el);
                return {
                    tag: el.tagName,
                    id: el.id || '',
                    className: el.className || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    display: s.display,
                    position: s.position,
                    overflow: s.overflow,
                    background: s.background.substring(0, 50),
                    border: s.border,
                    margin: s.margin,
                    padding: s.padding,
                    aspectRatio: s.aspectRatio,
                    maxWidth: s.maxWidth,
                };
            }
            
            // divPlugin 的子元素层级
            let divPluginChildren = [];
            if (divPlugin) {
                for (let i = 0; i < divPlugin.children.length; i++) {
                    let child = divPlugin.children[i];
                    let childInfo = getBox(child);
                    childInfo.childCount = child.children.length;
                    // 再深入一层
                    let grandChildren = [];
                    for (let j = 0; j < child.children.length; j++) {
                        let gc = child.children[j];
                        let gcInfo = getBox(gc);
                        gcInfo.childCount = gc.children.length;
                        // 再深入一层
                        let ggChildren = [];
                        for (let k = 0; k < gc.children.length; k++) {
                            let ggc = gc.children[k];
                            let ggcInfo = getBox(ggc);
                            ggcInfo.childCount = ggc.children.length;
                            ggChildren.push(ggcInfo);
                        }
                        gcInfo.children = ggChildren;
                        grandChildren.push(gcInfo);
                    }
                    childInfo.children = grandChildren;
                    divPluginChildren.push(childInfo);
                }
            }
            
            return {
                // 从外到内的层级
                layer1_consoleCenter: getBox(consoleCenter),
                layer2_videoWrap: getBox(videoWrap),
                layer3a_divPlugin: getBox(divPlugin),
                layer3b_mseVideo: getBox(mseVideo),
                // divPlugin 内部层级
                divPluginChildren: divPluginChildren,
                // divPlugin innerHTML 前500字符
                divPluginHTML: divPlugin ? divPlugin.innerHTML.substring(0, 500) : '',
            }
        }""")
        
        print("=" * 60)
        print("主控台黑色框体层级结构分析")
        print("=" * 60)
        
        for key in ['layer1_consoleCenter', 'layer2_videoWrap', 'layer3a_divPlugin', 'layer3b_mseVideo']:
            info = result[key]
            if info:
                print(f"\n--- {key} ---")
                print(f"  tag: {info['tag']}, id: {info['id']}, class: {info['className']}")
                print(f"  位置: x={info['x']}, y={info['y']}, w={info['w']}, h={info['h']}")
                print(f"  display: {info['display']}, position: {info['position']}")
                print(f"  background: {info['background']}")
                print(f"  border: {info['border']}")
                print(f"  margin: {info['margin']}, padding: {info['padding']}")
                print(f"  maxWidth: {info['maxWidth']}, aspectRatio: {info['aspectRatio']}")
        
        print(f"\n--- divPlugin 子元素 ---")
        for i, child in enumerate(result['divPluginChildren']):
            print(f"\n  [子{i}] tag={child['tag']}, id={child['id']}, class={child['className']}")
            print(f"    位置: x={child['x']}, y={child['y']}, w={child['w']}, h={child['h']}")
            print(f"    display={child['display']}, position={child['position']}, overflow={child['overflow']}")
            if 'children' in child:
                for j, gc in enumerate(child['children']):
                    print(f"    [孙{j}] tag={gc['tag']}, id={gc['id']}, class={gc['className']}")
                    print(f"      位置: x={gc['x']}, y={gc['y']}, w={gc['w']}, h={gc['h']}")
                    if 'children' in gc:
                        for k, ggc in enumerate(gc['children']):
                            print(f"      [曾孙{k}] tag={ggc['tag']}, id={ggc['id']}, class={ggc['className']}")
                            print(f"        位置: x={ggc['x']}, y={ggc['y']}, w={ggc['w']}, h={ggc['h']}")
        
        print(f"\n--- divPlugin innerHTML (前500字符) ---")
        print(result['divPluginHTML'])
        
        # 截图
        await page.screenshot(path="debug_layers.png", full_page=False)
        print("\n截图已保存: debug_layers.png")
        
        await browser.close()

asyncio.run(main())
