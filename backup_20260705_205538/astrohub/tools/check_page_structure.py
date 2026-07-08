from playwright.async_api import async_playwright
import asyncio

async def check_page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('http://127.0.0.1:10280')
        await page.wait_for_load_state('networkidle')
        
        # Check navigation structure
        nav_html = await page.evaluate("""() => {
            var nav = document.querySelector('nav, .nav, .sidebar, .top-nav, .main-nav');
            if (nav) return nav.innerHTML.substring(0, 2000);
            var buttons = document.querySelectorAll('button, a, li');
            var result = [];
            for (var i = 0; i < Math.min(30, buttons.length); i++) {
                result.push(buttons[i].outerHTML.substring(0, 200));
            }
            return result.join('\\n');
        }""")
        
        print("=== Navigation Structure ===")
        print(nav_html[:3000])
        
        await browser.close()

asyncio.run(check_page())
