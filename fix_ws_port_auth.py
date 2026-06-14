"""Fix WebSocket proxy: use port 7681 (authenticated) and forward WebSession cookie"""
main_py = r"C:\Users\admin\.openclaw\agents\dev-factory\astrohub\src\main\main.py"

with open(main_py, "r", encoding="utf-8") as f:
    content = f.read()

# Change default port from 7682 to 7681
content = content.replace("camera_ws_port = 7682", "camera_ws_port = 7681")

# The proxy already forwards ws_cookie to camera, but the cookie from browser might not be WebSession
# We need to extract WebSession from the proxy's own cookies or from login state
# For now, ensure the cookie forwarding uses the right format

# Check if there's a WebSession cookie being forwarded
# The browser sends cookies like: webVideoCtrlProxyWs=ip:port; webVideoCtrlProxyWsChannel=101
# But camera needs: WebSession_15edb5a7ff=xxx

# The proxy needs to get the WebSession cookie from the ISAPI login response
# For now, let's add a fallback: if no WebSession cookie, try without auth (7682)

# Find the cookie forwarding line and add WebSession fallback
old_auth = '''    # Forward WebSession auth cookie to camera for WebSocket auth
    ws_auth_headers = {"Cookie": ws_cookie} if ws_cookie else {}'''

new_auth = '''    # Forward WebSession auth cookie to camera for WebSocket auth
    # The browser cookie contains WebSession_15edb5a7ff from ISAPI login
    # Parse out just the WebSession cookie for camera auth
    ws_session_cookie = ""
    for c in ws_cookie.split(";"):
        c = c.strip()
        if c.startswith("WebSession"):
            ws_session_cookie = c
            break
    
    # If we have a WebSession cookie, use it for camera auth
    if ws_session_cookie:
        ws_auth_headers = {"Cookie": ws_session_cookie}
        log.info(f"WS proxy: using auth cookie: {ws_session_cookie[:50]}...")
    else:
        ws_auth_headers = {}
        log.info("WS proxy: NO WebSession cookie found, connecting without auth")'''

content = content.replace(old_auth, new_auth)

with open(main_py, "w", encoding="utf-8") as f:
    f.write(content)

# Verify
try:
    compile(content, "main.py", "exec")
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax error: {e}")

# Show key lines
with open(main_py, "r", encoding="utf-8") as f:
    lines = f.readlines()
    for i, line in enumerate(lines):
        if "camera_ws_port = 768" in line or "WebSession" in line or "ws_auth_headers" in line:
            print(f"L{i+1}: {line.rstrip()}")
