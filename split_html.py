import sys
import re
sys.stdout.reconfigure(encoding='utf-8')

html_path = r'D:\astro_py\astro_hub\src\web\index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all page sections
pages = {
    'dashboard': ('id="page-dashboard"', 'id="page-devices"'),
    'devices': ('id="page-devices"', 'id="page-console"'),
    'console': ('id="page-console"', 'id="page-observation"'),
    'observation': ('id="page-observation"', 'id="page-advanced"'),
    'advanced': ('id="page-advanced"', 'id="page-replay"'),
    'replay': ('id="page-replay"', None)
}

includes_dir = r'D:\astro_py\astro_hub\src\web\includes'

for name, (start_marker, end_marker) in pages.items():
    start_idx = content.find(start_marker)
    if end_marker:
        end_idx = content.find(end_marker)
    else:
        # Find end of page-replay div
        end_idx = content.find('</div>\n        </div>\n        <script', start_idx)
    
    if start_idx != -1:
        # Find the opening <div class="page" before the marker
        div_start = content.rfind('<div class="page"', 0, start_idx)
        if div_start != -1:
            section = content[div_start:end_idx]
            # Write to file
            file_path = f'{includes_dir}/{name}.html'
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(section)
            print(f'Created {name}.html ({len(section)} chars)')
    else:
        print(f'Marker not found for {name}')

print('HTML modules extracted')