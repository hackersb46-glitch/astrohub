"""v8.27 对焦SSE测试 - 正中心15%选区 (~403×228)"""
import json, urllib.request, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
            while b"\n\n" in buf:
                line, buf = buf.split(b"\n\n", 1)
                text = line.decode("utf-8")
                if text.startswith("data: "):
                    try:
                        events.append(json.loads(text[6:]))
                    except:
                        pass
    return events

print("=" * 50)
print("v8.37 对焦SSE测试 - 用户框选区域")
print("=" * 50)

# ISAPI分辨率
img_w, img_h = 2688, 1520
print(f"ISAPI分辨率: {img_w}x{img_h}")

# 用户框选区域: X=581~1005, Y=1343~1629
x1, x2 = 581, 1005
y1, y2 = 1343, 1629
fw, fh = x2 - x1, y2 - y1
x_ratio = x1 / img_w
y_ratio = y1 / img_h
w_ratio = fw / img_w
h_ratio = fh / img_h
print(f"选区比例: x={x_ratio:.4f} y={y_ratio:.4f} w={w_ratio:.4f} h={h_ratio:.4f}")

# SSE流式调用
print("\n" + "=" * 50)
print("开始对焦迭代搜索 (SSE流式)...")
print("=" * 50)

t0 = time.time()
events = sse_request(f"{API}/api/v1/vision/focus-search", {
    "x": x_ratio, "y": y_ratio, "w": w_ratio, "h": h_ratio
})
elapsed = time.time() - t0

# 打印每步
final_contrast = 0
best_contrast = 0
total_steps = 0
rollback_steps = 0
verified = False
print("")
for ev in events:
    t = ev.get("type", "?")
    if t == "start":
        print(f"  #0  开始  {ev.get('crop', '')}")
    elif t == "focus":
        total_steps = ev.get("step", 0)
        print(f"  #{total_steps:2d} {ev.get('stage',''):6s} {ev.get('action',''):10s} "
              f"反差={ev.get('contrast',0):8.1f} ({ev.get('duration',0):.1f}s) {ev.get('message','')}")
    elif t == "focus_rollback":
        print(f"  #R{ev.get('rollback_step',0)}  回滚  "
              f"反差={ev.get('contrast',0):8.1f} (最佳={ev.get('best_contrast',0):.1f}) {ev.get('message','')}")
    elif t == "done":
        final_contrast = ev.get("final_contrast", 0)
        best_contrast = ev.get("best_contrast", 0)
        rollback_steps = ev.get("rollback_steps", 0)
        verified = ev.get("verified", False)
        print(f"  #done 完成  反差={final_contrast:.1f} (最佳={best_contrast:.1f}) "
              f"回滚={rollback_steps}步 验证={'通过' if verified else '未通过'}")
    elif t == "wb_verify":
        print(f"  #V  验证  delta={ev.get('verified_delta',0):.4f} (最佳={ev.get('best_delta',0):.4f})")
    elif t == "cleanup":
        print(f"  #..  清理完成")
    elif t == "error":
        print(f"  #!!  错误: {ev.get('message','')}")

print(f"\n耗时: {elapsed:.1f}s")
print(f"总步数: {total_steps}")
print(f"最佳反差: {best_contrast:.1f}")
print(f"最终反差: {final_contrast:.1f}")
print(f"回滚步数: {rollback_steps}")
print(f"验证结果: {'通过' if verified else '未通过'}")

# 验证
print("\n--- 验证 ---")
checks = []
if total_steps > 3:
    checks.append(f"OK 有效迭代 ({total_steps}步)")
else:
    checks.append(f"FAIL 步数偏少 ({total_steps}步)")

if best_contrast > 0:
    checks.append(f"OK 最佳反差合理 ({best_contrast:.1f})")
else:
    checks.append(f"FAIL 最佳反差为0")

if rollback_steps > 0:
    checks.append(f"OK 有回滚 ({rollback_steps}步)")
else:
    checks.append(f"WARN 无回滚")

if verified:
    checks.append("OK 回滚验证通过")
else:
    checks.append(f"WARN 回滚未验证")

for c in checks:
    print(c)

print("\n" + "=" * 50)
print("测试完成  v8.27 对焦SSE")
print("=" * 50)
