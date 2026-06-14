import sys
sys.stdout.reconfigure(encoding='utf-8')

main_path = r'D:\astro_py\astro_hub\src\main.py'
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if Jinja2 already added
if 'Jinja2Templates' in content:
    print('Jinja2 already configured')
else:
    # Add import
    content = content.replace(
        'from fastapi.responses import FileResponse, HTMLResponse, Response',
        'from fastapi.responses import FileResponse, HTMLResponse, Response\nfrom fastapi.templating import Jinja2Templates'
    )
    print('Added Jinja2Templates import')
    
    # Add templates config after _WEB_DIR
    content = content.replace(
        '_WEB_DIR = Path(__file__).parent / "web"',
        '_WEB_DIR = Path(__file__).parent / "web"\n_templates = Jinja2Templates(directory=str(_WEB_DIR))'
    )
    print('Added templates config')
    
    # Modify serve_index
    content = content.replace(
        '@app.get("/", response_class=HTMLResponse)\n    async def serve_index() -> HTMLResponse:\n        return _INDEX_HTML.read_text(encoding="utf-8")',
        '@app.get("/", response_class=HTMLResponse)\n    async def serve_index(request: Request) -> HTMLResponse:\n        return _templates.TemplateResponse("index.html", {"request": request})'
    )
    print('Modified serve_index')
    
    # Add Request import
    if 'from fastapi import Request' not in content:
        content = content.replace(
            'from fastapi import FastAPI',
            'from fastapi import FastAPI, Request'
        )
        print('Added Request import')

with open(main_path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Saved main.py')