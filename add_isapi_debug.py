import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging to ISAPI proxy
old_log = "log.info('[ISAPI Proxy] %s -> %s', method, isapi_url)"

new_log = """log.info('[ISAPI Proxy] %s -> %s', method, isapi_url)
        log.info('[ISAPI] Using session for %s: %s', device_ip, 'new' if not session or getattr(session, 'closed', False) else 'cached')"""

content = content.replace(old_log, new_log)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added debug logging")