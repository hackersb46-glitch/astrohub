with open('astrohub/src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Search for EventSource related to vision operations
for keyword in ['EventSource', 'vision-search', 'done', 'catch', 'complete', 'whitebalance-done', 'focus-done']:
    positions = []
    idx = content.find(keyword)
    while idx >= 0 and len(positions) < 5:
        positions.append(idx)
        idx = content.find(keyword, idx + 1)
    
    print(f'=== "{keyword}" found at {len(positions)} positions: {positions[:5]} ===')
    for pos in positions[:3]:
        start = max(0, pos - 100)
        end = min(len(content), pos + 300)
        print(f'  pos {pos}: ...{content[start:end][:200]}...')
        print()
