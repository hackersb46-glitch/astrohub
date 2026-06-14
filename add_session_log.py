import re

with open('D:/py_app/astro_hub/src/main/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Check the session creation code
session_code = '''# Use cached session for sessionLogin consistency
            session = _isapi_sessions.get(device_ip)
            if not session or getattr(session, 'closed', False):
                session = aiohttp.ClientSession()
                _isapi_sessions[device_ip] = session'''

# Replace with a version that logs the session ID
new_session_code = '''# Use cached session for sessionLogin consistency
            session_key = device_ip
            session = _isapi_sessions.get(session_key)
            is_new = not session or getattr(session, 'closed', False)
            if is_new:
                session = aiohttp.ClientSession()
                _isapi_sessions[session_key] = session
            log.info('[ISAPI Session] device=%s, new=%s, id=%s', session_key, is_new, id(session))'''

content = content.replace(session_code, new_session_code)

with open('D:/py_app/astro_hub/src/main/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added session logging")