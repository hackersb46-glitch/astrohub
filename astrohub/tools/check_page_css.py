"""Check .page CSS in index.html"""

with open('src/web/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find style or <style> block
import re

# Extract the main <style> block or inline styles
style_matches = re.finditer(r'<style[^>]*>(.*?)</style>', content, re.DOTALL)
for match in style_matches:
    style_content = match.group(1)
    if '.page' in style_content or '.page,' in style_content:
        print('=== .page CSS found in <style> block ===')
        # Find .page CSS
        for line in style_content.split('\n'):
            if '.page' in line:
                print(line.strip())

print('\n=== Checking if .page has display settings ===')

# Check for .page classes
page_classes = {}
for match in re.finditer(r'(\.[a-zA-Z-]+)(?:\s*\{[^}]*\}|\s*,)', content):
    cls = match.group(1)
    if '.page' in cls or '.page,' in cls:
        print(f'Found: {cls}')

# Check active class assignment in initNav
nav_section = content[content.find('function initNav'):]
nav_section = nav_section[:1000]  # First 1000 chars

import re
active_assignments = re.findall(r'\.active', nav_section)
print(f'\nactive class is accessed (via \'.active\') in: {len(active_assignments)} locations')

# Check if .page.active is set
if 'page-active' in nav_section:
    print('Note: Uses page-active class, not .page.active')
else:
    print('.page element gets .active class applied')
