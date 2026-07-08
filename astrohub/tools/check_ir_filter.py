"""Check IR filter controls in detail"""
import requests, json, re
from requests.auth import HTTPDigestAuth

with open('data/devices/240f9b764193/info.json') as f:
    info = json.load(f)

s = requests.Session()
s.auth = HTTPDigestAuth(info['username'], info['password'])

# 1. Full capabilities XML
print('=== Capabilities: IR/filter related ===')
r = s.get('http://192.168.5.72/ISAPI/Image/channels/1/capabilities', timeout=10)
if r.status_code == 200:
    # Find all tags containing 'ir' or 'filter' or 'cut'
    for m in re.finditer(r'<([^>]*)(?:[Ii][Rr]|[Ff]ilter|[Cc]ut)([^>]*)>([^<]*)</', r.text):
        tag = m.group(0)
        print(f'  {tag[:150]}')

# 2. Full IrcutFilter XML
print('\n=== Full IrcutFilter XML ===')
r2 = s.get('http://192.168.5.72/ISAPI/Image/channels/1/IrcutFilter', timeout=10)
print(r2.text)

# 3. Full /Image/channels/1 - extract IrcutFilter block
print('\n=== /Image/channels/1: IrcutFilter block ===')
r3 = s.get('http://192.168.5.72/ISAPI/Image/channels/1', timeout=10)
m = re.search(r'<IrcutFilter[^>]*>.*?</IrcutFilter>', r3.text, re.DOTALL)
if m:
    print(m.group(0))

# Check for IrLight (IR supplement light - boss said NOT this)
m2 = re.search(r'<IrLight[^>]*>.*?</IrLight>', r3.text, re.DOTALL)
if m2:
    print(f'\nIrLight (IR supplement, not what we want):')
    print(m2.group(0))

# 4. Check for IR cut filter on/off capability
print('\n=== IrcutFilterType capabilities (from tags) ===')
# Find all IrcutFilterType elements
for m in re.finditer(r'<IrcutFilterType[^>]*>([^<]*)</IrcutFilterType>', r3.text):
    value = m.group(1)
    print(f'Current value: {value}')

for m in re.finditer(r'<IrcutFilterType[^>]*opt="([^"]*)"', r.text):
    options = m.group(1)
    print(f'Options: {options}')

print('\n=== Conclusion ===')
print('IR filter IS controlled by IrcutFilterType element.')
print('  day = IR cut filter ENGAGED (blocks IR, color)')
print('  night = IR cut filter DISENGAGED (allows IR, B&W)')
print('  auto = auto switch based on light')
print('No separate IR filter endpoint - the same setting.')
