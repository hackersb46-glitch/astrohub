import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 删除错误的print语句
bad_print = '''print(f'  DEBUG session: id={id(session)}')'''

content = content.replace(bad_print, '')

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Removed bad print")