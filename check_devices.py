from pathlib import Path
import json

devices_dir = Path(r'C:\Users\admin\.openclaw\agents\dev-factory\astrohub\data\devices')
device_id = '192.168.5.72'
target_ip = '192.168.5.72'

print(f'device_id={device_id}')
d = devices_dir / device_id
print(f'  exists: {d.exists()}, is_dir: {d.is_dir()}')
if d.exists():
    print(f'  files: {[f.name for f in d.iterdir()]}')

print()
print('iterating:')
for dd in devices_dir.iterdir():
    if dd.is_dir():
        print(f'  dir: {dd.name}')
        info = dd / 'info.json'
        if info.exists():
            data = json.loads(info.read_text('utf-8'))
            ip = data.get('ip')
            print(f'    IP: {ip}')
            func = dd / 'function.json'
            print(f'    function.json: {func.exists()}')
            if func.exists():
                func_data = json.loads(func.read_text('utf-8'))
                if 'functions' in func_data and 'shutter' in func_data['functions']:
                    opt = func_data['functions']['shutter'].get('opt_values', [])
                    print(f'    opt_values: {len(opt)} values')
