#!/usr/bin/env python
"""Debug body comparison between test script and proxy"""
import asyncio
import aiohttp
import hashlib
import re

def encrypt(salt, challenge, iterations, password):
    key = hashlib.sha256(('admin' + salt + password).encode()).hexdigest()
    key = hashlib.sha256((key + challenge).encode()).hexdigest()
    for _ in range(iterations - 2):
        key = hashlib.sha256(key.encode()).hexdigest()
    return key

async def test():
    device_ip = '192.168.5.72'
    
    # Step 1: GET capabilities
    async with aiohttp.ClientSession() as session:
        async with session.get(f'http://{device_ip}:80/ISAPI/Security/sessionLogin/capabilities?username=admin') as resp:
            caps = await resp.text()
    
    sid = re.search(r'<sessionID>([^<]+)</sessionID>', caps).group(1)
    ch = re.search(r'<challenge>([^<]+)</challenge>', caps).group(1)
    it = int(re.search(r'<iterations>([^<]+)</iterations>', caps).group(1))
    sa = re.search(r'<salt>([^<]+)</salt>', caps).group(1)
    
    key = encrypt(sa, ch, it, 'Nftw1357')
    body = f'<SessionLogin><userName>admin</userName><password>{key}</password><sessionID>{sid}</sessionID></SessionLogin>'
    
    print(f"sessionID: {sid}")
    print(f"challenge: {ch}")
    print(f"salt: {sa}")
    print(f"iterations: {it}")
    print(f"password hash: {key}")
    print(f"body length: {len(body)}")
    print(f"body: {body}")
    
    # Step 2: POST login
    async with aiohttp.ClientSession() as session:
        async with session.post(f'http://{device_ip}:80/ISAPI/Security/sessionLogin',
            data=body.encode('utf-8'),
            headers={'Content-Type': 'application/xml'}) as resp:
            login = await resp.text()
            print(f"\nPOST status: {resp.status}")
            print(f"Response: {login}")

asyncio.run(test())