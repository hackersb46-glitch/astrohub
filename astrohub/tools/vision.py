import base64, json, sys, urllib.request

def analyze(image_path, prompt):
    with open(image_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')
    data = {
        'model': 'qwen3.7-plus',
        'max_tokens': 1024,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': img_b64}},
                {'type': 'text', 'text': prompt}
            ]
        }]
    }
    req = urllib.request.Request(
        'https://coding.dashscope.aliyuncs.com/apps/anthropic/v1/messages',
        data=json.dumps(data).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'x-api-key': 'sk-sp-438656a7e1b740cdbac3f4d0f5369df7',
            'anthropic-version': '2023-06-01'
        }
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode('utf-8'))
        for block in result['content']:
            if block['type'] == 'text': print(block['text'])

if __name__ == '__main__':
    if len(sys.argv) >= 3:
        analyze(sys.argv[1], sys.argv[2])
    else:
        print('Usage: vision.py <image> <prompt>')
