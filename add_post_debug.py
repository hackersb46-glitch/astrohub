import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 打印POST请求的body内容
old_post = '''elif method == 'POST':
                async with session.post(isapi_url, data=body, headers=headers, timeout=timeout) as resp:'''

new_post = '''elif method == 'POST':
                print(f'  POST body: {body[:200] if body else "empty"}')
                async with session.post(isapi_url, data=body, headers=headers, timeout=timeout) as resp:'''

content = content.replace(old_post, new_post)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added POST body debug")