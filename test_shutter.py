import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'astrohub'))

from src.controlpanel.ptz_device_controller import PTZDeviceController

# 创建临时管理器获取客户端
mgr = PTZDeviceController("192.168.5.72")
ctrl, err = mgr._get_controller("192.168.5.72")

if err:
    print(f"Error: {err}")
    sys.exit(1)

client = ctrl.client

# 测试不同的快门值
test_values = ["1/60", "1/500", "1/600", "1/1000"]

for val in test_values:
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Shutter version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <ShutterLevel>{val}</ShutterLevel>
</Shutter>'''
    
    resp = client.put("/Image/channels/1/Shutter", xml)
    print(f"Shutter {val}: status={resp.status_code}, response={resp.text[:200] if resp.text else 'empty'}")
