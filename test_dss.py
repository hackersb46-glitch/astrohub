import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'astrohub'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'astrohub', 'src'))

from src.ptz.isapi.client import ISAPIClient

client = ISAPIClient('192.168.5.72', 'admin', 'Nftw1357')

# 获取当前值
resp = client.get('/Image/channels/1/DSS')
print('Before:', resp.xml)

# PUT 新值 *8
xml_str = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<DSS version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">\n'
    '  <enabled>true</enabled>\n'
    '  <DSSLevel>*8</DSSLevel>\n'
    '</DSS>'
)
put_resp = client.put('/Image/channels/1/DSS', xml_str)
print('PUT Status:', put_resp.status_code)

# 确认
resp2 = client.get('/Image/channels/1/DSS')
print('After:', resp2.xml)
