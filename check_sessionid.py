#!/usr/bin/env python
"""Compare sessionID from direct vs proxy"""
import requests
import hashlib
import re

print("=== DIRECT GET ===")
s1 = requests.Session()
r1 = s1.get('http://192.168.5.72:80/ISAPI/Security/sessionLogin/capabilities?username=admin')
sid1 = re.search(r'<sessionID>([^<]+)</sessionID>', r1.text).group(1)
print(f'Direct sessionID: {sid1}')

print("\n=== PROXY GET ===")
s2 = requests.Session()
r2 = s2.get('http://localhost:10280/ISAPI/Security/sessionLogin/capabilities?username=admin')
sid2 = re.search(r'<sessionID>([^<]+)</sessionID>', r2.text).group(1)
print(f'Proxy sessionID: {sid2}')

print("\n=== SAME SESSIONID? ===")
print(f'{sid1 == sid2}')

# 如果不同，检查摄像头是否基于来源IP区分
print("\n=== CHECK: SAME aiohttp session ===")
# 代理用同一个 aiohttp session，但摄像头返回不同 sessionID
# 说明摄像头可能根据 HTTP 连接来源区分

# 检查代理内部 session 的行为
print("Testing proxy internal session reuse...")