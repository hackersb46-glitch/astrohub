import requests
from src.ptz.isapi.client import ISAPIClient

# 直接测试 ISAPI 调用
client = ISAPIClient(ip='192.168.5.72', username='admin', password='admin12345', port=80)

# 1. 读取当前对焦模式
r = client.get('/System/Video/inputs/channels/1/focus')
print('GET /System/Video/inputs/channels/1/focus:')
print(f'  status={r.status_code}')
print(f'  xml={r.xml[:500]}')
print()

# 2. 设置手动对焦
xml = '<Focus xmlns="http://www.hikvision.com/ver20/XMLSchema"><autoFocusMode>Manual</autoFocusMode></Focus>'
r2 = client.put('/System/Video/inputs/channels/1/focus', xml)
print('PUT set manual:')
print(f'  status={r2.status_code}')
print(f'  xml={r2.xml[:500]}')
print()

# 3. 再次读取
r3 = client.get('/System/Video/inputs/channels/1/focus')
print('GET after set:')
print(f'  status={r3.status_code}')
print(f'  xml={r3.xml[:500]}')
print()

# 4. 发送焦点移动命令
xml2 = '<FocusData><focus>60</focus></FocusData>'
r4 = client.put('/System/Video/inputs/channels/1/focus', xml2)
print('PUT focus move:')
print(f'  status={r4.status_code}')
print(f'  xml={r4.xml[:500]}')
