# Check current ISAPI proxy implementation and add session persistence

import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find _isapi_devices and add session cache
old_devices = '''_isapi_devices = {}'''

new_devices = '''_isapi_devices = {}
_isapi_sessions = {}  # Per-device HTTP session cache for sessionLogin'''

content = content.replace(old_devices, new_devices)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added _isapi_sessions cache")