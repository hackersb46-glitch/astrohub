import json
from pathlib import Path

DEVICES_DIR = Path(r'C:\Users\admin\.openclaw\agents\dev-factory\astrohub\data\devices')
device_id = '192.168.5.72'
target_ip = '192.168.5.72'

# Method 1: device_id as MAC
device_dir = DEVICES_DIR / device_id
print(f'Method 1: {device_dir}')
print(f'  exists: {device_dir.exists()}, is_dir: {device_dir.is_dir()}')
if device_dir.exists() and device_dir.is_dir():
    func_file = device_dir / 'function.json'
    print(f'  function.json exists: {func_file.exists()}')
    # list files in this dir
    if device_dir.exists():
        for f in device_dir.iterdir():
            print(f'    file: {f.name}')

# Method 2: iterate and match IP
print(f'\nMethod 2: iterate dirs')
for device_dir in DEVICES_DIR.iterdir():
    if device_dir.is_dir():
        info_file = device_dir / 'info.json'
        if info_file.exists():
            info = json.loads(info_file.read_text(encoding='utf-8'))
            if info.get('ip') == target_ip:
                print(f'  Found match: {device_dir.name}')
                func_file = device_dir / 'function.json'
                print(f'  function.json exists: {func_file.exists()}')
                if func_file.exists():
                    func_data = json.loads(func_file.read_text(encoding='utf-8'))
                    opt_values = func_data['functions']['shutter'].get('opt_values', [])
                    print(f'  opt_values count: {len(opt_values)}')
                    print(f'  opt_values: {opt_values}')
                break
