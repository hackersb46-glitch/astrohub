import re

path = 'C:/Users/admin/.openclaw/agents/dev-factory/astrohub/src/api/router.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = 'irCutFilter'
new = 'ircutFilter'

count = content.count(old)
content = content.replace(old, new)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Replaced '{old}' -> '{new}': {count} occurrences")
