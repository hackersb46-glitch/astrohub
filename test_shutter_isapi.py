import sys
sys.path.insert(0, 'astrohub')

from src.api.ptz_client import PTZClient
from src.api.device_auth import get_device_auth

# 获取设备认证
auth = get_device_auth('192.168.5.72')
print('认证信息:', auth)

# 创建客户端
client = PTZClient('192.168.5.72', auth)
print('客户端创建成功')

# 直接ISAPI PUT测试不同的快门值
test_values = ['1/60', '1/500', '1/600', '1/125']

for val in test_values:
    xml_str = f'''<?xml version="1.0" encoding="UTF-8"?>
<Shutter version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ShutterLevel>{val}</ShutterLevel>
</Shutter>'''
    
    resp = client.put('/Image/channels/1/Shutter', xml_str)
    print(f'ISAPI {val}: status={resp.status_code}, response={resp.text[:200] if resp.text else "empty"}')
