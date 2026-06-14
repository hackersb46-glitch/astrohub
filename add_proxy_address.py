import re

# Read file
with open('D:/py_app/astro_hub/src/web/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find I_InitPlugin and add proxyAddress
old_pattern = r'''WebVideoCtrl\.I_InitPlugin\("100%", "100%", \{
                  bWndFull: true,
                  iPackageType: 2,
                  iWndowType: 1,
                  bNoPlugin: true,'''

new_pattern = '''WebVideoCtrl.I_InitPlugin("100%", "100%", {
                  bWndFull: true,
                  iPackageType: 2,
                  iWndowType: 1,
                  bNoPlugin: true,
                  // Direct camera access (bypass proxy for sessionLogin)
                  proxyAddress: {
                      ip: '192.168.5.72',
                      port: 80
                  },'''

content = re.sub(old_pattern, new_pattern, content)

with open('D:/py_app/astro_hub/src/web/base.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added proxyAddress config")