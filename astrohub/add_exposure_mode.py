"""添加曝光模式探测到 function.py"""
import re

with open('src/advanced/function.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 查找插入位置
old_text = '''    # --- P4.5 快门速度 ---
    "shutter": {'''

new_text = '''    # --- P4.4c 曝光模式 (Exposure Mode) ---
    "exposure_mode": {
        "p_id": "P4.4c",
        "label": "曝光模式",
        "endpoint": "/Image/channels/{ch}/exposure",
        "test_key": "ExposureType",
        "test_value": "auto",
        "test_values": ["manual", "auto", "IrisFirst", "ShutterFirst"],
        "mode": "exposure_mode",
        "description": "曝光模式: manual/auto/IrisFirst(光圈优先)/ShutterFirst(快门优先)",
    },

    # --- P4.5 快门速度 ---
    "shutter": {'''

if old_text in content:
    content = content.replace(old_text, new_text)
    with open('src/advanced/function.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('已添加曝光模式探测')
else:
    print('未找到插入位置')
