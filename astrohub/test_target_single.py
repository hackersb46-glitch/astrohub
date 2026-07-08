import urllib.request
import json

def test_brightness_search(target_val, shutter_idx, iris_idx, gain, label=""):
    url = 'http://127.0.0.1:10280/api/v1/vision/brightness-search'
    data = {
        "x": 900, "y": 500, "w": 400, "h": 400,
        "target": target_val,
        "shutter_idx": shutter_idx,
        "iris_idx": iris_idx,
        "gain": gain,
        "shutter_values": ["1/25","1/50","1/75","1/100","1/120","1/150","1/175","1/200","1/225","1/250","1/300","1/425","1/600","1/1000","1/1250","1/1750","1/2500","1/3500","1/6000","1/10000","1/30000"],
        "iris_values": ["160","200","240","280","340","400","480","560","680","960","1100","1400","1600","1900","2200"],
        "gain_min": 0,
        "gain_max": 100
    }

    req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as f:
            text = f.read().decode('utf-8')
            print(f"\n=== {label} ===")
            print(f"Raw response:\n{text[:2000]}")
    except Exception as e:
        print(f"\n=== {label} ===\nError: {e}")

# 只测试一个场景
test_brightness_search(0, 0, 0, 50, "target=0, shutter=1/25, iris=160, gain=50")
