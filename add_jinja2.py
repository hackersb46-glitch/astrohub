import sys
sys.stdout.reconfigure(encoding='utf-8')

main_path = r'D:\astro_py\astro_hub\src\main.py'
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add Jinja2 import
old_import = 'from fastapi.responses import FileResponse, HTMLResponse, Response'
new_import = '''from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates'''

if old_import in content and 'Jinja2Templates' not in content:
    content = content.replace(old_import, new_import)
    print('Added Jinja2Templates import')
else:
    print('Import already exists or pattern not found')

# Add templates config after imports
templates_config = '''
# Jinja2 Templates
templates = Jinja2Templates(directory=str(_WEB_DIR))
'''

# Find where to insert (after _WEB_DIR definition)
if 'templates = Jinja2Templates' not in content:
    # Find a good spot to insert
    insert_marker = '_WEB_DIR = Path'
    insert_idx = content.find(insert_marker)
    if insert_idx != -1:
        # Find end of that line section
        end_idx = content.find('\n\n', insert_idx)
        if end_idx != -1:
            content = content[:end_idx] + '\n' + templates_config + content[end_idx:]
            print('Added templates config')

# Modify serve_index to use templates
old_route = '''@app.get("/", response_class=HTMLResponse)
    async def serve_index() -> HTMLResponse:
        return _INDEX_HTML.read_text(encoding="utf-8")'''

new_route = '''@app.get("/", response_class=HTMLResponse)
    async def serve_index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("index.html", {"request": request})'''

if old_route in content:
    content = content.replace(old_route, new_route)
    print('Modified serve_index to use templates')
else:
    print('Route pattern not found')

# Add Request import if not present
if 'from starlette.requests import Request' not in content and 'Request' in new_route:
    old_starlette = 'from starlette.middleware'
    if old_starlette in content:
        # Add Request import
        content = content.replace(old_starlette, 'from starlette.requests import Request\nfrom starlette.middleware')
        print('Added Request import')

with open(main_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved main.py')