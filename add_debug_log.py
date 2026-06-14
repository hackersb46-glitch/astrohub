import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug logging for ISAPI proxy
old_log = '''log.info('[ISAPI Proxy] %s -> %s', method, isapi_url)'''

new_log = '''log.info('[ISAPI Proxy] %s -> %s', method, isapi_url)
        if body:
            log.info('[ISAPI Proxy] Body length: %d, Content-Type: %s', len(body), headers.get('Content-Type', 'none'))'''

content = content.replace(old_log, new_log)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added debug logging")