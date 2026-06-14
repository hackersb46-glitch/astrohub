import sys
sys.stdout.reconfigure(encoding='utf-8')

html_path = r'D:\astro_py\astro_hub\src\web\index.html'
with open(html_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Extract base.html (lines 1-162, before dashboard)
base_content = ''.join(lines[:162])

# Add include placeholders at the end of base
base_content += '''
        <!-- ==================== Page Modules ==================== -->
        {% include 'includes/dashboard.html' %}
        {% include 'includes/devices.html' %}
        {% include 'includes/console.html' %}
        {% include 'includes/observation.html' %}
        {% include 'includes/advanced.html' %}
        {% include 'includes/replay.html' %}
    </div>
    <!-- Toast Container -->
    <div class="toast-container" id="toastContainer"></div>
    <!-- Modal Container -->
    <div id="modalContainer"></div>
'''

# Extract JS section (lines 504-2278)
js_content = ''.join(lines[504:])

# Write base.html
base_path = r'D:\astro_py\astro_hub\src\web\base.html'
with open(base_path, 'w', encoding='utf-8') as f:
    f.write(base_content)
print(f'Created base.html ({len(base_content)} chars)')

# Write js to static/js/main.js
js_path = r'D:\astro_py\astro_hub\src\web\static\js\main.js'
with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)
print(f'Created main.js ({len(js_content)} chars)')

print('Done')