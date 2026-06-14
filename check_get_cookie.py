#!/usr/bin/env python
"""Check if GET returns cookie in direct access"""
import requests

s = requests.Session()

# GET
r1 = s.get('http://192.168.5.72:80/ISAPI/Security/sessionLogin/capabilities?username=admin')
print(f'[1] GET:')
print(f'Status: {r1.status_code}')
print(f'Response cookies: {r1.cookies}')
print(f'Session cookies after GET: {s.cookies}')
print(f'Response headers: {r1.headers}')

# 检查 Set-Cookie header
if 'Set-Cookie' in r1.headers:
    print(f'Set-Cookie header: {r1.headers["Set-Cookie"]}')
else:
    print('No Set-Cookie in GET response')