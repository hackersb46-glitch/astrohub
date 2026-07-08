import urllib.request
import json
import time

def test_brightness_search(target_val, shutter_idx, iris_idx, gain, label=""):
    url = 'http://127.0.0.1:10280/api/v1/vision/brightness-search'
    
    # 归一化坐标：假设图像1920x1080，选择中间区域 400x400 像素
    img_w, img_h = 1920, 1080
    pixel_x, pixel_y = 760, 340  # 中心位置
    pixel_w, pixel_h = 400, 400  # 区域大小
    
    data = {
        "x": pixel_x / img_w,      # 归一化 x
        "y": pixel_y / img_h,      # 归一化 y
        "w": pixel_w / img_w,      # 归一化宽度
        "h": pixel_h / img_h,      # 归一化高度
        "target": target_val,
        "shutter_idx": shutter_idx,
        "iris_idx": iris_idx,
        "gain": gain,
        "shutter_values": ["1/25","1/50","1/75","1/100","1/120","1/150","1/175","1/200","1/225","1/250","1/300","1/425","1/600","1/1000","1/1250","1/1750","1/2500","1/3500","1/6000","1/10000","1/30000"],
        "iris_values": ["160","200","240","280","340","400","480","560","680","960","1100","1400","1600","1900","2200"],
        "gain_min": 0,
        "gain_max": 100
    }

    print(f"\n{'='*60}")
    print(f"测试: {label}")
    print(f"参数: target={target_val}, shutter_idx={shutter_idx}, iris_idx={iris_idx}, gain={gain}")
    print(f"{'='*60}")
    
    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=180) as f:
            text = f.read().decode('utf-8')
            lines = text.strip().split('\n')
            step_count = 0
            for line in lines:
                if not line.strip():
                    continue
                if line.startswith('data:'):
                    try:
                        data_json = json.loads(line[5:].strip())
                        event_type = data_json.get('type')
                        
                        if event_type == 'start':
                            print(f"  初始亮度: {data_json.get('initial_brightness', '?')}")
                        elif event_type == 'brightness':
                            step_count += 1
                            action = data_json.get('action', '')
                            b = data_json.get('brightness', 0)
                            msg = data_json.get('message', '')
                            print(f"  Step {step_count:3d}: b={b:5.1f} {action:12s} {msg}")
                        elif event_type == 'done':
                            print(f"\n  ✓ 完成: reason={data_json.get('reason')}, "
                                  f"brightness={data_json.get('final_brightness', 0):.1f}, "
                                  f"steps={data_json.get('total_steps')}")
                        elif event_type == 'error':
                            print(f"\n  ✗ 错误: {data_json.get('message')}")
                    except Exception as e:
                        print(f"  解析错误: {e}")
            if step_count == 0:
                print("  (无输出)")
    except Exception as e:
        print(f"请求错误: {e}")

# 边界场景测试
print("="*60)
print("边界场景测试 - 使用归一化坐标")
print("="*60)

# 场景1: target=0, 从中间参数开始
test_brightness_search(0, 10, 5, 50, "target=0, 中间参数")
time.sleep(2)  # 避免并发

# 场景2: target=100, 从中间参数开始  
test_brightness_search(100, 10, 5, 50, "target=100, 中间参数")
time.sleep(2)

# 场景3: target=0, 从最暗参数开始（快门最快，光圈最小，增益最低）
test_brightness_search(0, 20, 14, 0, "target=0, 起始最暗")
time.sleep(2)

# 场景4: target=100, 从最亮参数开始（快门最慢，光圈最大，增益最高）
test_brightness_search(100, 0, 0, 100, "target=100, 起始最亮")

print("\n" + "="*60)
print("测试完成")
print("="*60)
