"""Analyze index.html structure"""
import re

with open('src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

print('=== Pages defined in index.html ===')
for m in re.finditer(r'id="page-([^"]+)"', content):
    print(f'  id="page-{m.group(1)}"')

print('\n=== nav-btn data-page values ===')
for m in re.finditer(r'data-page="([^"]+)"', content):
    print(f'  data-page="{m.group(1)}"')

print('\n=== console.html include ===')
if 'console.html' in content:
    idx = content.find('console.html')
    print(f'  Found at pos {idx}')
    print(f'  Context: {content[max(0,idx-50):idx+100]}')
else:
    print('  NOT found')

print('\n=== replay related ===')
for kw in ['page-replay', 'initReplay', 'replayPage']:
    if kw in content:
        idx = content.find(kw)
        print(f'  {kw}: {content[max(0,idx-30):idx+100][:130]}')
    else:
        print(f'  {kw}: NOT found')

# Check for WASM cleanup/destroy on tab switch
print('\n=== WASM cleanup on tab switch ===')
for kw in ['destroy', 'destroyWorker', 'wasmStop', 'moveVideoTo']:
    if kw in content:
        idx = content.find(kw)
        print(f'  {kw}: {content[max(0,idx-30):idx+120][:150]}')
    else:
        print(f'  {kw}: NOT found')
