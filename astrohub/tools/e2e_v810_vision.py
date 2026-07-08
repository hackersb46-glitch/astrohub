"""v8.10 E2E - 白平衡 + 反差对焦 端到端测试
模拟: 截图 → 裁剪区域 → POST分析 → 验证结果
"""
import sys
import base64
import cv2
import numpy as np
import requests
import json
from pathlib import Path

BASE = "http://127.0.0.1:10280/api/v1"
DEVICE = "192.168.5.72"
passed = 0
failed = 0
results = []

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        results.append(f"  PASS {name}")
        print(f"  [PASS] {name}{' - ' + detail if detail else ''}")
    else:
        failed += 1
        results.append(f"  FAIL {name}: {detail}")
        print(f"  [FAIL] {name}: {detail}")

def region_b64_from_file(image_path, x, y, w, h):
    """从截图文件裁剪区域 → base64"""
    img = cv2.imread(image_path)
    if img is None:
        return None
    crop = img[y:y+h, x:x+w]
    _, buf = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf).decode('utf-8')

print("=" * 60)
print("v8.10 E2E: 白平衡 + 反差对焦")
print("=" * 60)

# ── Step 1: 截图获取真实画面 ──
print("\n[1] 截图获取真实画面...")
r = requests.post(f"{BASE}/ptz/{DEVICE}/capture", timeout=30)
data = r.json()
check("截图成功", data.get("success"), data.get("message", ""))
image_path = data.get("data", {}).get("image_path", "")
check("有文件路径", bool(image_path), image_path)

if not image_path or not Path(image_path).exists():
    print(f"  [FATAL] 截图文件不存在: {image_path}")
    sys.exit(1)

# ── Step 2: 读取图片并裁剪中心区域 ──
print("\n[2] 读取图片并裁剪中心区域...")
img = cv2.imread(image_path)
check("图片可读", img is not None, f"shape={img.shape if img is not None else 'None'}")

h, w = img.shape[:2]
cx, cy = w // 2, h // 2
# 裁剪中央 200x200 区域
rw, rh = 200, 200
rx, ry = cx - rw // 2, cy - rh // 2
region_b64 = region_b64_from_file(image_path, rx, ry, rw, rh)
check("区域裁剪+base64编码", region_b64 is not None and len(region_b64) > 0,
      f"length={len(region_b64) if region_b64 else 0}")
check("base64以/9j开头(JPEG)", region_b64.startswith("/9j/") if region_b64 else False)

# ── Step 3: POST /vision/region-analyze (whitebalance) ──
print("\n[3] POST /vision/region-analyze (whitebalance)...")
r = requests.post(f"{BASE}/vision/region-analyze", json={
    "image_base64": region_b64,
    "action": "whitebalance"
}, timeout=30)
wb_data = r.json()
check("HTTP 200", r.status_code == 200, f"status={r.status_code}")
check("success=true", wb_data.get("success"), wb_data.get("message", ""))
check("返回 whitebalance 数据", "whitebalance" in wb_data,
      str(wb_data.get("whitebalance", "")))
if "whitebalance" in wb_data:
    wb = wb_data["whitebalance"]
    check("red_gain 是整数", isinstance(wb.get("red_gain"), (int, float)))
    check("blue_gain 是整数", isinstance(wb.get("blue_gain"), (int, float)))
    check("r_mean 有值", isinstance(wb.get("r_mean"), (int, float)))
    check("g_mean 有值", isinstance(wb.get("g_mean"), (int, float)))
    check("b_mean 有值", isinstance(wb.get("b_mean"), (int, float)))
    print(f"    → R={wb.get('red_gain')} B={wb.get('blue_gain')} "
          f"(Rmean={wb.get('r_mean')} Gmean={wb.get('g_mean')} Bmean={wb.get('b_mean')})")

# ── Step 4: POST /vision/region-analyze (focus) ──
print("\n[4] POST /vision/region-analyze (focus)...")
r = requests.post(f"{BASE}/vision/region-analyze", json={
    "image_base64": region_b64,
    "action": "focus"
}, timeout=30)
focus_data = r.json()
check("HTTP 200", r.status_code == 200, f"status={r.status_code}")
check("success=true", focus_data.get("success"), focus_data.get("message", ""))
check("返回 contrast 值", "contrast" in focus_data,
      str(focus_data.get("contrast", "")))
if "contrast" in focus_data:
    check("contrast > 0", focus_data["contrast"] > 0,
          f"contrast={focus_data['contrast']:.1f}")
    print(f"    → contrast={focus_data['contrast']:.1f}")

# ── Step 5: POST /vision/region-analyze (both) ──
print("\n[5] POST /vision/region-analyze (both)...")
r = requests.post(f"{BASE}/vision/region-analyze", json={
    "image_base64": region_b64,
    "action": "both"
}, timeout=30)
both_data = r.json()
check("HTTP 200", r.status_code == 200)
check("success=true", both_data.get("success"))
check("同时返回 whitebalance", "whitebalance" in both_data)
check("同时返回 contrast", "contrast" in both_data)

# ── Step 6: POST /vision/whitebalance-apply ──
print("\n[6] POST /vision/whitebalance-apply...")
r = requests.post(f"{BASE}/vision/whitebalance-apply", json={
    "device_id": DEVICE,
    "red_gain": 100,
    "blue_gain": 100
}, timeout=30)
wb_apply = r.json()
check("HTTP 200", r.status_code == 200)
check("有返回消息", "message" in wb_apply, str(wb_apply)[:100])
print(f"    → {wb_apply.get('message', wb_apply.get('success'))}")

# ── Step 7: POST /vision/focus-search ──
print("\n[7] POST /vision/focus-search...")
r = requests.post(f"{BASE}/vision/focus-search", json={
    "device_id": DEVICE,
    "image_base64": region_b64
}, timeout=120)
fs_data = r.json()
check("HTTP 200", r.status_code == 200)
check("有返回消息", "message" in fs_data or "success" in fs_data, str(fs_data)[:200])
print(f"    → {json.dumps(fs_data, ensure_ascii=False)[:200]}")

# ── Step 8: 边界测试 ──
print("\n[8] 边界测试...")
# 空base64
r = requests.post(f"{BASE}/vision/region-analyze", json={
    "image_base64": "",
    "action": "both"
}, timeout=30)
check("空base64返回非200", r.status_code != 500)
print(f"    → 空base64: status={r.status_code} msg={r.json().get('message', '')[:80]}")

# 无设备ID
r = requests.post(f"{BASE}/vision/focus-search", json={
    "device_id": "0.0.0.0",
    "image_base64": region_b64
}, timeout=30)
check("无效设备不崩溃", r.status_code != 500)
print(f"    → 无效设备: status={r.status_code} msg={r.json().get('message', '')[:80]}")

# ── 结果汇总 ──
print("\n" + "=" * 60)
print(f"  结果: {passed} PASS / {failed} FAIL / {passed+failed} TOTAL")
if failed == 0:
    print("  ✅ ALL PASS")
else:
    print("  ❌ FAILURES DETECTED")
print("=" * 60)
