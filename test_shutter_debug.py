import sys
sys.path.insert(0, 'astrohub')
from src.config_paths import DEVICES_DIR
import json

# Simulate exactly what get_shutter does
device_id = '192.168.5.72'
target_ip = '192.168.5.72'

# Method 1: device_id is MAC
device_dir = DEVICES_DIR / device_id
print(f'Method 1: {device_dir}')
print(f'  exists: {device_dir.exists()}')
if device_dir.exists() and device_dir.is_dir():
    func_file = device_dir / 'function.json'
    print(f'  function.json: {func_file.exists()}')

# Method 2: iterate and match IP
print()
print('Method 2: iterate dirs')
for dd in DEVICES_DIR.iterdir():
    if dd.is_dir():
        info_file = dd / 'info.json'
        if info_file.exists():
            info = json.loads(info_file.read_text(encoding='utf-8'))
            ip = info.get('ip')
            print(f'  Dir: {dd.name}, IP: {ip}')
            if ip == target_ip:
                func_file = dd / 'function.json'
                print(f'  MATCH: {dd.name}')
                print(f'  function.json: {func_file.exists()}')
                if func_file.exists():
                    func_data = json.loads(func_file.read_text(encoding='utf-8'))
                    if 'functions' in func_data and 'shutter' in func_data['functions']:
                        opt = func_data['functions']['shutter'].get('opt_values', [])
                        print(f'  opt_values: {len(opt)} values')
                        print(f'  values: {opt}')
                break
