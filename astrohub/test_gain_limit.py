import requests
from requests.auth import HTTPDigestAuth

auth = HTTPDigestAuth('admin', 'Nftw1357')
url = 'http://192.168.5.72/ISAPI/Image/channels/1/gain'

# Try PUT with GainLimit
xml = '''<?xml version="1.0" encoding="UTF-8"?>
<Gain version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">
<GainLevel>50</GainLevel>
<GainLimit>80</GainLimit>
</Gain>'''

headers = {'Content-Type': 'application/xml'}
try:
    resp = requests.put(url, auth=auth, data=xml, headers=headers, timeout=5)
    print(f'PUT Status: {resp.status_code}')
    print(f'PUT Response: {resp.text[:200]}')
except Exception as e:
    print(f'PUT Error: {e}')

# Verify the change
print('\n--- Verify ---')
try:
    resp = requests.get(url, auth=auth, timeout=5)
    print(f'GET Status: {resp.status_code}')
    print(resp.text[:500])
except Exception as e:
    print(f'GET Error: {e}')
