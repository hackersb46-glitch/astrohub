#!/usr/bin/env python
"""Capture actual HTTP requests sent by requests vs aiohttp"""
import requests
import hashlib
import re

print("=== DIRECT REQUESTS (via requests.Session) ===")
s = requests.Session()

# GET
r1 = s.get('http://192.168.5.72:80/ISAPI/Security/sessionLogin/capabilities?username=admin')
sid = re.search(r'<sessionID>([^<]+)</sessionID>', r1.text).group(1)
ch = re.search(r'<challenge>([^<]+)</challenge>', r1.text).group(1)
it = int(re.search(r'<iterations>([^<]+)</iterations>', r1.text).group(1))
sa = re.search(r'<salt>([^<]+)</salt>', r1.text).group(1)

key = hashlib.sha256(('admin' + sa + 'Nftw1357').encode()).hexdigest()
key = hashlib.sha256((key + ch).encode()).hexdigest()
for _ in range(it - 2):
    key = hashlib.sha256(key.encode()).hexdigest()

body = f'<SessionLogin><userName>admin</userName><password>{key}</password><sessionID>{sid}</sessionID></SessionLogin>'

# POST
r2 = s.post('http://192.168.5.72:80/ISAPI/Security/sessionLogin',
    data=body.encode('utf-8'),
    headers={'Content-Type': 'application/xml'})

print(f'Direct POST status: {r2.status_code}')
print(f'Direct POST request headers: {r2.request.headers}')
print(f'Direct POST response headers: {r2.headers}')
print(f'Direct POST cookies: {s.cookies}')

print("\n=== PROXY REQUESTS (via proxy) ===")
s2 = requests.Session()

# GET
r3 = s2.get('http://localhost:10280/ISAPI/Security/sessionLogin/capabilities?username=admin')
sid2 = re.search(r'<sessionID>([^<]+)</sessionID>', r3.text).group(1)
ch2 = re.search(r'<challenge>([^<]+)</challenge>', r3.text).group(1)
it2 = int(re.search(r'<iterations>([^<]+)</iterations>', r3.text).group(1))
sa2 = re.search(r'<salt>([^<]+)</salt>', r3.text).group(1)

key2 = hashlib.sha256(('admin' + sa2 + 'Nftw1357').encode()).hexdigest()
key2 = hashlib.sha256((key2 + ch2).encode()).hexdigest()
for _ in range(it2 - 2):
    key2 = hashlib.sha256(key2.encode()).hexdigest()

body2 = f'<SessionLogin><userName>admin</userName><password>{key2}</password><sessionID>{sid2}</sessionID></SessionLogin>'

r4 = s2.post('http://localhost:10280/ISAPI/Security/sessionLogin',
    data=body2.encode('utf-8'),
    headers={'Content-Type': 'application/xml'})

print(f'Proxy POST status: {r4.status_code}')
print(f'Proxy POST request headers: {r4.request.headers}')
print(f'Proxy POST response headers: {r4.headers}')
print(f'Proxy POST cookies: {s2.cookies}')

print("\n=== COMPARISON ===")
print(f'Same password hash? {key == key2}')
print(f'Password hash direct: {key[:50]}')
print(f'Password hash proxy:  {key2[:50]}')