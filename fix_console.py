import re

with open('astrohub/src/web/includes/console.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 在setWhiteBalanceMode中抑制toast（已完成，跳过）
# 2. 在setWhiteBalanceGain中抑制toast（已完成，跳过）
# 3. 在setNoiseReduce中抑制toast（已完成，跳过）

# 4. 修改setShutterSpeed中的showToast
content = content.replace(
    "                showToast('success', '快门: ' + shutterLevel);",
    "                if (!_isInitializingImageParams) showToast('success', '快门: ' + shutterLevel);"
)

# 5. 修改setIrisLevel中的showToast
content = content.replace(
    "                showToast('success', '光圈: ' + label);",
    "                if (!_isInitializingImageParams) showToast('success', '光圈: ' + label);"
)

# 6. 修改setExposureMode中的showToast
content = content.replace(
    "                showToast('success', '曝光: ' + label);",
    "                if (!_isInitializingImageParams) showToast('success', '曝光: ' + label);"
)

# 7. 修改setSharpness中的showToast
content = content.replace(
    "                showToast('success', '锐度: ' + sharpnessLevel);",
    "                if (!_isInitializingImageParams) showToast('success', '锐度: ' + sharpnessLevel);"
)

# 8. 修改setSlowShutter中的showToast
content = content.replace(
    "                showToast('success', '慢快门: ' + (dssLevel === 'off' ? '关闭' : dssLevel));",
    "                if (!_isInitializingImageParams) showToast('success', '慢快门: ' + (dssLevel === 'off' ? '关闭' : dssLevel));"
)

with open('astrohub/src/web/includes/console.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('console.html 修改完成')
