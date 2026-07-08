import re

with open('astrohub/src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find SSE event handlers for whitebalance and focus
keywords = ['event: whitebalance', 'event: focus', 'whitebalance-done', 'focus-done', 'wb-done', 'af-done']

for keyword in keywords:
    idx = content.find(keyword)
    if idx >= 0:
        start = max(0, idx - 200)
        end = min(len(content), idx + 500)
        print(f'--- Found "{keyword}" at {idx} ---')
        print(content[start:end])
        print()
