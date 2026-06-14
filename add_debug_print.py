# 测试代理是否真的使用了 session cache
# 在代理内添加全局计数器来验证

import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 添加请求计数器来验证代理被调用
old_session_check = '''session_key = device_ip
            session = _isapi_sessions.get(session_key)'''

new_session_check = '''session_key = device_ip
            global _isapi_request_count
            _isapi_request_count = getattr(__builtins__, '_isapi_request_count', 0) + 1
            print(f'[ISAPI DEBUG #{_isapi_request_count}] device={session_key}, method={method}')
            session = _isapi_sessions.get(session_key)'''

content = content.replace(old_session_check, new_session_check)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added debug print")