from PIL import Image

for name in ['proxy_preview', 'proxy_main_stream', 'proxy_sub_stream']:
    path = f'astrohub/tests/screenshots/{name}.png'
    try:
        img = Image.open(path)
    except FileNotFoundError:
        print(f'{name}: NOT FOUND')
        continue
    
    region = img.crop((10, 90, 630, 430))
    pixels = list(region.getdata())
    total = len(pixels)
    
    colored = sum(1 for p in pixels if abs(int(p[0])-int(p[1])) > 25 or abs(int(p[1])-int(p[2])) > 25)
    colored_pct = colored/total*100
    
    non_dark = sum(1 for p in pixels if p[0] > 30 or p[1] > 30 or p[2] > 30)
    
    print(f'=== {name} ===')
    print(f'  Colored: {colored_pct:.1f}%, Non-dark: {non_dark/total*100:.1f}%')
    # Sample some pixels from different parts of the image
    step = total // 10
    for i in range(0, total, step):
        p = pixels[i]
        print(f'  Pixel@{i}: R={p[0]} G={p[1]} B={p[2]}')
    print()
