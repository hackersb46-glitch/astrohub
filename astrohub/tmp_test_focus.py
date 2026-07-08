"""模拟用户操作：画面中间30%自动对焦

前端逻辑（index.html _finishRegion）：
1. 用户框选区域 → 归一化坐标 (x, y, w, h)
2. POST /api/v1/vision/focus-search
3. 读取 SSE 事件流

画面中间30% = x=0.35, y=0.35, w=0.30, h=0.30
"""
import requests
import json
import time

BASE_URL = 'http://localhost:10280'

# 画面中间30%
region = {
    "x": 0.35,
    "y": 0.35,
    "w": 0.30,
    "h": 0.30
}

print(f"=== AstroHub v8.59 自动对焦测试 ===")
print(f"设备: 192.168.5.72 (4k 32X DC)")
print(f"区域: 画面中间30% (x={region['x']}, y={region['y']}, w={region['w']}, h={region['h']})")
print(f"开始时间: {time.strftime('%H:%M:%S')}")
print(f"=" * 60)

# POST 请求，读取 SSE 流
url = f'{BASE_URL}/api/v1/vision/focus-search'
headers = {'Content-Type': 'application/json'}
body = json.dumps(region)

try:
    resp = requests.post(url, headers=headers, data=body, stream=True, timeout=120)
    print(f"HTTP {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"Error: {resp.text[:200]}")
    else:
        # 读取 SSE 事件
        buffer = ""
        step_count = 0
        start_time = time.time()
        
        for chunk in resp.iter_content(chunk_size=512, decode_unicode=True):
            if chunk:
                buffer += chunk
                # 按 \n\n 分割事件
                parts = buffer.split('\n\n')
                buffer = parts.pop()  # 最后一段可能不完整
                
                for part in parts:
                    if not part.startswith('data: '):
                        continue
                    try:
                        ev = json.loads(part[6:])
                        ev_type = ev.get('type', '')
                        
                        if ev_type == 'start':
                            print(f"[START] 裁剪区域: {ev.get('crop', '')}")
                        
                        elif ev_type == 'focus':
                            step_count += 1
                            stage = ev.get('stage', '')
                            action = ev.get('action', '')
                            contrast = ev.get('contrast', 0)
                            duration = ev.get('duration', 0)
                            msg = ev.get('message', '')
                            print(f"  #{step_count:2d} [{stage:8s}] {action:12s} contrast={contrast:8.1f} dur={duration:.3f}s | {msg}")
                        
                        elif ev_type == 'done':
                            final_c = ev.get('final_contrast', 0)
                            best_c = ev.get('best_contrast', 0)
                            total = ev.get('total_steps', 0)
                            verified = ev.get('verified', False)
                            elapsed = time.time() - start_time
                            print(f"\n[DONE] 最终反差={final_c} 峰值={best_c} 总步数={total} 验证={'PASS' if verified else 'FAIL'}")
                            print(f"[TIME] 耗时 {elapsed:.1f}s")
                        
                        elif ev_type == 'error':
                            print(f"[ERROR] {ev.get('message', '')}")
                        
                        elif ev_type == 'interrupt':
                            print(f"[INTERRUPT] {ev.get('message', '')}")
                        
                        elif ev_type == 'cleanup':
                            print(f"[CLEANUP] 清理完成")
                        
                        elif ev_type == 'warning':
                            print(f"[WARNING] {ev.get('message', '')}")
                        
                    except json.JSONDecodeError:
                        pass
        
        print(f"\n结束时间: {time.strftime('%H:%M:%S')}")
        
except requests.exceptions.Timeout:
    print("[TIMEOUT] 对焦搜索超时（120s）")
except Exception as e:
    print(f"[EXCEPTION] {e}")
