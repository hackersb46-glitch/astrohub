"""Fix P4.6 slow_shutter in function.py"""
path = r'astrohub\src\advanced\function.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the slow_shutter block
start_marker = '    # --- P4.6 慢快门 ---\n    "slow_shutter": {'
end_marker = '    # --- P4.7 光圈 Iris ---'

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx >= 0 and end_idx >= 0:
    new_block = '''    # --- P4.6 DSS 慢快门(低照度电子慢快门) ---
    "slow_shutter": {
        "p_id": "P4.6",
        "label": "DSS 慢快门",
        "endpoint": "/Image/channels/{ch}/DSS",
        "test_key": "DSSLevel",
        "test_values": ["*1.25", "*1.5", "*2", "*3", "*4", "*6", "*8"],
        "mode": "enum",
        "description": "低照度电子慢快门(DSS)，通过enabled开关+DSSLevel倍率控制",
    },

'''
    content = content[:start_idx] + new_block + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('P4.6 block replaced successfully')
else:
    print(f'start_marker found: {start_idx >= 0}, end_marker found: {end_idx >= 0}')
    # Try to find what's there
    idx = content.find('slow_shutter')
    if idx >= 0:
        print('Content around slow_shutter:')
        print(repr(content[idx-50:idx+300]))
