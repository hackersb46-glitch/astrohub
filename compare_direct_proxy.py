#!/usr/bin/env python
"""Fetch official Hikvision ISAPI docs and analyze login flow"""
import requests
import hashlib
import re

# 1. 直接访问摄像头获取完整 capabilities 响应
print("=== DIRECT ACCESS TO CAMERA ===")
s = requests.Session()

caps_url = 'http://192.168.5.72:80/ISAPI/Security/sessionLogin/capabilities?username=admin'
r = s.get(caps_url, timeout=10)
print(f'[1] GET capabilities direct:')
print(f'Status: {r.status_code}')
print(f'Full response:')
print(r.text)
print(f'Cookies: {s.cookies}')

if r.status_code == 200:
    sid = re.search(r'<sessionID>([^<]+)</sessionID>', r.text).group(1)
    ch = re.search(r'<challenge>([^<]+)</challenge>', r.text).group(1)
    it = int(re.search(r'<iterations>([^<]+)</iterations>', r.text).group(1))
    sa = re.search(r'<salt>([^<]+)</salt>', r.text).group(1)
    
    # 检查是否有其他字段
    print(f'\n=== PARSED VALUES ===')
    print(f'sessionID: {sid}')
    print(f'challenge: {ch}')
    print(f'iterations: {it}')
    print(f'salt: {sa}')
    
    # 检查 isIrreversible
    is_irr = re.search(r'<isIrreversible>([^<]+)</isIrreversible>', r.text)
    if is_irr:
        print(f'isIrreversible: {is_irr.group(1)}')
    
    key = hashlib.sha256(('admin' + sa + 'Nftw1357').encode()).hexdigest()
    key = hashlib.sha256((key + ch).encode()).hexdigest()
    for _ in range(it - 2):
        key = hashlib.sha256(key.encode()).hexdigest()
    
    body = f'<SessionLogin><userName>admin</userName><password>{key}</password><sessionID>{sid}</sessionID></SessionLogin>'
    
    print(f'\n=== POST LOGIN ===')
    print(f'Encrypted password: {key[:50]}...')
    print(f'POST body: {body}')
    
    login_url = 'http://192.168.5.72:80/ISAPI/Security/sessionLogin'
    r2 = s.post(login_url, data=body.encode('utf-8'), headers={'Content-Type': 'application/xml'}, timeout=10)
    print(f'\n[2] POST login direct:')
    print(f'Status: {r2.status_code}')
    print(f'Response: {r2.text}')
    print(f'Cookies after POST: {s.cookies}')

# 2. 对比代理请求
print("\n\n=== PROXY ACCESS ===")
s2 = requests.Session()

caps_proxy = 'http://localhost:10280/ISAPI/Security/sessionLogin/capabilities?username=admin'
r3 = s2.get(caps_proxy, timeout=10)
print(f'[1] GET via proxy:')
print(f'Status: {r3.status_code}')
print(f'Response: {r3.text[:200]}')

if r3.status_code == 200:
    sid2 = re.search(r'<sessionID>([^<]+)</sessionID>', r3.text).group(1)
    ch2 = re.search(r'<challenge>([^<]+)</challenge>', r3.text).group(1)
    it2 = int(re.search(r'<iterations>([^<]+)</iterations>', r3.text).group(1))
    sa2 = re.search(r'<salt>([^<]+)</salt>', r3.text).group(1)
    
    key2 = hashlib.sha256(('admin' + sa2 + 'Nftw1357').encode()).hexdigest()
    key2 = hashlib.sha256((key2 + ch2).encode()).hexdigest()
    for _ in range(it2 - 2):
        key2 = hashlib.sha256(key2.encode()).hexdigest()
    
    body2 = f'<SessionLogin><userName>admin</userName><password>{key2}</password><sessionID>{sid2}</sessionID></SessionLogin>'
    
    login_proxy = 'http://localhost:10280/ISAPI/Security/sessionLogin'
    r4 = s2.post(login_proxy, data=body2.encode('utf-8'), headers={'Content-Type': 'application/xml'}, timeout=10)
    print(f'\n[2] POST via proxy:')
    print(f'Status: {r4.status_code}')
    print(f'Response: {r4.text}')
    print(f'Cookies: {s2.cookies}')

print("\n\n=== COMPARISON ===")
print(f"Direct GET sessionID: {sid}")
print(f"Proxy  GET sessionID: {sid2}")
print(f"Same sessionID? {sid == sid2}")
print(f"Direct password hash: {key[:50]}")
print(f"Proxy  password hash: {key2[:50]}")
print(f"Same hash? {key == key2}")