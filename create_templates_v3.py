import sys
sys.stdout.reconfigure(encoding='utf-8')

html_path = r'D:\astro_py\astro_hub\src\web\index.html.bak'
with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Structure:
# Lines 1-162: HTML head, CSS, nav
# Lines 163-499: Page modules (dashboard, devices, console, observation, advanced, replay)
# Lines 500-503: Toast/Modal containers
# Lines 504-2278: JavaScript

# 1. Base: head + CSS + nav + includes placeholder + toast/modal + scripts
base_lines = lines[:162]  # Head, CSS, nav

# Add includes placeholder
base_lines.append('\n        <!-- ==================== Page Modules ==================== -->\n')
base_lines.append('        {% include "includes/dashboard.html" %}\n')
base_lines.append('        {% include "includes/devices.html" %}\n')
base_lines.append('        {% include "includes/console.html" %}\n')
base_lines.append('        {% include "includes/observation.html" %}\n')
base_lines.append('        {% include "includes/advanced.html" %}\n')
base_lines.append('        {% include "includes/replay.html" %}\n')
base_lines.append('    </div>\n')

# Add toast/modal + scripts
base_lines.extend(lines[499:])  # Toast, Modal, and all scripts

base_content = ''.join(base_lines)

# Write base.html
base_path = r'D:\astro_py\astro_hub\src\web\base.html'
with open(base_path, 'w', encoding='utf-8') as f:
    f.write(base_content)
print(f'Created base.html ({len(base_content)} chars, {len(base_lines)} lines)')

# 2. Create index.html
index_content = '{% extends "base.html" %}'
index_path = r'D:\astro_py\astro_hub\src\web\index.html'
with open(index_path, 'w', encoding='utf-8') as f:
    f.write(index_content)
print(f'Created index.html')

print('Done')