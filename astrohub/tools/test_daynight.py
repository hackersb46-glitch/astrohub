"""Test dayNight endpoints on device"""
import requests, json
from requests.auth import HTTPDigestAuth

with open('data/devices/240f9b764193/info.json') as f:
    info = json.load(f)

s = requests.Session()
s.auth = HTTPDigestAuth(info['username'], info['password'])

# Test multiple potential day/night endpoints
endpoints = [
    '/ISAPI/Image/channels/1/dayNightMode',
    '/ISAPI/Image/channels/1/dayNight',
    '/ISAPI/Image/channels/1/daynightMode',
    '/ISAPI/Image/channels/1/switchMode',
    '/ISAPI/Image/channels/1/ImageChannel/dayNightMode',
    '/ISAPI/System/Video/inputs/channels/1/dayNightMode',
    '/ISAPI/Image/channels/1/VideoParam',
    '/ISAPI/Image/channels/1/ImageParam',
    '/ISAPI/Image/channels/1/DayNight',
    '/ISAPI/Image/dayNight/channels/1',
    '/ISAPI/Image/channels/1/DayNightMode',
    '/ISAPI/Image/channels/1/irCutFilter',
    '/ISAPI/Image/channels/1/IrcutFilter',
]

print('Testing day-night endpoints:')
for ep in endpoints:
    try:
        r = s.get(f'http://192.168.5.72{ep}', timeout=5)
        status = r.status_code
        size = len(r.text)
        preview = r.text[:200] if status == 200 else ''
        print(f'  {ep}: {status} ({size} bytes)')
        if status == 200:
            print(f'    Preview: {preview[:150]}')
    except Exception as e:
        print(f'  {ep}: ERROR - {e}')

# Also test PUT to /Image/channels/1 with a partial XML containing dayNightMode
print('\n--- Test PUT /Image/channels/1 with partial XML ---')
xml_partial = '<?xml version="1.0" encoding="UTF-8"?><ImageChannel xmlns="http://www.hikvision.com/ver20/XMLSchema"><dayNightMode>day</dayNightMode></ImageChannel>'
try:
    r = s.put('http://192.168.5.72/ISAPI/Image/channels/1', 
              data=xml_partial.encode('utf-8'),
              headers={'Content-Type': 'application/xml; charset=UTF-8'}, timeout=10)
    print(f'PUT partial XML: {r.status_code}')
    print(f'  Response: {r.text[:300]}')
except Exception as e:
    print(f'PUT partial XML: ERROR - {e}')

# Test GET /Image/channels/1 with longer timeout to make sure it works
print('\n--- Test GET /Image/channels/1 (15s timeout) ---')
import time
start = time.time()
try:
    r = s.get('http://192.168.5.72/ISAPI/Image/channels/1', timeout=15)
    elapsed = time.time() - start
    print(f'GET: {r.status_code}, size={len(r.text)}, time={elapsed:.1f}s')
    # Search for any day/night related tags
    import re
    for kw in ['dayNight', 'DayNight', 'day_night', 'switchMode', 'SwitchMode']:
        if kw.lower() in r.text.lower():
            m = re.search(rf'.{{0,30}}{kw}.{{0,80}}', r.text, re.IGNORECASE)
            if m:
                print(f'  Found "{kw}": {m.group(0)[:120]}')
except Exception as e:
    print(f'GET ERROR: {e}')

# Test PUT /Image/channels/1 with full original XML (unchanged)
print('\n--- Test PUT /Image/channels/1 with original XML (unchanged) ---')
try:
    r_get = s.get('http://192.168.5.72/ISAPI/Image/channels/1', timeout=10)
    if r_get.status_code == 200:
        r_put = s.put('http://192.168.5.72/ISAPI/Image/channels/1',
                      data=r_get.text.encode('utf-8'),
                      headers={'Content-Type': 'application/xml; charset=UTF-8'}, timeout=10)
        print(f'PUT unchanged: {r_put.status_code}')
        print(f'  Response: {r_put.text[:300]}')
except Exception as e:
    print(f'PUT unchanged: ERROR - {e}')
