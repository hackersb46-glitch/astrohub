"""v8.10 E2E: Playwright 真实 UI 测试
流程:
  A. 白平衡: 自动(官方) → 验证按钮拦截 → 切手动 → 框选分析
  B. 对焦:   自动 → 验证按钮拦截 → 切手动 → 框选分析
"""
import time
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:10280"
passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}{' - ' + detail if detail else ''}")
    else:
        failed += 1
        print(f"  [FAIL] {name}: {detail}")

def wait_toast(page, keyword, timeout_s=30):
    for i in range(timeout_s * 2):  # 每 0.5s 轮询
        time.sleep(0.5)
        for sel in [".toast.success", ".toast.error", ".toast.warning", ".toast.info"]:
            toast = page.query_selector(sel)
            if toast:
                t = toast.text_content() or ""
                if keyword in t:
                    return True, t
                if "失败" in t or "错误" in t:
                    return False, t
    return False, "timeout"

def run():
    global passed, failed
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("dialog", lambda d: d.accept())

        # ── 1: 打开控制台 ──
        print("\n[1] 打开控制台...")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        time.sleep(2)
        page.click('[data-page="console"]')
        time.sleep(1)
        page.wait_for_selector("#btnConsoleSnapshot", state="visible", timeout=15000)
        check("控制台可见", True)

        # ── 2: 通过设备管理连接设备 ──
        print("\n[2] 连接设备...")
        page.click('[data-page="devices"]')
        time.sleep(1)
        discover = page.query_selector("#btnDiscover")
        if discover:
            discover.click()
            time.sleep(5)
        page.wait_for_selector("#deviceTable tr", timeout=15000)
        switches = page.query_selector_all('#deviceTable input[type="checkbox"]')
        check("设备开关存在", len(switches) > 0, f"{len(switches)} 个")
        if switches and not switches[0].is_checked():
            switches[0].click()
            time.sleep(3)
        page.click('[data-page="console"]')
        time.sleep(2)
        page.wait_for_selector("#btnConsoleSnapshot", state="visible", timeout=10000)
        check("切回控制台", True)

        # ═══════════ A. 白平衡 ═══════════
        print("\n── 白平衡测试 ──")

        # A1: 切白平衡到"自动（官方）"
        print("\n[A1] 切白平衡到自动(官方)...")
        time.sleep(3)  # 等参数加载
        wb = page.query_selector("#wbMode")
        check("wbMode下拉存在", wb is not None)
        if wb:
            page.select_option("#wbMode", "auto_official")
            time.sleep(2)
            current = wb.input_value()
            check("切到自动(官方)", current == "auto_official", f"实际={current}")

        # A2: 自动模式下点击白平衡按钮应被拦截
        print("\n[A2] 自动模式点击白平衡按钮...")
        # 监听 toast 创建
        toast_captured = []
        page.evaluate("""() => {
            window._capturedToast = null;
            var obs = new MutationObserver(function(muts) {
                muts.forEach(function(m) {
                    m.addedNodes.forEach(function(n) {
                        if (n.classList && (n.classList.contains('toast') || n.classList.contains('warning'))) {
                            window._capturedToast = n.textContent;
                        }
                    });
                });
            });
            var c = document.getElementById('toastContainer');
            if (c) obs.observe(c, { childList: true });
        }""")
        page.click("#btnRegionWB")
        time.sleep(1.5)
        captured = page.evaluate("() => window._capturedToast || ''")
        overlay_vis = page.evaluate("""() => {
            var el = document.getElementById('regionOverlay');
            return el ? window.getComputedStyle(el).display : 'none';
        }""")
        check("overlay未显示(自动模式拦截)", overlay_vis == "none",
              f"display={overlay_vis}")
        check("拦截toast提示", "手动" in captured or "切换" in captured,
              f"toast='{captured[:60]}'")

        # A3: 切到手动模式
        print("\n[A3] 切白平衡到手動...")
        page.select_option("#wbMode", "manual")
        ok, msg = wait_toast(page, "白平衡", 5)
        check("手动切换成功", ok, msg[:60])

        # A4: 框选白平衡分析
        print("\n[A4] 框选白平衡分析...")
        page.click("#btnRegionWB")
        time.sleep(1)
        overlay_vis = page.evaluate("""() => {
            var el = document.getElementById('regionOverlay');
            return el ? window.getComputedStyle(el).display : 'none';
        }""")
        check("overlay显示(手动模式)", overlay_vis == "block", f"display={overlay_vis}")

        # 拖拽框选
        overlay_box = page.query_selector("#regionOverlay").bounding_box()
        if overlay_box and overlay_box["width"] > 100:
            cx = overlay_box["x"] + overlay_box["width"] / 2
            cy = overlay_box["y"] + overlay_box["height"] / 2
            # 200x200 框
            page.mouse.move(cx - 100, cy - 100)
            page.mouse.down()
            page.mouse.move(cx + 100, cy - 100, steps=3)
            page.mouse.move(cx + 100, cy + 100, steps=3)
            page.mouse.up()
            time.sleep(0.5)
        else:
            check("overlay尺寸有效", False, f"box={overlay_box}")

        ok, msg = wait_toast(page, "白平衡", 15)
        check("白平衡分析完成", ok, msg[:80])

        # ═══════════ B. 对焦 ═══════════
        print("\n── 对焦测试 ──")

        # B1: 切对焦到自动
        print("\n[B1] 切对焦到自动...")
        fm = page.query_selector("#focusMode")
        check("focusMode下拉存在", fm is not None)
        if fm:
            page.select_option("#focusMode", "auto")
            time.sleep(5)  # 等 toast 完全消失 (3.7s show + fade)
            current = fm.input_value()
            check("切到自动", current == "auto", f"实际={current}")

        # B2: 自动模式点击对焦按钮应被拦截
        print("\n[B2] 自动模式点击对焦按钮...")
        # 先清除B1的toast状态
        page.evaluate("() => { window._capturedToast = null; }")
        time.sleep(0.5)
        page.evaluate("""() => {
            window._capturedToast = null;
            var obs = new MutationObserver(function(muts) {
                muts.forEach(function(m) {
                    m.addedNodes.forEach(function(n) {
                        if (n.classList && (n.classList.contains('toast') || n.classList.contains('warning'))) {
                            window._capturedToast = n.textContent;
                        }
                    });
                });
            });
            var c = document.getElementById('toastContainer');
            if (c) obs.observe(c, { childList: true });
        }""")
        page.click("#btnRegionAF")
        time.sleep(1.5)
        captured = page.evaluate("() => window._capturedToast || ''")
        overlay_vis = page.evaluate("""() => {
            var el = document.getElementById('regionOverlay');
            return el ? window.getComputedStyle(el).display : 'none';
        }""")
        check("overlay未显示(自动模式拦截)", overlay_vis == "none",
              f"display={overlay_vis}")
        check("拦截toast提示", "手动" in captured or "切换" in captured,
              f"toast='{captured[:60]}'")

        # B3: 半自动模式也应拦截
        print("\n[B3] 半自动模式也应拦截...")
        page.evaluate("() => { window._capturedToast = null; }")
        time.sleep(0.5)
        page.select_option("#focusMode", "semiauto")
        time.sleep(2)  # 等 B2 残留 toast 消失
        page.evaluate("""() => {
            window._capturedToast = null;
            var obs = new MutationObserver(function(muts) {
                muts.forEach(function(m) {
                    m.addedNodes.forEach(function(n) {
                        if (n.classList && n.classList.contains('toast'))
                            window._capturedToast = n.textContent;
                    });
                });
            });
            var c = document.getElementById('toastContainer');
            if (c) obs.observe(c, { childList: true });
        }""")
        page.click("#btnRegionAF")
        time.sleep(1.5)
        overlay_vis = page.evaluate("""() => {
            var el = document.getElementById('regionOverlay');
            return el ? window.getComputedStyle(el).display : 'none';
        }""")
        check("半自动也拦截", overlay_vis == "none", f"display={overlay_vis}")

        # B4: 切到手动
        print("\n[B4] 切对焦到手動...")
        page.select_option("#focusMode", "manual")
        ok, msg = wait_toast(page, "对焦", 5)
        check("手动切换成功", ok, msg[:60])

        # B5: 框选对焦分析
        print("\n[B5] 框选反差对焦...")
        page.click("#btnRegionAF")
        time.sleep(1)
        overlay_vis = page.evaluate("""() => {
            var el = document.getElementById('regionOverlay');
            return el ? window.getComputedStyle(el).display : 'none';
        }""")
        check("overlay显示(手动模式)", overlay_vis == "block")

        if overlay_box and overlay_box["width"] > 100:
            page.mouse.move(cx - 100, cy - 100)
            page.mouse.down()
            page.mouse.move(cx + 100, cy - 100, steps=3)
            page.mouse.move(cx + 100, cy + 100, steps=3)
            page.mouse.up()
            time.sleep(0.5)

        ok, msg = wait_toast(page, "对焦完成", 60)
        check("对焦分析完成", ok, msg[:80])

        # ── 汇总 ──
        total = passed + failed
        print(f"\n{'='*60}")
        print(f"  {passed} PASS / {failed} FAIL / {total} TOTAL")
        print(f"  {'ALL PASS' if failed == 0 else 'FAILURES DETECTED'}")
        print(f"{'='*60}")
        time.sleep(2)
        browser.close()

if __name__ == "__main__":
    run()
