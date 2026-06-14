import re

with open('D:/py_app/astro_hub/src/web/base.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and modify I_InitPlugin config to add proxyAddress pointing to camera
old_config = '''bNoPlugin: true,
                  cbEvent: function(iEventType, iParam1, iParam2) {
                      console.log("[WASM] Event:", iEventType, iParam1, iParam2);
                  },'''

new_config = '''bNoPlugin: true,
                  // For WASM sessionLogin, must directly access camera IP
                  // Proxy mode breaks HTTP session consistency
                  proxyAddress: {
                      ip: '192.168.5.72',
                      port: 80
                  },
                  cbEvent: function(iEventType, iParam1, iParam2) {
                      console.log("[WASM] Event:", iEventType, iParam1, iParam2);
                  },'''

content = content.replace(old_config, new_config)

with open('D:/py_app/astro_hub/src/web/base.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added proxyAddress config for direct camera access")