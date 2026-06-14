#!/usr/bin/env python
"""
Detailed comparison of direct vs proxy HTTP requests
"""
import asyncio
import aiohttp
import hashlib
import re
import requests

def encrypt(salt, challenge, iterations, password):
    key = hashlib.sha256(('admin' + salt + password).encode()).hexdigest()
    key = hashlib.sha256((key + challenge).encode()).hexdigest()
    for _ in range(iterations - 2):
        key = hashlib.sha256(key.encode()).hexdigest()
    return key

print("=" * 70)
print("TEST 1: AIOHTTP DIRECT (same session)")
print("=" * 70)

async def test_direct():
    connector = aiohttp.TCPConnector(limit=1, force_close=False)
    session = aiohttp.ClientSession(connector=connector)
    
    # GET
    async with session.get('http://192.168.5.72:80/ISAPI/Security/sessionLogin/capabilities?username=admin') as resp:
        caps = await resp.text()
        print(f"GET Status: {resp.status}")
        print(f"GET Headers: {dict(resp.headers)}")
        
    sid = re.search(r'<sessionID>([^<]+)</sessionID>', caps).group(1)
    ch = re.search(r'<challenge>([^<]+)</challenge>', caps).group(1)
    it = int(re.search(r'<iterations>([^<]+)</iterations>', caps).group(1))
    sa = re.search(r'<salt>([^<]+)</salt>', caps).group(1)
    
    key = encrypt(sa, ch, it, 'Nftw1357')
    body = f'<SessionLogin><userName>admin</userName><password>{key}</password><sessionID>{sid}</sessionID></SessionLogin>'
    
    # POST
    async with session.post('http://192.168.5.72:80/ISAPI/Security/sessionLogin',
        data=body.encode('utf-8'),
        headers={'Content-Type': 'application/xml'}) as resp:
        login = await resp.text()
        print(f"POST Status: {resp.status}")
        print(f"POST Headers: {dict(resp.headers)}")
        print(f"Response: {login[:150]}")
    
    await session.close()

asyncio.run(test_direct())

print("\n" + "=" * 70)
print("TEST 2: REQUESTS DIRECT (same session)")
print("=" * 70)

s = requests.Session()

r1 = s.get('http://192.168.5.72:80/ISAPI/Security/sessionLogin/capabilities?username=admin')
print(f"GET Status: {r1.status_code}")
print(f"GET Headers sent: {dict(r1.request.headers)}")
print(f"GET Headers recv: {dict(r1.headers)}")

caps = r1.text
sid = re.search(r'<sessionID>([^<]+)</sessionID>', caps).group(1)
ch = re.search(r'<challenge>([^<]+)</challenge>', caps).group(1)
it = int(re.search(r'<iterations>([^<]+)</iterations>', caps).group(1))
sa = re.search(r'<salt>([^<]+)</salt>', caps).group(1)

key = encrypt(sa, ch, it, 'Nftw1357')
body = f'<SessionLogin><userName>admin</userName><password>{key}</password><sessionID>{sid}</sessionID></SessionLogin>'

r2 = s.post('http://192.168.5.72:80/ISAPI/Security/sessionLogin',
    data=body.encode('utf-8'),
    headers={'Content-Type': 'application/xml'})

print(f"POST Status: {r2.status_code}")
print(f"POST Headers sent: {dict(r2.request.headers)}")
print(f"POST Headers recv: {dict(r2.headers)}")

print("\n" + "=" * 70)
print("TEST 3: PROXY (via requests)")
print("=" * 70)

s2 = requests.Session()

r3 = s2.get('http://localhost:10280/ISAPI/Security/sessionLogin/capabilities?username=admin')
print(f"GET Status: {r3.status_code}")
print(f"GET Headers sent: {dict(r3.request.headers)}")
print(f"GET Headers recv: {dict(r3.headers)}")

caps2 = r3.text
sid2 = re.search(r'<sessionID>([^<]+)</sessionID>', caps2).group(1)
ch2 = re.search(r'<challenge>([^<]+)</challenge>', caps2).group(1)
it2 = int(re.search(r'<iterations>([^<]+)</iterations>', caps2).group(1))
sa2 = re.search(r'<salt>([^<]+)</salt>', caps2).group(1)

key2 = encrypt(sa2, ch2, it2, 'Nftw1357')
body2 = f'<SessionLogin><userName>admin</userName><password>{key2}</password><sessionID>{sid2}</sessionID></SessionLogin>'

r4 = s2.post('http://localhost:10280/ISAPI/Security/sessionLogin',
    data=body2.encode('utf-8'),
    headers={'Content-Type': 'application/xml'})

print(f"POST Status: {r4.status_code}")
print(f"POST Headers sent: {dict(r4.request.headers)}")
print(f"POST Headers recv: {dict(r4.headers)}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"AIOHTTP direct:  GET=200, POST=200")
print(f"Requests direct: GET=200, POST={r2.status_code}")
print(f"Proxy:           GET=200, POST={r4.status_code}")