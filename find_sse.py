with open('astrohub/src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find SSE event handlers for whitebalance and focus
for keyword in ['event: whitebalance', 'event: focus', 'done', 'catch']:
    idx = content.find(keyword)
    while idx >= 0:
        start = max(0, idx - 150)
        end = min(len(content), idx + 400)
        print(f'--- Found "{keyword}" at {idx} ---')
        print(content[start:end])
        print()
        idx = content.find(keyword, idx + 1)
        if idx > 0 and idx - content.find(keyword) > 5000:  # limit to first few matches
            break
