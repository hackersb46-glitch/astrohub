"""v8.13 白平衡SSE测试 - 中央200x200选区"""
import json, urllib.request, time

API = "http://127.0.0.1:10280"
DEVICE = "192.168.5.72"

def req_json(url, data=None):
    d = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=d, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())

def sse_request(url, data):
    """SSE流式请求，返回所有解析后的事件列表"""
    d = json.dumps(data).encode()
    r = urllib.request.Request(url, data=d, headers={"Content-Type": "application/json"})
    events = []
    with urllib.request.urlopen(r, timeout=180) as resp:
        buf = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            # 按 \n\n 分割
            while b"\n\n" in buf:
                line, buf = buf.split(b"\n\n", 1)
                text = line.decode("utf-8")
                if text.startswith("data: "):
                    try:
                        events.append(json.loads(text[6:]))
                    except:
                        pass
    return events

# 1. 切手动模式
print("=" * 50)
print("v8.13 白平衡SSE测试 - 中央200x200")
print("=" * 50)

wb_state = req_json(f"{API}/api/v1/ptz/{DEVICE}/image/whitebalance")
print(f"当前白平衡: {wb_state.get('mode','?')} R={wb_state.get('red_gain','?')} B={wb_state.get('blue_gain','?')}")

print("切换手动模式...")
r = req_json(f"{API}/api/v1/ptz/{DEVICE}/image/whitebalance", {"mode": "manual", "red_gain": 100, "blue_gain": 100})
print(f"切换结果: {r.get('message', r)}")
time.sleep(0.5)

# 2. ISAPI分辨率
img_w, img_h = 2688, 1520
print(f"ISAPI分辨率: {img_w}x{img_h}")

# 3. 中央200x200
cx, cy = 0.5, 0.5
fw, fh = 200, 200
x_ratio = cx - (fw / img_w) / 2
y_ratio = cy - (fh / img_h) / 2
w_ratio = fw / img_w
h_ratio = fh / img_h
print(f"选区比例: x={x_ratio:.4f} y={y_ratio:.4f} w={w_ratio:.4f} h={h_ratio:.4f}")

# 4. SSE流式调用
print("\n" + "=" * 50)
print("开始白平衡迭代搜索 (SSE流式)...")
print("=" * 50)

t0 = time.time()
events = sse_request(f"{API}/api/v1/vision/whitebalance-search", {
    "x": x_ratio, "y": y_ratio, "w": w_ratio, "h": h_ratio
})
elapsed = time.time() - t0

# 打印每步
final_red = 100
final_blue = 100
total_steps = 0
print("")
for ev in events:
    t = ev.get("type", "?")
    if t == "start":
        print(f"  #0  开始  {ev.get('crop', '')}")
    elif t == "wb":
        total_steps = ev.get("step", 0)
        print(f"  #{total_steps:2d} {ev.get('stage',''):6s} R={ev.get('red_gain',0):3d} B={ev.get('blue_gain',0):3d} "
              f"-> R={ev.get('r_avg',0):6.1f} G={ev.get('g_avg',0):6.1f} B={ev.get('b_avg',0):6.1f} "
              f"(D={ev.get('delta',0):.4f}) {ev.get('message','')}")
    elif t == "done":
        final_red = ev.get("final_red", 100)
        final_blue = ev.get("final_blue", 100)
        print(f"  #{'done':2s} 完成  R={final_red} B={final_blue}")
    elif t == "cleanup":
        print(f"  #..  清理完成")
    elif t == "error":
        print(f"  #!!  错误: {ev.get('message','')}")

print(f"\n耗时: {elapsed:.1f}s")
print(f"总步数: {total_steps}")
print(f"最终 R增益: {final_red}")
print(f"最终 B增益: {final_blue}")

# 5. 验证
print("\n--- 验证 ---")
checks = []
if final_red != 100 or final_blue != 100:
    checks.append("OK 增益已调整 (非100/100)")
else:
    checks.append("FAIL 增益未变化 (100/100)")

if total_steps > 3:
    checks.append(f"OK 有效迭代 ({total_steps}步)")
else:
    checks.append(f"WARN 步数偏少 ({total_steps}步)")

wb_events = [e for e in events if e.get("type") == "wb"]
if wb_events:
    last_delta = wb_events[-1].get("delta", 999)
    if last_delta < 1.0:
        checks.append(f"OK Delta合理 ({last_delta:.4f} < 1.0)")
    else:
        checks.append(f"FAIL Delta过大 ({last_delta:.4f})")

for c in checks:
    print(c)

print("\n" + "=" * 50)
print("测试完成  v8.13 SSE")
print("=" * 50)
