from src.core.config_manager import ConfigManager

config = ConfigManager()
ptz_config = config.load_ptz_config()
devices = ptz_config.get('devices', {})

for mac, dev in devices.items():
    print(f'MAC: {mac}')
    print(f'  IP: {dev.get("ip")}')
    print(f'  username: {dev.get("username")}')
    password = dev.get('password')
    print(f'  password: {"***" if password else "(empty)"}')
    print(f'  port: {dev.get("port", 80)}')