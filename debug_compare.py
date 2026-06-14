#!/usr/bin/env python
"""
Debug ISAPI proxy - compare direct vs proxy in detail
"""
import requests
import hashlib
import re

def encrypt_password(salt, challenge, iterations, password):
    """Hikvision irreversible encryption"""
    key = hashlib.sha256(('admin' + salt + password).encode()).hexdigest()
    key = hashlib.sha256((key + challenge).encode()).hexdigest()
    for _ in range(iterations - 2):
        key = hashlib.sha256(key.encode()).hexdigest()
    return key

print("=" * 60)
print("DIRECT ACCESS TEST")
print("=" * 60)

s1 = requests.Session()

# GET capabilities
r1 = s1.get('http://192.168.5.72:80/ISAPI/Security/sessionLogin/capabilities?username=admin', timeout=10)
print(f"\n[1] GET /capabilities")
print(f"    Status: {r1.status_code}")
print(f"    Response headers: {dict(r1.headers)}")

caps_text = r1.text
sid1 = re.search(r'<sessionID>([^<]+)</sessionID>', caps_text).group(1)
ch1 = re.search(r'<challenge>([^<]+)</challenge>', caps_text).group(1)
it1 = int(re.search(r'<iterations>([^<]+)</iterations>', caps_text).group(1))
sa1 = re.search(r'<salt>([^<]+)</salt>', caps_text).group(1)

print(f"\n    Parsed:")
print(f"    sessionID: {sid1[:20]}...")
print(f"    challenge: {ch1[:20]}...")
print(f"    iterations: {it1}")
print(f"    salt: {sa1[:20]}...")

# POST login
key1 = encrypt_password(sa1, ch1, it1, 'Nftw1357')
body1 = f'<SessionLogin><userName>admin</userName><password>{key1}</password><sessionID>{sid1}</sessionID></SessionLogin>'

print(f"\n[2] POST /sessionLogin")
print(f"    Body: {body1[:100]}...")
print(f"    Cookie before POST: {s1.cookies}")

r2 = s1.post('http://192.168.5.72:80/ISAPI/Security/sessionLogin',
    data=body1.encode('utf-8'),
    headers={'Content-Type': 'application/xml'}, timeout=10)

print(f"    Status: {r2.status_code}")
print(f"    Response headers: {dict(r2.headers)}")
print(f"    Cookie after POST: {s1.cookies}")

print("\n" + "=" * 60)
print("PROXY ACCESS TEST")
print("=" * 60)

s2 = requests.Session()

# GET via proxy
r3 = s2.get('http://localhost:10280/ISAPI/Security/sessionLogin/capabilities?username=admin', timeout=10)
print(f"\n[1] GET /capabilities (via proxy)")
print(f"    Status: {r3.status_code}")
print(f"    Response headers: {dict(r3.headers)}")

caps_text2 = r3.text
sid2 = re.search(r'<sessionID>([^<]+)</sessionID>', caps_text2).group(1)
ch2 = re.search(r'<challenge>([^<]+)</challenge>', caps_text2).group(1)
it2 = int(re.search(r'<iterations>([^<]+)</iterations>', caps_text2).group(1))
sa2 = re.search(r'<salt>([^<]+)</salt>', caps_text2).group(1)

print(f"\n    Parsed:")
print(f"    sessionID: {sid2[:20]}...")
print(f"    challenge: {ch2[:20]}...")
print(f"    iterations: {it2}")
print(f"    salt: {sa2[:20]}...")

# POST via proxy
key2 = encrypt_password(sa2, ch2, it2, 'Nftw1357')
body2 = f'<SessionLogin><userName>admin</userName><password>{key2}</password><sessionID>{sid2}</sessionID></SessionLogin>'

print(f"\n[2] POST /sessionLogin (via proxy)")
print(f"    Body: {body2[:100]}...")
print(f"    Cookie before POST: {s2.cookies}")

r4 = s2.post('http://localhost:10280/ISAPI/Security/sessionLogin',
    data=body2.encode('utf-8'),
    headers={'Content-Type': 'application/xml'}, timeout=10)

print(f"    Status: {r4.status_code}")
print(f"    Response headers: {dict(r4.headers)}")
print(f"    Cookie after POST: {s2.cookies}")

print("\n" + "=" * 60)
print("COMPARISON")
print("=" * 60)
print(f"\nDirect sessionID: {sid1[:30]}...")
print(f"Proxy sessionID:  {sid2[:30]}...")
print(f"Same sessionID: {sid1 == sid2}")
print(f"\nDirect password hash: {key1[:40]}...")
print(f"Proxy password hash:  {key2[:40]}...")
print(f"Same password: {key1 == key2}")
print(f"\nDirect POST status: {r2.status_code}")
print(f"Proxy POST status:  {r4.status_code}")