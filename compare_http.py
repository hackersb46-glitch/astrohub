#!/usr/bin/env python
"""Compare HTTP requests at low level"""
import http.client
import hashlib
import re

def encrypt_password(salt, challenge, iterations, password):
    key = hashlib.sha256(('admin' + salt + password).encode()).hexdigest()
    key = hashlib.sha256((key + challenge).encode()).hexdigest()
    for _ in range(iterations - 2):
        key = hashlib.sha256(key.encode()).hexdigest()
    return key

print("=== DIRECT HTTP CONNECTION ===")

# Direct connection to camera
conn1 = http.client.HTTPConnection("192.168.5.72", 80)
conn1.request("GET", "/ISAPI/Security/sessionLogin/capabilities?username=admin")
resp1 = conn1.getresponse()
print(f"GET Status: {resp1.status}")
print(f"GET Headers: {resp1.getheaders()}")
caps1 = resp1.read().decode('utf-8')

sid1 = re.search(r'<sessionID>([^<]+)</sessionID>', caps1).group(1)
ch1 = re.search(r'<challenge>([^<]+)</challenge>', caps1).group(1)
it1 = int(re.search(r'<iterations>([^<]+)</iterations>', caps1).group(1))
sa1 = re.search(r'<salt>([^<]+)</salt>', caps1).group(1)

key1 = encrypt_password(sa1, ch1, it1, 'Nftw1357')
body1 = f'<SessionLogin><userName>admin</userName><password>{key1}</password><sessionID>{sid1}</sessionID></SessionLogin>'

# POST using same connection
conn1.request("POST", "/ISAPI/Security/sessionLogin", 
    body=body1.encode('utf-8'),
    headers={"Content-Type": "application/xml", "Content-Length": str(len(body1))})
resp2 = conn1.getresponse()
print(f"\nPOST Status: {resp2.status}")
print(f"POST Headers: {resp2.getheaders()}")
conn1.close()

print("\n=== PROXY HTTP CONNECTION ===")

# Connection to proxy
conn2 = http.client.HTTPConnection("localhost", 10280)
conn2.request("GET", "/ISAPI/Security/sessionLogin/capabilities?username=admin")
resp3 = conn2.getresponse()
print(f"GET Status: {resp3.status}")
print(f"GET Headers: {resp3.getheaders()}")
caps2 = resp3.read().decode('utf-8')

sid2 = re.search(r'<sessionID>([^<]+)</sessionID>', caps2).group(1)
ch2 = re.search(r'<challenge>([^<]+)</challenge>', caps2).group(1)
it2 = int(re.search(r'<iterations>([^<]+)</iterations>', caps2).group(1))
sa2 = re.search(r'<salt>([^<]+)</salt>', caps2).group(1)

key2 = encrypt_password(sa2, ch2, it2, 'Nftw1357')
body2 = f'<SessionLogin><userName>admin</userName><password>{key2}</password><sessionID>{sid2}</sessionID></SessionLogin>'

# POST using same connection
conn2.request("POST", "/ISAPI/Security/sessionLogin",
    body=body2.encode('utf-8'),
    headers={"Content-Type": "application/xml", "Content-Length": str(len(body2))})
resp4 = conn2.getresponse()
print(f"\nPOST Status: {resp4.status}")
print(f"POST Headers: {resp4.getheaders()}")
conn2.close()

print("\n=== COMPARISON ===")
print(f"Direct: GET={resp1.status}, POST={resp2.status}")
print(f"Proxy:  GET={resp3.status}, POST={resp4.status}")
print(f"Same sessionID: {sid1 == sid2}")