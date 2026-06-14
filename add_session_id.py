import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在session创建后打印session ID
old_log = '''log.info('[ISAPI Session] device=%s, new=%s, id=%s', session_key, is_new, id(session))'''

new_log = '''log.info('[ISAPI Session] device=%s, new=%s, session_id=%s', session_key, is_new, id(session))
              print(f'  DEBUG session object id: {id(session)}')'''

content = content.replace(old_log, new_log)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added session id debug")