with open(r'C:\Users\admin\.openclaw\agents\dev-factory\astrohub\src\api\router.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i in range(50):
        print(f'{i+1}: {lines[i].rstrip()}')
