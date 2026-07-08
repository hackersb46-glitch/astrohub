"""Find router.py locations for filter endpoints"""
import re

with open('src/api/router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print('=== Finding filter endpoints in router.py ===\n')

for i, line in enumerate(lines):
    if any(kw in line for kw in ['filter', 'dayNight', 'IrcutFilter']):
        ctx = ''.join(lines[max(0, i-2):min(len(lines), i+10)])
        print(f'{i+1}: {ctx[:200]}')
