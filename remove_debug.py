import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the debug logging line that causes the error
old_log = "log.info('[ISAPI] Using session for %s: %s', device_ip, 'new' if not session or getattr(session, 'closed', False) else 'cached')"

# Just remove it
content = content.replace(old_log, "")

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Removed debug log")