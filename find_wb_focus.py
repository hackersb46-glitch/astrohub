with open('astrohub/src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Search for whitebalance/focus related code
for keyword in ['whitebalance', 'focus', 'vision']:
    idx = content.find(keyword)
    count = 0
    while idx >= 0 and count < 3:
        start = max(0, idx - 200)
        end = min(len(content), idx + 400)
        print(f'--- Found "{keyword}" at {idx} (match {count+1}) ---')
        print(content[start:end])
        print()
        idx = content.find(keyword, idx + 1)
        count += 1
