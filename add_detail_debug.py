import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加更详细的调试
old_log = '''print(f'[ISAPI #{req_count}] device={session_key}, method={method}, sessions_cached={list(_isapi_sessions.keys())}')'''

new_log = '''print(f'[ISAPI #{req_count}] device={session_key}, method={method}')
            print(f'  sessions: {list(_isapi_sessions.keys())}')
            if session:
                print(f'  session._loop: {id(session._loop) if hasattr(session, "_loop") else "N/A"}')
            print(f'  isapi_url: {isapi_url}')
            print(f'  body len: {len(body) if body else 0}')'''

content = content.replace(old_log, new_log)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added detailed debug")