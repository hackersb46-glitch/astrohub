#!/usr/bin/env python
"""Check if proxy POST uses correct sessionID"""
import requests
import hashlib
import re

s = requests.Session()

# GET via proxy
print("=== PROXY GET ===")
r1 = s.get('http://localhost:10280/ISAPI/Security/sessionLogin/capabilities?username=admin')
print(f'Status: {r1.status_code}')
print(f'Response: {r1.text[:200]}')

sid = re.search(r'<sessionID>([^<]+)</sessionID>', r1.text).group(1)
ch = re.search(r'<challenge>([^<]+)</challenge>', r1.text).group(1)
it = int(re.search(r'<iterations>([^<]+)</iterations>', r1.text).group(1))
sa = re.search(r'<salt>([^<]+)</salt>', r1.text).group(1)

print(f'\nsessionID from GET: {sid}')

# 计算加密密码
key = hashlib.sha256(('admin' + sa + 'Nftw1357').encode()).hexdigest()
key = hashlib.sha256((key + ch).encode()).hexdigest()
for _ in range(it - 2):
    key = hashlib.sha256(key.encode()).hexdigest()

body = f'<SessionLogin><userName>admin</userName><password>{key}</password><sessionID>{sid}</sessionID></SessionLogin>'

print(f'\n=== PROXY POST ===')
print(f'Using sessionID: {sid}')
print(f'POST body: {body}')

r2 = s.post('http://localhost:10280/ISAPI/Security/sessionLogin',
    data=body.encode('utf-8'),
    headers={'Content-Type': 'application/xml'})

print(f'\nStatus: {r2.status_code}')
print(f'Response: {r2.text}')