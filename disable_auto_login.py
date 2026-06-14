import re

html_path = r"D:\astro_py\astro_hub\src\web\index.html"

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove auto-login block that runs on page load
# The user explicitly said: login should happen when clicking "Connect" button

# Pattern: Auto-detect block in refreshDevices
old_auto_login = r'''// Auto-detect: if there's a device with credentials, fetch creds and auto-login
                console\.log\('\[AUTO-LOGIN\] allDevices:', allDevices\);
                var autoDev = allDevices\.find\(function\(d\) \{ return d\.has_credentials; \}\);
                console\.log\('\[AUTO-LOGIN\] autoDev:', autoDev, 'window\.connectedDevice:', window\.connectedDevice\);
                if \(autoDev && !window\.connectedDevice\) \{[^}]*apiGet\('/api/v1/ptz/devices/'[^}]*setTimeout\(function\(\)[^}]*\}, 1000\);
                \}
            \}\)\.catch\(function\(e\) \{[^}]*\}\);'''

# Simplified: just comment out the auto-login block
content = re.sub(
    r"// Auto-detect: if there's a device with credentials",
    "// DISABLED: Auto-login removed - user must click Connect button first",
    content
)

# Also disable the setTimeout auto-login calls
content = re.sub(
    r"console\.log\('\[AUTO-LOGIN\]",
    "// console.log('[AUTO-LOGIN] DISABLED:",
    content
)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Disabled auto-login logic")