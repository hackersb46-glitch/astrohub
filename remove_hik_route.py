import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

py_path = r'D:\astro_py\astro_hub\src\main.py'
with open(py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove /hik route block
pattern = r'@app\.get\("/hik"\)\s+async def hik_page\(\):.*?raise HTTPException\(status_code=404, detail="hik\.html not found"\)'
match = re.search(pattern, content, re.DOTALL)
if match:
    content = content.replace(match.group(), '')
    print('Removed /hik route block')
else:
    print('Pattern not found, trying alternative...')
    # Alternative: remove lines between @app.get("/hik") and next route
    lines = content.split('\n')
    new_lines = []
    skip = False
    for line in lines:
        if '@app.get("/hik")' in line:
            skip = True
            continue
        if skip and line.strip().startswith('# =') or (skip and '@app.get' in line and '/hik' not in line):
            skip = False
        if not skip:
            new_lines.append(line)
    content = '\n'.join(new_lines)
    print('Removed using line-by-line method')

with open(py_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved')