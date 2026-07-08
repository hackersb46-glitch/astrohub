import requests

# 测试supported_levels中的所有值
levels = ['1/30', '1/60', '1/125', '1/250', '1/500', '1/1000', '1/2000', '1/4000', '1/8000', '1/30000', '1/25']
print("Testing all supported levels:")
for level in levels:
    r = requests.post('http://localhost:10280/api/v1/ptz/192.168.5.72/image/shutter', json={'level': level})
    result = r.json()
    status = 'OK' if result.get('success') else f"FAIL({result.get('message', '')})"
    print(f'{level}: {status}')
