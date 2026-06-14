import sys
sys.stdout.reconfigure(encoding='utf-8')

html_path = r'D:\astro_py\astro_hub\src\web\index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Page boundaries (from earlier analysis)
pages = [
    ('dashboard', 163, 194),    # line 163 to 194 (before devices)
    ('devices', 195, 227),      # line 195 to 227
    ('console', 228, 351),      # line 228 to 351
    ('observation', 352, 378),  # line 352 to 378
    ('advanced', 379, 489),     # line 379 to 489
    ('replay', 490, None)       # line 490 to end of pages
]

includes_dir = r'D:\astro_py\astro_hub\src\web\includes'

# Find end of replay page (before <script>)
replay_end = None
for i, line in enumerate(lines):
    if i >= 489 and '<script>' in line and 'script src' not in line.lower():
        # Find the </div> before script
        for j in range(i-1, 0, -1):
            if '</div>' in lines[j] and 'page' in ''.join(lines[max(0,j-10):j]):
                replay_end = j + 1
                break
        break

if replay_end:
    pages[5] = ('replay', 490, replay_end)

for name, start, end in pages:
    if end:
        section = ''.join(lines[start-1:end])
    else:
        section = ''.join(lines[start-1:])
    
    file_path = f'{includes_dir}/{name}.html'
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(section)
    print(f'Created {name}.html ({len(section)} chars, lines {start}-{end})')

print('Done')