import os

filepath = r"C:\Users\admin\.openclaw\agents\dev-factory\astrohub\src\web\base.html"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. WASM 登录成功
content = content.replace(
    "g_bLoggedIn2 = true;\n              console.log('[WASM SDK] Login success: ' + g_szDeviceIdentify2);",
    "g_bLoggedIn2 = true;\n              console.log('[WASM SDK] Login success: ' + g_szDeviceIdentify2);\n              if (typeof ptzLog === 'function') ptzLog('WASM 登录成功', 'success');"
)

# 2. WASM 登录失败
content = content.replace(
    "console.error('[WASM SDK] Login failed:', status);\n              g_bLoggedIn2 = false;",
    "console.error('[WASM SDK] Login failed:', status);\n              g_bLoggedIn2 = false;\n              if (typeof ptzLog === 'function') ptzLog('WASM 登录失败: ' + status, 'error');"
)

# 3. 视频流开始播放
content = content.replace(
    "g_bPlaying2 = true;\n                  console.log('[WASM SDK] Real play started');",
    "g_bPlaying2 = true;\n                  console.log('[WASM SDK] Real play started');\n                  if (typeof ptzLog === 'function') ptzLog('视频流开始播放', 'success');"
)

# 4. 视频流播放错误
content = content.replace(
    "console.error('[WASM SDK] StartRealPlay error:', status);",
    "console.error('[WASM SDK] StartRealPlay error:', status);\n                  if (typeof ptzLog === 'function') ptzLog('视频播放错误: ' + status, 'error');"
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Added ptzLog calls")
