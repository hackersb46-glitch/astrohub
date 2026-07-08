import json
from pathlib import Path

DEVICES_DIR = Path(r'C:\Users\admin\.openclaw\agents\dev-factory\astrohub\data\devices')
target_ip = '192.168.5.72'

print('DEVICES_DIR exists:', DEVICES_DIR.exists())
print('Iterating devices:')
for device_dir in DEVICES_DIR.iterdir():
    if device_dir.is_dir():
        print(f'  Dir: {device_dir.name}')
        info_file = device_dir / 'info.json'
        if info_file.exists():
            info = json.loads(info_file.read_text(encoding='utf-8'))
            print(f'    IP: {info.get("ip")}')
            if info.get('ip') == target_ip:
                print(f'    MATCH!')
                func_file = device_dir / 'function.json'
                print(f'    function.json exists: {func_file.exists()}')
                if func_file.exists():
                    func_data = json.loads(func_file.read_text(encoding='utf-8'))
                    has_functions = 'functions' in func_data
                    has_shutter = 'shutter' in func_data.get('functions', {})
                    print(f'    functions key: {has_functions}')
                    print(f'    shutter key: {has_shutter}')
                    if has_functions and has_shutter:
                        opt_values = func_data['functions']['shutter'].get('opt_values', [])
                        print(f'    opt_values count: {len(opt_values)}')
                        print(f'    opt_values: {opt_values}')
