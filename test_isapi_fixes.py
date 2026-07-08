"""Test DSS off and filter settings against the ISAPI device"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'astrohub'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'astrohub', 'src'))
from src.ptz.isapi.client import ISAPIClient

client = ISAPIClient('192.168.5.72', 'admin', 'Nftw1357')

# Test 1: DSS off (without DSSLevel?)
print("=== Test 1: DSS off without DSSLevel ===")
xml_off = '<?xml version="1.0" encoding="UTF-8"?>\n<DSS version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">\n  <enabled>false</enabled>\n</DSS>'
resp = client.put('/Image/channels/1/DSS', xml_off)
print('Status:', resp.status_code)
print('Response:', resp.xml[:300] if hasattr(resp, 'xml') else 'N/A')

# Check current
resp_get = client.get('/Image/channels/1/DSS')
print('After:', resp_get.xml[:300])

# Restore
print("\n=== Restore DSS *4 ===")
xml_on = '<?xml version="1.0" encoding="UTF-8"?>\n<DSS version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">\n  <enabled>true</enabled>\n  <DSSLevel>*4</DSSLevel>\n</DSS>'
resp2 = client.put('/Image/channels/1/DSS', xml_on)
print('Status:', resp2.status_code)

# Test 2: GET Image/channels/1 for filter fields
print("\n=== Test 2: GET /Image/channels/1 ===")
resp_img = client.get('/Image/channels/1')
print('Status:', resp_img.status_code)
# Find IrcutFilterType in XML
xml = resp_img.xml
for line in xml.split('\n'):
    if 'IrcutFilterType' in line or 'irCutFilter' in line.lower():
        print('Found:', line.strip())
