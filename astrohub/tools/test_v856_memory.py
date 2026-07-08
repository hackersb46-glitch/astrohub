# -*- coding: utf-8 -*-
"""
v8.56 内存泄漏端到端测试

流程：启动程序→进入主控台→录像5秒→回放→回到主控台
全程监控 Python 进程内存，生成报告
"""
import sys, io, time, json, asyncio, os
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_URL = "http://localhost:10280"
DEVICE_ID = "240f9b764193"
SAMPLE_INTERVAL = 1.0  # 每秒采样一次内存

# 内存采样数据
memory_samples = []
phase_markers = []  # [(timestamp, phase_name)]

def get_python_memory():
    """获取 Python 进程内存 (MB)"""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cmdline']):
            try:
                if p.info['name'] and 'python' in p.info['name'].lower():
                    cmdline = p.info.get('cmdline') or []
                    if any('src.main.main' in str(c) for c in cmdline):
                        rss = p.info['memory_info'].rss / 1024 / 1024
                        procs.append((p.info['pid'], rss))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        if procs:
            # 返回主进程内存（最大的那个）
            procs.sort(key=lambda x: x[1], reverse=True)
            return procs[0][1]
        return None
    except ImportError:
        # 没有 psutil，用 Windows 命令
        try:
            import subprocess
            result = subprocess.run(
                ['wmic', 'process', 'where', "name='python.exe'", 'get', 'WorkingSetSize'],
                capture_output=True, text=True, timeout=5
            )
            lines = [l.strip() for l in result.stdout.split('\n') if l.strip() and l.strip() != 'WorkingSetSize']
            if lines:
                max_mem = max(int(l) for l in lines if l.isdigit()) / 1024 / 1024
                return max_mem
        except Exception:
            pass
        return None

def mark_phase(name):
    """标记当前阶段"""
    ts = time.time()
    phase_markers.append((ts, name))
    mem = get_python_memory()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] PHASE: {name} | Memory: {mem:.1f} MB" if mem else f"[{datetime.now().strftime('%H:%M:%S')}] PHASE: {name} | Memory: N/A")

async def memory_monitor(stop_event):
    """后台内存监控"""
    while not stop_event.is_set():
        mem = get_python_memory()
        if mem is not None:
            memory_samples.append((time.time(), mem))
        await asyncio.sleep(SAMPLE_INTERVAL)

async def wait_with_monitor(seconds, phase_name):
    """等待并监控内存"""
    mark_phase(f"{phase_name} (等待{seconds}s)")
    for i in range(seconds):
        await asyncio.sleep(1)
        mem = get_python_memory()
        if mem:
            print(f"  [{i+1}/{seconds}s] Memory: {mem:.1f} MB")

async def main():
    from playwright.async_api import async_playwright
    import aiohttp

    print("=" * 60)
    print("v8.56 Memory Leak E2E Test")
    print("=" * 60)
    print(f"Server: {BASE_URL}")
    print(f"Device: {DEVICE_ID}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 检查 psutil
    try:
        import psutil
        print("[INFO] psutil available")
    except ImportError:
        print("[INFO] psutil not available, using wmic")

    # Phase 1: 启动前基线
    baseline = get_python_memory()
    print(f"\n[Phase 1] Baseline (before test)")
    print(f"  Server memory: {baseline:.1f} MB" if baseline else "  Server memory: N/A")

    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 监听 console 消息
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))

        # 监听页面错误
        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # Phase 2: 进入主控台
        mark_phase("进入 AstroHub 主页")
        print(f"\n[Phase 2] Navigate to AstroHub")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        # 尝试进入 console 页面
        print("  Looking for console nav button...")
        nav_buttons = await page.query_selector_all('.nav-btn')
        console_btn = None
        for btn in nav_buttons:
            text = await btn.text_content()
            print(f"    Nav button: {text}")
            if 'console' in (text or '').lower() or '主控' in (text or ''):
                console_btn = btn
                break

        if console_btn:
            print("  Clicking console nav button...")
            await console_btn.click()
            await page.wait_for_timeout(3000)
            mark_phase("进入主控台")
        else:
            # 可能默认就在 console 页面
            print("  No console button found, may already be on console page")
            # 检查是否已经在 console 页面
            active_page = await page.query_selector('.page.active')
            if active_page:
                page_id = await active_page.get_attribute('id')
                print(f"  Active page: {page_id}")
                if page_id == 'page-console':
                    mark_phase("已在主控台")
                else:
                    # 尝试点击第一个 nav 按钮
                    if nav_buttons:
                        await nav_buttons[0].click()
                        await page.wait_for_timeout(2000)
                        mark_phase("点击第一个 nav 按钮")

        await wait_with_monitor(3, "主控台空闲")

        # Phase 3: 录像 5 秒
        print(f"\n[Phase 3] Recording 5 seconds")
        mark_phase("开始录像")

        # 尝试通过 API 启动录像
        try:
            async with aiohttp.ClientSession() as session:
                # 启动录像
                rec_url = f"{BASE_URL}/api/v1/ptz/{DEVICE_ID}/record/start"
                print(f"  POST {rec_url}")
                async with session.post(rec_url, json={"target_name": "memory_test"}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    rec_data = await resp.json()
                    print(f"  Record start response: {rec_data}")

                # 等待 5 秒（录像中）
                await wait_with_monitor(5, "录像中")

                # 停止录像
                stop_url = f"{BASE_URL}/api/v1/ptz/{DEVICE_ID}/record/stop"
                print(f"  POST {stop_url}")
                async with session.post(stop_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    stop_data = await resp.json()
                    print(f"  Record stop response: {stop_data}")

        except Exception as e:
            print(f"  Recording API error: {e}")

        mark_phase("录像结束")
        await wait_with_monitor(3, "录像后空闲")

        # Phase 4: 切换到回放页面
        print(f"\n[Phase 4] Switch to Replay page")
        nav_buttons = await page.query_selector_all('.nav-btn')
        replay_btn = None
        for btn in nav_buttons:
            text = await btn.text_content()
            print(f"  Nav button: {text}")
            if 'replay' in (text or '').lower() or '回放' in (text or ''):
                replay_btn = btn
                break

        if replay_btn:
            print("  Clicking replay nav button...")
            await replay_btn.click()
            await page.wait_for_timeout(2000)
            mark_phase("进入回放页面")
        else:
            print("  No replay button found, trying second nav button")
            if len(nav_buttons) >= 2:
                await nav_buttons[1].click()
                await page.wait_for_timeout(2000)
                mark_phase("点击第二个 nav 按钮（回放）")

        await wait_with_monitor(5, "回放页面")

        # Phase 5: 切换回主控台
        print(f"\n[Phase 5] Switch back to Console")
        nav_buttons = await page.query_selector_all('.nav-btn')
        console_btn = None
        for btn in nav_buttons:
            text = await btn.text_content()
            if 'console' in (text or '').lower() or '主控' in (text or ''):
                console_btn = btn
                break

        if console_btn:
            print("  Clicking console nav button...")
            await console_btn.click()
            await page.wait_for_timeout(2000)
            mark_phase("回到主控台")
        else:
            if nav_buttons:
                await nav_buttons[0].click()
                await page.wait_for_timeout(2000)
                mark_phase("点击第一个 nav 按钮（主控台）")

        await wait_with_monitor(5, "回到主控台后")

        # Phase 6: 最终内存
        final_mem = get_python_memory()
        mark_phase("测试结束")

        # 检查 WASM 错误
        wasm_errors = [e for e in page_errors if '1011' in e]
        if wasm_errors:
            print(f"\n  [WARNING] WASM Error 1011 detected: {len(wasm_errors)} times")
        else:
            print(f"\n  [OK] No WASM Error 1011")

        if page_errors:
            print(f"  [INFO] Page errors ({len(page_errors)}):")
            for e in page_errors[:5]:
                print(f"    - {e[:100]}")

        await browser.close()

    # 生成报告
    print("\n" + "=" * 60)
    print("MEMORY REPORT")
    print("=" * 60)

    if not memory_samples:
        print("[WARNING] No memory samples collected!")
        return

    # 基线
    print(f"\nBaseline: {baseline:.1f} MB" if baseline else "\nBaseline: N/A")

    # 峰值
    max_mem = max(m for _, m in memory_samples)
    min_mem = min(m for _, m in memory_samples)
    final = memory_samples[-1][1] if memory_samples else 0
    delta = final - (baseline or 0)

    print(f"Min Memory:     {min_mem:.1f} MB")
    print(f"Max Memory:     {max_mem:.1f} MB")
    print(f"Final Memory:   {final:.1f} MB")
    print(f"Delta (final - baseline): {delta:+.1f} MB")
    print(f"Peak Delta (max - baseline): {(max_mem - (baseline or 0)):+.1f} MB")

    # 按阶段汇总
    print(f"\n{'Phase':<35} {'Memory (MB)':<15} {'Delta from baseline':<20}")
    print("-" * 70)
    for ts, phase in phase_markers:
        # 找最近的内存采样
        closest = min(memory_samples, key=lambda s: abs(s[0] - ts)) if memory_samples else (0, 0)
        mem = closest[1]
        d = mem - (baseline or 0)
        print(f"{phase:<35} {mem:<15.1f} {d:<+20.1f}")

    # 内存趋势
    print(f"\nMemory Trend (every 5s):")
    print(f"{'Time':<10} {'Memory (MB)':<15} {'Delta (MB)':<15}")
    print("-" * 40)
    for i in range(0, len(memory_samples), 5):
        ts, mem = memory_samples[i]
        t = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
        d = mem - (baseline or 0)
        print(f"{t:<10} {mem:<15.1f} {d:<+15.1f}")

    # 结论
    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)

    if delta > 50:
        print(f"[LEAK SUSPECTED] Memory increased {delta:+.1f} MB ({(delta/(baseline or 1)*100):+.1f}%)")
    elif delta > 20:
        print(f"[WARNING] Memory increased {delta:+.1f} MB, may need investigation")
    else:
        print(f"[OK] Memory stable. Delta: {delta:+.1f} MB ({(delta/(baseline or 1)*100):+.1f}%)")

    if wasm_errors:
        print(f"[WARNING] WASM Error 1011 still occurring ({len(wasm_errors)} times)")

    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
