import sys
sys.stdout.reconfigure(encoding='utf-8')

html_path = r'D:\astro_py\astro_hub\src\web\index.html.bak'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Extract base template (everything except page modules)
base_end = content.find('<!-- ==================== 仪表盘 ====================')
base_content = content[:base_end]

# 2. Add includes and toast/modal from end section
end_section_start = content.find('<!-- ==================== 状态提示/弹窗 ====================')
end_section = content[end_section_start:]

# Combine base + includes placeholder + end section (scripts)
base_content += '''
        <!-- ==================== Page Modules ==================== -->
        {% include "includes/dashboard.html" %}
        {% include "includes/devices.html" %}
        {% include "includes/console.html" %}
        {% include "includes/observation.html" %}
        {% include "includes/advanced.html" %}
        {% include "includes/replay.html" %}
''' + end_section

# Write base.html
base_path = r'D:\astro_py\astro_hub\src\web\base.html'
with open(base_path, 'w', encoding='utf-8') as f:
    f.write(base_content)
print(f'Created base.html ({len(base_content)} chars)')

# 3. Create index.html that extends base
index_content = '''{% extends "base.html" %}'''
index_path = r'D:\astro_py\astro_hub\src\web\index.html'
with open(index_path, 'w', encoding='utf-8') as f:
    f.write(index_content)
print(f'Created index.html ({len(index_content)} chars)')

print('Done')