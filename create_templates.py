import sys
sys.stdout.reconfigure(encoding='utf-8')

html_path = r'D:\astro_py\astro_hub\src\web\index.html.bak'
with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Extract base template (before dashboard page)
base_end = content.find('<!-- ==================== 仪表盘 ====================')
base_content = content[:base_end]

# Add includes placeholder and close base structure
base_content += '''
        <!-- ==================== Page Modules ==================== -->
        {% include "includes/dashboard.html" %}
        {% include "includes/devices.html" %}
        {% include "includes/console.html" %}
        {% include "includes/observation.html" %}
        {% include "includes/advanced.html" %}
        {% include "includes/replay.html" %}
        <!-- Toast Container -->
        <div id="toastContainer"></div>
        <!-- Modal Container -->
        <div id="modalContainer"></div>
    </div>

    <!-- ==================== JavaScript ==================== -->
    <script src="/static/js/modules/common.js"></script>
    <script src="/static/js/modules/devices.js"></script>
    <script src="/static/js/modules/ptz.js"></script>
    <script src="/static/js/modules/console.js"></script>
    <script src="/static/js/modules/wasm.js"></script>
</body>
</html>'''

# Write base.html
base_path = r'D:\astro_py\astro_hub\src\web\base.html'
with open(base_path, 'w', encoding='utf-8') as f:
    f.write(base_content)
print(f'Created base.html ({len(base_content)} chars)')

# 2. Extract page modules (already done in includes/)
print('Page modules already in includes/')

# 3. Create index.html that extends base
index_content = '''{% extends "base.html" %}'''
index_path = r'D:\astro_py\astro_hub\src\web\index.html'
with open(index_path, 'w', encoding='utf-8') as f:
    f.write(index_content)
print(f'Created index.html ({len(index_content)} chars)')

print('Done')