"""直接调用API检查滤镜状态"""
import requests
import json

# 调用滤镜API
url = "http://127.0.0.1:10280/api/v1/ptz/192.168.5.72/image/filter"
try:
    response = requests.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")
